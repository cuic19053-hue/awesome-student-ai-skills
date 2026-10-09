from __future__ import annotations

import json
import html
import ipaddress
import os
import re
import socket
import subprocess
import tempfile
import urllib.parse
import urllib.request
import sys
from pathlib import Path
from typing import Any, Callable
from html.parser import HTMLParser
from datetime import datetime, timezone

from .retrieval import ProjectRetriever
from .skills import registry, valid_fact_key
from .storage import Store, new_id

ROOT = Path(__file__).resolve().parents[2]
INNOVATION_SKILL = ROOT / "subskills" / "innovation-research" / "SKILL.md"
IDEA_GUIDE = ROOT / "subskills" / "innovation-research" / "references" / "idea-scaffold.md"


def _official_url(url: str) -> bool:
    host = urllib.parse.urlparse(url).hostname or ""
    host = host.lower().removeprefix("www.")
    return host.endswith((".edu.cn", ".gov.cn")) or host in {
        "moe.gov.cn",
        "www.gov.cn",
        "most.gov.cn",
    }


def _validate_public_official_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url.strip())
    if parsed.scheme.lower() != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("官方来源必须是 HTTPS 链接。")
    host = parsed.hostname.lower()
    try:
        direct_ip = ipaddress.ip_address(host)
    except ValueError:
        direct_ip = None
    # This development host maps outbound DNS through RFC 2544's 198.18/15
    # benchmark range. Keep that host-specific egress alias usable while still
    # blocking ordinary private, loopback, and link-local targets.
    egress_testnet = ipaddress.ip_network("198.18.0.0/15")
    if direct_ip and direct_ip not in egress_testnet and (
        direct_ip.is_private or direct_ip.is_loopback or direct_ip.is_link_local or direct_ip.is_reserved
    ):
        raise ValueError("不允许访问本机或私有网络地址。")
    if not _official_url(url):
        raise ValueError("只允许读取 edu.cn / gov.cn 官方域名。")
    try:
        addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        if not addresses:
            raise ValueError("域名无法解析。")
        for address in addresses:
            ip = ipaddress.ip_address(address[4][0])
            if ip not in egress_testnet and (
                ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved
            ):
                raise ValueError("不允许访问本机或私有网络地址。")
    except socket.gaierror as exc:
        raise ValueError("官方域名无法解析。") from exc
    return url.strip()


class _OfficialPageParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.title_parts: list[str] = []
        self.published_at = ""
        self._skip_depth = 0
        self._in_title = False

    def handle_starttag(self, tag: str, attrs):
        attributes = {key.lower(): value or "" for key, value in attrs}
        if tag in {"script", "style", "noscript", "svg"}:
            self._skip_depth += 1
        if tag == "title":
            self._in_title = True
        if tag == "meta":
            key = (attributes.get("property") or attributes.get("name") or "").lower()
            if key in {"article:published_time", "date", "pubdate", "publishdate"}:
                self.published_at = attributes.get("content", "")
        if tag == "time" and not self.published_at:
            self.published_at = attributes.get("datetime", "")

    def handle_endtag(self, tag: str):
        if tag in {"script", "style", "noscript", "svg"} and self._skip_depth:
            self._skip_depth -= 1
        if tag == "title":
            self._in_title = False

    def handle_data(self, data: str):
        text = re.sub(r"\s+", " ", data).strip()
        if text and not self._skip_depth:
            self.parts.append(text)
            if self._in_title:
                self.title_parts.append(text)


class _OfficialRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _validate_public_official_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class ProposalTools:
    """Shared, bounded tool implementations for Ollama tool-calling and MCP."""

    def __init__(self, store: Store, retriever: ProjectRetriever | None = None):
        self.store = store
        self.retriever = retriever or ProjectRetriever(store)

    def get_project_state(self, project_id: str) -> dict[str, Any]:
        project = self.store.get_project(project_id)
        if not project:
            return {"error": "找不到这个项目。"}
        docs = self.store.list_documents(project_id)
        return {
            "project": project,
            "documents": [
                {
                    "id": d["id"],
                    "name": d["original_name"],
                    "kind": d["kind"],
                    "confirmed": bool(d["confirmed"]),
                    "status": d["extraction_status"],
                    "warning": d["extraction_warning"],
                }
                for d in docs
            ],
        }

    def add_text_material(
        self,
        project_id: str,
        filename: str,
        text: str,
    ) -> dict[str, Any]:
        if not self.store.get_project(project_id):
            return {"error": "找不到这个项目。"}
        if not text.strip() or len(text) > 200000:
            return {"error": "材料文字不能为空，且最多 200,000 字符。"}
        safe_name = Path(filename or "MCP-材料.txt").name
        if not safe_name.lower().endswith(".txt"):
            safe_name += ".txt"
        document_id = new_id()
        project_folder = self.store.files_dir / project_id
        project_folder.mkdir(parents=True, exist_ok=True)
        path = project_folder / f"{document_id}.txt"
        content = text.strip()
        path.write_text(content, encoding="utf-8")
        document = self.store.add_document(
            project_id,
            safe_name,
            str(path),
            "source",
            "text/plain",
            document_id=document_id,
        )
        self.store.update_document_extraction(
            document_id,
            content,
            "ready",
            "",
            0,
            confirmed=False,
        )
        return {
            "document_id": document_id,
            "filename": safe_name,
            "preview": content[:1200],
            "confirmed": False,
            "next_step": "请先让学生核对文字，再调用 confirm_project_material；确认前不会进入 RAG。",
        }

    def confirm_project_material(
        self,
        project_id: str,
        document_id: str,
        corrected_text: str = "",
    ) -> dict[str, Any]:
        document = self.store.get_document(document_id)
        if not document or document["project_id"] != project_id:
            return {"error": "项目材料不存在或不属于当前项目。"}
        if document["kind"] == "template":
            return {"error": "学校模板不作为项目事实材料索引。"}
        text = corrected_text if corrected_text.strip() else document["extracted_text"]
        if not text.strip():
            return {"error": "材料文字为空，请重新上传或补充。"}
        self.store.update_document_extraction(
            document_id,
            text,
            "ready",
            document["extraction_warning"],
            document["low_confidence_count"],
            confirmed=True,
        )
        chunks = self.retriever.index_document(document_id, text)
        return {
            "success": True,
            "filename": document["original_name"],
            "indexed_chunks": chunks,
            "source_notice": "该文字已由调用者确认，可作为本项目 RAG 证据；仍不能超出原文推断事实。",
        }

    def get_writing_guidance(self, project_id: str, section: str = "") -> dict[str, Any]:
        project = self.store.get_project(project_id)
        if not project:
            return {"error": "找不到这个项目。"}
        skill_id = str(project.get("state", {}).get("skill_id", "innovation-research"))
        if skill_id == "innovation-research" and section in {"想法整理", "项目框架", "立项依据"} and IDEA_GUIDE.exists():
            source_path = IDEA_GUIDE
        else:
            selected = registry.get(skill_id) or registry.get("innovation-research")
            source_path = selected["skill_path"] if selected else INNOVATION_SKILL
        text = source_path.read_text(encoding="utf-8")
        lines = text.splitlines()
        if section:
            matches = [i for i, line in enumerate(lines) if line.startswith("#") and section in line]
            if matches:
                start = matches[0]
                end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("#")), len(lines))
                excerpt = "\n".join(lines[start:end])[:7000]
            else:
                excerpt = "\n".join(lines[:240])[:7000]
        else:
            excerpt = "\n".join(lines[:240])[:7000]
        return {
            "source": str(source_path.relative_to(ROOT)),
            "section": section or "起步指南",
            "guidance": excerpt,
            "rule": "只写有用户材料或可核验来源支持的事实；未知内容标为待补充或待验证。",
        }

    def search_project_materials(
        self, project_id: str, query: str, top_k: int = 5
    ) -> dict[str, Any]:
        return self.retriever.search(project_id, query, top_k)

    def search_papers(self, query: str, limit: int = 5) -> dict[str, Any]:
        query = query.strip()[:300]
        if not query:
            return {"results": [], "error": "论文查询关键词不能为空。"}
        params = urllib.parse.urlencode(
            {
                "query.bibliographic": query,
                "rows": max(1, min(limit, 10)),
                "select": "DOI,title,author,published,URL,container-title,type",
            }
        )
        request = urllib.request.Request(
            f"https://api.crossref.org/works?{params}",
            headers={"User-Agent": "AwesomeStudentAIProposalAgent/0.1 (educational project)"},
        )
        try:
            with urllib.request.urlopen(request, timeout=12) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            return {
                "results": [],
                "error": f"暂时无法连接 Crossref：{exc}",
                "note": "请稍后重试或让学生上传论文；不能编造参考文献。",
            }
        items = []
        for item in payload.get("message", {}).get("items", []):
            title = (item.get("title") or [""])[0]
            if not title:
                continue
            authors = [
                " ".join(part for part in [a.get("given"), a.get("family")] if part)
                for a in item.get("author", [])
            ]
            date_parts = (
                item.get("published-print", {}).get("date-parts")
                or item.get("published-online", {}).get("date-parts")
                or []
            )
            year = date_parts[0][0] if date_parts and date_parts[0] else None
            doi = item.get("DOI", "")
            abstract = html.unescape(re.sub(r"<[^>]+>", " ", item.get("abstract", "")))
            abstract = re.sub(r"\s+", " ", abstract).strip()
            abstract = abstract[:2000]
            items.append(
                {
                    "title": title,
                    "authors": authors[:8],
                    "year": year,
                    "venue": (item.get("container-title") or [""])[0],
                    "doi": doi,
                    "url": f"https://doi.org/{doi}" if doi else item.get("URL", ""),
                    "abstract": abstract,
                    "content_checked": bool(abstract),
                    "warning": (
                        "只有摘要/元数据，没有论文正文；不可声称已阅读全文。"
                        if abstract
                        else "只有题名和元数据，尚无摘要或正文；不可写研究结论。"
                    ),
                }
            )
        return {"query": query, "results": items, "source": "Crossref"}

    def search_official_notices(
        self, query: str, school: str = "", max_results: int = 5
    ) -> dict[str, Any]:
        query = query.strip()[:300]
        school = school.strip()[:120]
        if not query:
            return {"results": [], "error": "官方通知查询关键词不能为空。"}
        full_query = f"{school} {query} 大学生创新训练计划".strip()
        searxng_url = os.environ.get("SEARXNG_URL", "").strip()
        if searxng_url:
            params = urllib.parse.urlencode(
                {"q": f"{full_query} site:edu.cn OR site:gov.cn", "format": "json", "categories": "general"}
            )
            try:
                endpoint = urllib.parse.urljoin(searxng_url.rstrip("/") + "/", f"search?{params}")
                with urllib.request.urlopen(endpoint, timeout=8) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                candidates = payload.get("results", [])
                results = [
                    {
                        "title": item.get("title", ""),
                        "url": item.get("url", ""),
                        "snippet": item.get("content", ""),
                        "published_at": item.get("publishedDate", ""),
                        "source_domain": urllib.parse.urlparse(item.get("url", "")).hostname,
                        "source_type": "official-domain-search-result",
                        "warning": "请打开原始通知核验年份、适用范围和附件；摘要不等于官方全文。",
                    }
                    for item in candidates
                    if _official_url(item.get("url", ""))
                ][:max_results]
                return {
                    "query": full_query,
                    "results": results,
                    "source": "configured SearXNG",
                    "note": "只返回 edu.cn / gov.cn 官方域名结果。",
                }
            except Exception as exc:
                searxng_error = str(exc)
        else:
            searxng_error = ""
        try:
            from ddgs import DDGS
        except ImportError:
            return {
                "results": [],
                "error": "官网搜索依赖尚未安装，请执行 pip install -r server/requirements.txt。",
            }
        full_query = f"{full_query} site:edu.cn OR site:gov.cn"
        try:
            candidates = list(
                DDGS(timeout=5).text(
                    full_query,
                    max_results=max(5, min(max_results * 3, 15)),
                    backend=os.environ.get("DDGS_BACKEND", "duckduckgo"),
                    region="cn-zh",
                )
            )
        except Exception as exc:
            fallback = "；也可粘贴学校官网 HTTPS 通知链接或上传通知文件。"
            if searxng_error:
                fallback = f"；SearXNG 错误：{searxng_error}" + fallback
            return {"results": [], "error": f"搜索暂不可用：{exc}{fallback}"}
        results = []
        for item in candidates:
            url = item.get("href") or item.get("url") or ""
            if not _official_url(url):
                continue
            results.append(
                {
                    "title": item.get("title", ""),
                    "url": url,
                    "snippet": item.get("body", ""),
                    "published_at": item.get("published") or item.get("date") or "",
                    "source_domain": urllib.parse.urlparse(url).hostname,
                    "source_type": "official-domain-search-result",
                    "warning": "请打开原始通知核验年份、适用范围和附件；摘要不等于官方全文。",
                }
            )
            if len(results) >= max_results:
                break
        return {
            "query": full_query,
            "results": results,
            "note": "仅返回 edu.cn / gov.cn 官方域名结果；检索不到时请学生上传学校通知。",
        }

    def fetch_official_notice(self, url: str) -> dict[str, Any]:
        """Fetch one user-provided official page with strict domain and size checks."""
        if len(url) > 2048:
            return {"error": "官方来源链接过长。"}
        try:
            url = _validate_public_official_url(url)
        except ValueError as exc:
            return {"error": str(exc), "url": url}
        opener = urllib.request.build_opener(_OfficialRedirectHandler())
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "AwesomeStudentAIProposalAgent/0.1 (official notice reader)"},
        )
        try:
            with opener.open(request, timeout=12) as response:
                content_type = response.headers.get_content_type()
                body = response.read(5 * 1024 * 1024 + 1)
                final_url = response.geturl()
        except Exception as exc:
            return {"error": f"读取官方页面失败：{exc}", "url": url}
        if len(body) > 5 * 1024 * 1024:
            return {"error": "页面超过 5 MB，无法作为来源读取。", "url": final_url}
        try:
            _validate_public_official_url(final_url)
        except ValueError as exc:
            return {"error": str(exc), "url": final_url}
        if content_type == "application/pdf":
            from .documents import extract_file

            filename = Path(urllib.parse.urlparse(final_url).path).name or "official-notice.pdf"
            extraction = extract_file(filename if filename.lower().endswith(".pdf") else "official-notice.pdf", body)
            content = extraction.text
            warning = extraction.warning
            title = filename
            published_at = ""
        elif content_type in {"text/html", "application/xhtml+xml"}:
            encoding = "utf-8"
            charset = re.search(r"charset=([\w-]+)", response.headers.get("Content-Type", ""), re.I)
            if charset:
                encoding = charset.group(1)
            decoded = body.decode(encoding, errors="replace")
            parser = _OfficialPageParser()
            parser.feed(decoded)
            title = " ".join(parser.title_parts).strip()[:300] or final_url
            content = re.sub(r"\s+", " ", "\n".join(parser.parts)).strip()
            warning = ""
            published_at = parser.published_at
        else:
            return {
                "error": f"暂不支持该官方页面类型：{content_type}",
                "url": final_url,
            }
        return {
            "success": bool(content),
            "title": title,
            "url": final_url,
            "content": content[:20000],
            "source_domain": urllib.parse.urlparse(final_url).hostname,
            "published_at": published_at,
            "retrieved_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "warning": warning or "页面内容来自公开官方域名；请核对通知年份、适用范围和附件。",
        }

    def save_section(self, project_id: str, section_id: str, content: str) -> dict[str, Any]:
        project = self.store.get_project(project_id)
        if not project:
            return {"error": "找不到这个项目。"}
        if not section_id or len(section_id) > 80:
            return {"error": "章节标识无效。"}
        sections = dict(project["sections"])
        sections[section_id] = content[:30000]
        self.store.update_project(project_id, sections=sections)
        return {"success": True, "section_id": section_id, "character_count": len(content)}

    def save_project_fact(
        self,
        project_id: str,
        key: str,
        value: str,
        source_quote: str,
    ) -> dict[str, Any]:
        project = self.store.get_project(project_id)
        if not project:
            return {"error": "找不到这个项目。"}
        if not valid_fact_key(key):
            return {"error": "字段标识无效。请使用小写英文字母、数字和下划线。"}
        quote = source_quote.strip()
        if len(quote) < 4:
            return {"error": "请提供可核验的原文依据。"}
        if value.strip() != quote:
            return {
                "error": "保存失败：为避免摘要改变事实，自动提取字段必须与原文逐字一致；可请学生在事实面板手动修改。"
            }
        supported = False
        user_messages = [m["content"] for m in self.store.messages(project_id) if m["role"] == "user"]
        last_user = user_messages[-1] if user_messages else ""
        confirmation = last_user.strip().lower().strip("。.!！?？ ")
        confirmed_words = {
            "确认", "我确认", "确认无误", "是", "是的", "对", "没错", "正确",
            "可以", "确定", "信息正确", "我确认以上信息",
        }
        explicit_confirmation = confirmation in confirmed_words
        if not explicit_confirmation:
            return {
                "pending_confirmation": True,
                "key": key,
                "proposed_value": value.strip()[:2000],
                "source_quote": quote[:600],
                "message": "事实尚未保存。请先把整理结果复述给学生，并等待学生明确回复“确认/正确/是”等。",
            }
        if any(quote in message for message in user_messages):
            supported = True
        if not supported:
            for doc in self.store.list_documents(project_id):
                if doc["confirmed"] and quote in doc["extracted_text"]:
                    supported = True
                    break
        if not supported:
            return {
                "error": "保存失败：引用依据必须逐字来自学生本轮输入或已确认的项目材料。请先让学生确认或补充来源。"
            }
        value_numbers = re.findall(r"\d+(?:\.\d+)?", value)
        quote_numbers = re.findall(r"\d+(?:\.\d+)?", quote)
        if any(number not in quote_numbers for number in value_numbers):
            return {
                "error": "保存失败：事实中的数字与原文依据不一致，请重新核对。",
                "value_numbers": value_numbers,
                "source_numbers": quote_numbers,
            }
        state = dict(project["state"])
        facts = dict(state.get("confirmed_facts", {}))
        fact_sources = dict(state.get("fact_sources", {}))
        facts[key] = value.strip()[:2000]
        fact_sources[key] = quote[:600]
        state["confirmed_facts"] = facts
        state["fact_sources"] = fact_sources
        state[key] = facts[key]
        self.store.update_project(project_id, state=state)
        return {"success": True, "key": key, "value": facts[key], "source_quote": fact_sources[key]}

    def validate_project(self, project_id: str) -> dict[str, Any]:
        project = self.store.get_project(project_id)
        if not project:
            return {"error": "找不到这个项目。"}
        state = project["state"]
        sections = project["sections"]
        documents = self.store.list_documents(project_id)
        is_innovation = str(state.get("skill_id", "innovation-research")) == "innovation-research"
        skill = registry.get(str(state.get("skill_id", "innovation-research")))
        photo_relevant = is_innovation or (skill or {}).get("category") in {
            "research", "competition", "practice"
        }
        required_facts = (
            {
                "problem": "待补充：要解决的具体问题",
                "target_user": "待补充：服务对象或应用场景",
                "method": "待补充：拟采用的方法",
                "foundation": "待补充：现有基础或可用资源",
            }
            if is_innovation
            else {}
        )
        missing = [
            {"field": key, "label": label}
            for key, label in required_facts.items()
            if not str(state.get(key, state.get("confirmed_facts", {}).get(key, ""))).strip()
        ]
        pending_ocr = [
            d["original_name"]
            for d in documents
            if d["kind"] != "template" and not d["confirmed"]
        ]
        low_confidence = [
            {"name": d["original_name"], "count": d["low_confidence_count"]}
            for d in documents
            if d["low_confidence_count"] and d["kind"] != "template"
        ]
        photos = [d for d in documents if d["kind"] == "photo"]
        section_count = len([s for s in sections.values() if str(s).strip()])
        missing_sections = [
            item.get("title", item.get("id", "章节"))
            for item in project["outline"]
            if not str(sections.get(item.get("id", ""), "")).strip()
        ]
        consistency_warnings = []
        known_source_names = {
            document["original_name"].casefold()
            for document in documents
            if document["confirmed"] and document["kind"] != "template"
        }
        confirmed_refs = list(state.get("references", [])) + list(state.get("official_sources", []))
        for reference in confirmed_refs:
            if isinstance(reference, dict):
                for value in (reference.get("title"), reference.get("doi"), reference.get("url")):
                    if value:
                        known_source_names.add(str(value).casefold())
        citation_warnings = []
        for section_id, content in sections.items():
            for source_name in re.findall(r"\[来源[：:]\s*([^\],，]+)", str(content)):
                source_name = source_name.strip().casefold()
                if source_name and not any(source_name in known for known in known_source_names):
                    citation_warnings.append(
                        f"章节“{section_id}”的来源标记“{source_name}”未匹配到已确认材料或文献。"
                    )
        consistency_warnings.extend(citation_warnings)
        budget = str(state.get("budget", "")).strip()
        budget_section = " ".join(
            str(value)
            for key, value in sections.items()
            if "budget" in key.lower() or "预算" in key
        )
        budget_numbers = set(re.findall(r"\d+(?:\.\d+)?", budget))
        total_budget_pattern = re.compile(
            r"(?:经费预算合计|预算合计|总预算|预算总额|申请经费|项目总经费|经费总额)"
            r"[^\n\d]{0,24}([\d,]+(?:\.\d+)?)\s*(万元|万|元)?"
        )
        section_numbers = {
            match.group(1).replace(",", "")
            for match in total_budget_pattern.finditer(budget_section)
        }
        if budget_numbers and section_numbers and not budget_numbers.intersection(section_numbers):
            consistency_warnings.append(
                f"预算信息可能不一致：项目事实为 {budget}，预算章节出现的数字为 {', '.join(sorted(section_numbers))}。"
            )
        if len(budget_numbers) > 1:
            consistency_warnings.append("项目基本信息中的预算含多个不同数字，请核对。")
        source_budgets: list[dict[str, str]] = []
        budget_pattern = re.compile(
            r"(?:经费预算合计|预算合计|总预算|预算总额|申请经费|项目总经费|经费总额)"
            r"[^\n\d]{0,24}"
            r"([\d,]+(?:\.\d+)?)\s*(万元|万|元)?"
        )
        for document in documents:
            if document["kind"] == "template" or not document["confirmed"]:
                continue
            for match in budget_pattern.finditer(document["extracted_text"]):
                number = float(match.group(1).replace(",", ""))
                if match.group(2) in {"万元", "万"}:
                    number *= 10000
                source_budgets.append(
                    {
                        "name": document["original_name"],
                        "amount": str(int(number) if number.is_integer() else number),
                        "context": match.group(0).strip()[:100],
                    }
                )
        observed_budget_values = {item["amount"] for item in source_budgets}
        if len(observed_budget_values) > 1:
            details = "；".join(f"{item['name']}：{item['context']}" for item in source_budgets[:5])
            consistency_warnings.append(f"已确认材料中出现多个预算金额，请学生核对：{details}")
        if budget_numbers and observed_budget_values and not any(
            value in observed_budget_values for value in budget_numbers
        ):
            consistency_warnings.append(
                f"项目预算“{budget}”与已确认材料中的金额不一致：{', '.join(sorted(observed_budget_values))}。"
            )
        return {
            "passed": (
                not missing
                and not pending_ocr
                and not low_confidence
                and not missing_sections
                and not consistency_warnings
            ),
            "missing_facts": missing,
            "unconfirmed_documents": pending_ocr,
            "low_confidence_ocr": low_confidence,
            "missing_sections": missing_sections,
            "consistency_warnings": consistency_warnings,
            "source_citation_warnings": citation_warnings,
            "budget_evidence": source_budgets,
            "section_count": section_count,
            "photo_notice": (
                "已上传项目照片。请确认照片与说明对应。"
                if photos
                else (
                    "待补充：如该赛道要求实践/项目照片，请上传真实图片；不会生成假照片。"
                    if photo_relevant
                    else "当前赛道通常不要求项目照片。"
                )
            ),
            "draft_notice": "材料不全仍可导出草稿；缺失项必须标注“待补充”，不得作为可直接提交的正式材料。",
            "automatic_review": "仅运行事实缺失、来源、占位和数字一致性等基础检查；专家式评审需用户主动选择。",
            "validation_scope": (
                "大创创新训练专用事实检查"
                if is_innovation
                else "通用完整性检查；赛道专属要求以当前 Skill 和学校通知为准"
            ),
        }

    def save_diagram(
        self,
        project_id: str,
        title: str,
        nodes: list[str],
        diagram_id: str = "",
    ) -> dict[str, Any]:
        project = self.store.get_project(project_id)
        if not project:
            return {"error": "找不到这个项目。"}
        clean_nodes = [str(node).strip()[:80] for node in nodes if str(node).strip()][:12]
        if len(clean_nodes) < 2:
            return {"error": "一张流程图至少需要两个步骤。"}
        diagrams = list(project["diagrams"])
        diagram_id = (
            re.sub(r"[^a-zA-Z0-9_-]", "_", diagram_id)[:40]
            if diagram_id
            else re.sub(r"[^a-zA-Z0-9_-]", "_", title)[:40]
        ) or "diagram"
        preview_path = self.store.files_dir / project_id / f"{diagram_id}.png"
        try:
            import sys

            if str(ROOT) not in sys.path:
                sys.path.insert(0, str(ROOT))
            from utils.figgen import render_flowchart

            rendered = render_flowchart(clean_nodes, out_path=str(preview_path))
        except Exception:
            rendered = None
        item = {
            "id": diagram_id,
            "title": title[:100],
            "nodes": clean_nodes,
            "preview": str(rendered) if rendered else "",
        }
        diagrams = [d for d in diagrams if d.get("id") != diagram_id]
        diagrams.append(item)
        self.store.update_project(project_id, diagrams=diagrams)
        return {
            "success": True,
            "diagram": item,
            "warning": "" if rendered else "图表渲染依赖或中文字体不可用；流程节点已保存，Word 中将附可编辑步骤。",
        }

    def export_docx(self, project_id: str) -> dict[str, Any]:
        project = self.store.get_project(project_id)
        if not project:
            return {"success": False, "error": "找不到这个项目。"}
        from .exporter import export_project

        output = self.store.files_dir / project_id / "申报书草稿.docx"
        return export_project(self.store, project_id, output)

    def simulate_review(self, project_id: str) -> dict[str, Any]:
        project = self.store.get_project(project_id)
        if not project:
            return {"error": "找不到这个项目。"}
        text_parts = []
        for section in project["outline"]:
            section_id = section.get("id", "")
            content = str(project["sections"].get(section_id, "")).strip()
            if content:
                text_parts.append(f"{section.get('title', section_id)}\n{content}")
        review_text = "\n\n".join(text_parts)
        if not review_text:
            return {"error": "请先保存至少一章草稿，再选择模拟评审。"}
        script = ROOT / "utils" / "review_simulator.py"
        temp_path = ""
        try:
            with tempfile.NamedTemporaryFile(
                "w", suffix=".txt", prefix="proposal-review-", delete=False, encoding="utf-8"
            ) as text_file:
                text_file.write(review_text[:80000])
                temp_path = text_file.name
            result = subprocess.run(
                [
                    sys.executable,
                    str(script),
                "--skill",
                str(project.get("state", {}).get("skill_id", "innovation-research")).replace("-", "_"),
                    "--json",
                    "--text-file",
                    temp_path,
                ],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                timeout=40,
            )
        except Exception as exc:
            return {"error": f"模拟评审暂不可用：{exc}"}
        finally:
            if temp_path:
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass
        try:
            report = json.loads(result.stdout)
        except json.JSONDecodeError:
            return {
                "error": "评审工具没有返回有效 JSON。",
                "stderr": result.stderr[-2000:],
                "returncode": result.returncode,
            }
        return {
            "success": True,
            "evaluation_passed": bool(report.get("passed", False)),
            "report": report,
            "notice": "这是基于项目内规则的模拟参考，不代表真实评审结果；用户主动选择后才运行。",
        }

    def schemas(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "get_project_state",
                    "description": "读取当前项目已确认的设定和材料状态。",
                    "parameters": {
                        "type": "object",
                        "properties": {"project_id": {"type": "string"}},
                        "required": ["project_id"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_writing_guidance",
                    "description": "按需读取当前项目所选赛道的写作指南或当前章节要求。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "project_id": {"type": "string"},
                            "section": {"type": "string"},
                        },
                        "required": ["project_id"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "search_project_materials",
                    "description": "只在当前项目已由学生确认的上传资料中检索依据，返回文件名和段落/页码。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "project_id": {"type": "string"},
                            "query": {"type": "string"},
                            "top_k": {"type": "integer"},
                        },
                        "required": ["project_id", "query"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "search_papers",
                    "description": "通过 Crossref 查找真实论文元数据。若只有标题/摘要，不得假称读过全文。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string"},
                            "limit": {"type": "integer"},
                        },
                        "required": ["query"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "search_official_notices",
                    "description": "搜索学校/教育主管部门的当前申报通知，只返回 edu.cn / gov.cn 来源。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string"},
                            "school": {"type": "string"},
                        },
                        "required": ["query"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "fetch_official_notice",
                    "description": "读取用户提供的学校/政府官方 HTTPS 通知链接，仅接受 edu.cn/gov.cn 域名。",
                    "parameters": {
                        "type": "object",
                        "properties": {"url": {"type": "string"}},
                        "required": ["url"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "save_section",
                    "description": "保存已经生成或修改的章节草稿。导出前仍需用户确认。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "project_id": {"type": "string"},
                            "section_id": {"type": "string"},
                            "content": {"type": "string"},
                        },
                        "required": ["project_id", "section_id", "content"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "save_project_fact",
                    "description": "仅在学生明确回复确认后保存项目事实；value 和 source_quote 必须逐字一致，且原文来自用户输入或已确认材料。若学生尚未确认，返回待确认状态而不保存。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "project_id": {"type": "string"},
                            "key": {"type": "string", "pattern": "^[a-z][a-z0-9_]{1,63}$"},
                            "value": {"type": "string"},
                            "source_quote": {"type": "string"},
                        },
                        "required": ["project_id", "key", "value", "source_quote"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "validate_project",
                    "description": "导出前检查缺失资料、未确认材料和照片占位。此工具不进行专家评审。",
                    "parameters": {
                        "type": "object",
                        "properties": {"project_id": {"type": "string"}},
                        "required": ["project_id"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "save_diagram",
                    "description": "保存学生确认过的技术路线或进度图节点，并尝试生成可预览的图片。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "project_id": {"type": "string"},
                            "title": {"type": "string"},
                            "nodes": {"type": "array", "items": {"type": "string"}},
                            "diagram_id": {"type": "string"},
                        },
                        "required": ["project_id", "title", "nodes"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "export_docx",
                    "description": "生成当前项目的 Word 草稿。缺失信息需写待补充，不可声称可直接提交。",
                    "parameters": {
                        "type": "object",
                        "properties": {"project_id": {"type": "string"}},
                        "required": ["project_id"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "simulate_review",
                    "description": "用户明确要求模拟评审时，对已保存草稿给出参考性评审，不代表真实评审结论。",
                    "parameters": {
                        "type": "object",
                        "properties": {"project_id": {"type": "string"}},
                        "required": ["project_id"],
                    },
                },
            },
        ]

    def handlers(self) -> dict[str, Callable[..., Any]]:
        return {
            "get_project_state": self.get_project_state,
            "get_writing_guidance": self.get_writing_guidance,
            "search_project_materials": self.search_project_materials,
            "search_papers": self.search_papers,
            "search_official_notices": self.search_official_notices,
            "fetch_official_notice": self.fetch_official_notice,
            "save_section": self.save_section,
            "save_project_fact": self.save_project_fact,
            "validate_project": self.validate_project,
            "save_diagram": self.save_diagram,
            "export_docx": self.export_docx,
            "simulate_review": self.simulate_review,
        }

    def invoke(self, name: str, arguments: dict[str, Any]) -> Any:
        handler = self.handlers().get(name)
        if not handler:
            return {"error": f"未授权的工具：{name}"}
        try:
            return handler(**arguments)
        except TypeError as exc:
            return {"error": f"工具参数不正确：{exc}"}
        except Exception as exc:
            return {"error": f"工具执行失败：{exc}"}
