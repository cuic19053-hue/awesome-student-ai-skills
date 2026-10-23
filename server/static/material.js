/* Pilot UI: all user/project text uses textContent, never injected HTML. */
(() => {
  "use strict";
  let host, data, root, projectId, urls = [], fillPlan;
  const el = (tag, text, cls) => {
    const n = document.createElement(tag);
    if (text !== undefined) n.textContent = text;
    if (cls) n.className = cls;
    return n;
  };
  const active = () => Boolean(host?.state.project?.material?.enabled);
  const path = suffix => `/api/projects/${encodeURIComponent(host.state.project.id)}/material${suffix}`;
  const request = (suffix, method = "GET", body) => host.api(path(suffix), {
    method, ...(body === undefined ? {} : { headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
  });
  function action(text, fn, parent) {
    const button = el("button", text, "button button-small button-secondary");
    button.type = "button";
    button.onclick = async () => {
      button.disabled = true;
      try { await fn(); } catch (e) { host.toast(e.message, true); }
      finally { button.disabled = false; }
    };
    parent.append(button);
    return button;
  }
  function input(parent, label, value = "", multiline = false) {
    const wrap = el("label", label, "material-field");
    const field = el(multiline ? "textarea" : "input");
    field.value = value;
    if (multiline) field.rows = 3;
    wrap.append(field); parent.append(wrap);
    return field;
  }
  function select(parent, label, values) {
    const wrap = el("label", label, "material-field");
    const node = el("select");
    values.forEach(([value, title]) => {
      const option = el("option", title); option.value = value; node.append(option);
    });
    wrap.append(node); parent.append(wrap); return node;
  }
  const jobStatus = { pending: "排队中", running: "执行中", completed: "已完成",
    failed: "失败", cancelled: "已取消", needs_review: "待核对结果与费用" };
  const jobKind = { section: "章节", outline: "候选目录", plan: "配图建议",
    figure: "图表", export: "Word 导出" };
  const jobStep = {
    queued: "排队中", preparing_inputs: "准备项目资料", planning_outline: "整理候选目录",
    planning_figure: "拟定候选配图方案", writing_and_existing_review: "生成本章并按原流程评审",
    model_request: "等待模型响应", draft_saved: "草稿已保存，继续本轮检查",
    drawing: "绘制图表", checking_figure_text: "检查图片文字",
    assembling_document: "组装 Word", rendering_pages: "渲染页面供检查",
    saving_artifacts: "保存下载文件",
  };
  async function blobUrl(url) {
    const headers = {};
    if (host.state.authSession?.access_token) headers.Authorization = `Bearer ${host.state.authSession.access_token}`;
    const response = await fetch(url, { headers });
    if (!response.ok) throw new Error("私有产物读取失败，请检查登录状态");
    const objectUrl = URL.createObjectURL(await response.blob());
    urls.push(objectUrl);
    return objectUrl;
  }
  async function refresh() {
    if (!active()) return;
    const id = host.state.project.id;
    const next = await request("");
    if (host.state.project?.id !== id) return;
    data = next;
    host.state.project.material = data.context;
    host.state.project.material_revision = data.context.revision;
    draw();
  }
  async function mount(config) {
    host = config;
    root = document.querySelector("#materialPilot");
    if (!root) {
      root = el("section", undefined, "material-pilot");
      root.id = "materialPilot";
      document.querySelector("#templateStatus").after(root);
    }
    root.classList.toggle("hidden", !active());
    if (!active()) { projectId = null; data = null; return; }
    projectId = host.state.project.id;
    try { await refresh(); } catch (e) {
      root.replaceChildren(el("p", `大创链路暂不可用：${e.message}`));
    }
  }
  function draw() {
    if (!data || !active()) return;
    urls.forEach(u => URL.revokeObjectURL(u)); urls = [];
    root.replaceChildren();
    const details = el("details"); details.open = true;
    details.append(el("summary", "大创创新训练 · 信息、要求、配图与交付"));
    details.append(el("p", data.worker_ready
      ? "已启用持久任务。付费模型须明确确认；失败不自动重复调用。"
      : "Worker 尚未配置：可整理信息和计划，完整生成与页面检查尚未启用。"));
    action("刷新任务与关联提示", refresh, details);
    const stale = Object.entries(data.context.stale || {});
    for (const [node, reasons] of stale) {
      const row = el("div", `${node} 可能需要更新：${reasons.join("、")}`, "material-warning");
      action("已核对当前版本", async () => {
        await request("/acknowledge", "POST", { revision: data.context.revision, snapshot: data.context.snapshot, nodes: [node] });
        await refresh();
      }, row);
      details.append(row);
    }
    const sources = data.context.sources || [];
    const pending = sources.filter(s => !s.confirmed && s.kind !== "template");
    details.append(el("p", `资料 ${sources.length} 份，待核对 ${pending.length} 份。请在材料区核对 OCR 和来源。`));
    requirementEditor(details);
    planEditor(details);
    const tasks = el("details"); tasks.open = true; tasks.append(el("summary", "任务与交付结果"));
    for (const job of data.jobs || []) {
      const row = el("div", `${jobKind[job.kind] || "材料任务"} · ${job.target || "整份材料"} · ${jobStatus[job.status] || "处理中"} · ${jobStep[job.step] || "处理中"}`, "material-job");
      if (job.error) row.append(el("p", job.error));
      if (job.status !== "completed" && job.result?.partial_content) {
        const partial = el("details"); partial.append(el("summary", "查看已保存草稿（后续检查未完成）"));
        partial.append(el("pre", job.result.partial_content)); row.append(partial);
      }
      if (["pending", "running"].includes(job.status))
        action("取消后续执行", async () => { await request(`/jobs/${job.id}/cancel`, "POST"); await refresh(); }, row);
      if (job.status === "completed") {
        if (!job.result?.applied && job.kind !== "export")
          action("保存结果／保留为备选", async () => {
            await flushEdits();
            const result = await request(`/jobs/${job.id}/apply`, "POST");
            host.toast(result.notice || "结果已保存"); await host.reload(projectId);
          }, row);
        if (job.result?.conflict_status) row.append(el("p", "输入已经变化：结果保留为备选，未覆盖当前内容。"));
        if (job.kind === "section" && job.result?.content) {
          const alternative = el("details"); alternative.append(el("summary", "查看生成正文"));
          alternative.append(el("pre", job.result.content)); row.append(alternative);
        }
        if (job.kind === "plan" && job.result?.plan) {
          const proposed = job.result.plan;
          row.append(el("p", `${proposed.title}：${proposed.nodes.join(" → ")}`));
          action("编辑此配图建议", () => fillPlan(proposed), row);
        }
        if (job.kind === "outline" && job.result?.outline) {
          row.append(el("p", job.result.outline.map(s => s.title).join("；")));
        }
        if (job.kind === "figure") {
          action("查看生成图片", async () => {
            const image = el("img"); image.alt = job.target;
            image.src = await blobUrl(path(`/jobs/${job.id}/files/figure.png`)); row.append(image);
          }, row);
          if (job.result?.asset?.scene_text?.length) {
            row.append(el("p", `请逐字核对场景文字：${job.result.asset.scene_text.join("；")}`));
            action("已逐字核对并确认", async () => {
              if (!confirm("请先查看大图，并确认场景内所有关键文字准确。")) return;
              await request(`/figures/${job.target}/confirm-text`, "POST", {
                revision: data.context.revision, snapshot: data.context.snapshot, nodes: [],
              }); await refresh();
            }, row);
          }
        }
        if (job.kind === "export") {
          const report = job.result.report || {};
          const quality = { failed: "检查发现问题", not_checked: "尚未完成页面检查", needs_review: "需人工核对" };
          row.append(el("p", `排版检查：${quality[report.quality_status] || "未完成"}；模板：${report.template_status === "mapped" ? "已按规则填充，仍需核对" : "待核对"}`));
          row.append(el("p", `内容基础检查：${report.validation?.passed ? "通过基础检查，仍需人工核对" : "仍有缺项或一致性问题"}；图表和模板状态请分别查看，文件可生成不等于可直接提交。`));
          for (const warning of report.warnings || []) row.append(el("p", warning, "material-warning"));
          for (const check of report.checks || []) row.append(el("p", `${check.rule}：${({
            passed: "通过", failed: "失败", not_checked: "未检查", needs_review: "需人工核对",
          })[check.status] || "未完成"} · ${check.detail}`));
          action("下载可编辑 Word 草稿", async () => {
            const link = el("a"); link.href = await blobUrl(path(`/jobs/${job.id}/files/proposal.docx`));
            link.download = "大创创新训练申报书草稿.docx"; link.click();
          }, row);
          action("查看逐页预览", async () => {
            const pages = el("div", undefined, "material-pages"); row.append(pages);
            for (const name of report.pages || []) {
              const image = el("img"); image.alt = name; image.loading = "lazy";
              image.src = await blobUrl(path(`/jobs/${job.id}/files/${name}`)); pages.append(image);
            }
          }, row);
        }
      }
      tasks.append(row);
    }
    details.append(tasks); root.append(details);
  }
  function requirementEditor(parent) {
    const box = el("details"); box.append(el("summary", "适用要求与优先级"));
    box.append(el("p", data.context.requirements.priority.join(" → ")));
    for (const conflict of data.context.requirements.conflicts || [])
      box.append(el("p", `${conflict.key}：${conflict.status === "needs_confirmation" ? "同级冲突，请确认后修改要求" : "按优先级采用：" + conflict.selected.value}`, "material-warning"));
    data.requirements.forEach((rule, index) => {
      const row = el("div", `${rule.key}：${rule.value}（${rule.source}；${rule.confirmed && rule.applicable ? "已确认适用" : "待确认"}）`);
      action("移除", async () => {
        await request("/requirements", "PUT", { revision: data.context.revision, items: data.requirements.filter((_, i) => i !== index) }); await refresh();
      }, row); box.append(row);
    });
    const kind = select(box, "来源类型", [["official", "正式通知／学校模板"], ["user", "我的明确要求"], ["material", "大创规则"], ["example", "参考示例"], ["default", "默认样式"]]);
    const key = select(box, "约束对象", [["word_count", "字数"], ["page_limit", "页数"], ["sections", "章节栏目"], ["font", "字体"], ["format", "版式"], ["content", "内容要求"]]);
    const value = input(box, "具体要求", "", true);
    const source = input(box, "出处／文件名");
    const scope = input(box, "适用学校、年份和范围");
    action("确认这条要求适用并保存", async () => {
      await request("/requirements", "PUT", { revision: data.context.revision, items: [...data.requirements, {
        key: key.value, value: value.value.trim(), source_kind: kind.value, source: source.value.trim(),
        scope: scope.value.trim(), confirmed: true, applicable: true,
      }] }); await refresh();
    }, box);
    parent.append(box);
  }
  function planEditor(parent) {
    const box = el("details"); box.append(el("summary", "图表计划与绘图"));
    box.append(el("p", "流程与架构用程序画；数据图只使用真实确认数据；GPT 生成概念示意。可编辑后确认，不强制每章配图。"));
    data.plans.forEach(plan => {
      const row = el("div", `${plan.title} → ${plan.section_id} · ${plan.renderer}`, "material-job");
      action("编辑", () => { fill(plan); box.open = true; }, row);
      action("确认并生成此图", async () => {
        if (!plan.confirmed) {
          fill(plan);
          box.open = true;
          host.toast("请先核对候选方案，点击下方保存并确认");
          return;
        }
        await submit("figure", plan.id, plan.renderer === "gpt");
      }, row);
      action("移除计划", async () => {
        await request("/plans", "PUT", { revision: data.context.revision, items: data.plans.filter(p => p.id !== plan.id) }); await refresh();
      }, row);
      box.append(row);
    });
    let editingId = null;
    const title = input(box, "图题");
    const section = select(box, "所属章节", host.state.outline.map(s => [s.id, s.title]));
    action("根据已确认资料拟定配图方案", async () => {
      if (!section.value) throw new Error("请先确认目录");
      await refresh();
      await submit("plan", section.value, true);
    }, box);
    const renderer = select(box, "绘图方式", [["svg", "流程／架构（HTML/SVG）"], ["python", "数据图（Python）"], ["gpt", "概念／场景（GPT Image，付费）"], ["overlay", "已有图片追加准确文字（不调用生图模型）"], ["upload", "真实上传照片／素材（不调用模型）"]]);
    const chart = select(box, "数据图类型", [["bar", "柱状图"], ["line", "折线图"], ["gantt", "甘特图"]]);
    const nodes = input(box, "流程节点：每行一个", "", true);
    const edges = input(box, "连接关系：每行“1->2”；留空按节点顺序连接", "", true);
    const method = data.context.planned_items?.method || "";
    if (method) nodes.value = String(method).split(/[；;。\n]+/).filter(Boolean).join("\n");
    const numbers = input(box, "数据：每行“名称,数值”；甘特图为“名称,开始时间,持续时间”", "", true);
    const dataStatus = select(box, "数据性质", [["planned", "计划值"], ["measured", "实测值"]]);
    const source = input(box, "数据或图片来源说明");
    const prompt = input(box, "概念图描述（仅 GPT Image 使用）", "", true);
    const scene = input(box, "必须融入画面的文字：每行一条；普通科研标签请放下面", "", true);
    const overlay = input(box, "程序追加文字：每行一条，放在独立说明区域，不覆盖原图", "", true);
    const base = select(box, "局部排字的原图任务", [["", "不使用"], ...data.jobs.filter(j => j.kind === "figure" && j.status === "completed").map(j => [j.id, `${j.target} · ${j.id.slice(0, 8)}`])]);
    const documentId = select(box, "使用的真实上传图片", [["", "不使用"], ...(host.state.documents || [])
      .filter(d => (d.content_type || "").startsWith("image/")).map(d => [d.id, d.original_name])]);
    function fill(plan) {
      box.open = true;
      editingId = plan.id; title.value = plan.title; section.value = plan.section_id; renderer.value = plan.renderer;
      chart.value = plan.chart === "flow" ? "bar" : plan.chart; nodes.value = plan.nodes.join("\n");
      edges.value = (plan.edges || []).map(e => `${e.source+1}->${e.target+1}`).join("\n");
      numbers.value = plan.labels.map((l, i) => [l, ...(plan.chart === "gantt" ? [plan.starts[i]] : []), plan.values[i]].join(",")).join("\n");
      source.value = plan.source; prompt.value = plan.prompt; scene.value = plan.scene_text.join("\n");
      overlay.value = plan.overlays.map(o => o.text).join("\n"); base.value = plan.base_asset_job;
      dataStatus.value = plan.data_status;
      documentId.value = plan.document_id || "";
      title.scrollIntoView({ block: "center", behavior: "smooth" });
    }
    fillPlan = fill;
    const lines = value => value.split(/\r?\n/).map(v => v.trim()).filter(Boolean);
    action("保存并确认图表计划（不调用模型）", async () => {
      const rows = lines(numbers.value).map(l => l.split(/[,，]/).map(s => s.trim()));
      const spec = {
        id: editingId || `fig_${crypto.randomUUID().replaceAll("-", "").slice(0, 16)}`,
        section_id: section.value, title: title.value.trim(), renderer: renderer.value,
        chart: renderer.value === "svg" ? "flow" : chart.value, nodes: lines(nodes.value),
        edges: lines(edges.value).map(value => {
          const match = value.match(/^(\d+)\s*->\s*(\d+)$/);
          if (!match) throw new Error("连接关系请填写 1->2 这样的编号");
          return { source: Number(match[1])-1, target: Number(match[2])-1 };
        }),
        labels: rows.map(r => r[0]), values: rows.map(r => Number(r.at(-1))),
        starts: chart.value === "gantt" ? rows.map(r => Number(r[1])) : [],
        source: source.value, data_status: dataStatus.value, prompt: prompt.value,
        scene_text: lines(scene.value), overlays: lines(overlay.value).map(text => ({ text })),
        base_asset_job: base.value, confirmed: true, text_confirmed: false,
        document_id: documentId.value,
      };
      await request("/plans", "PUT", { revision: data.context.revision, items: [...data.plans.filter(p => p.id !== spec.id), spec] }); await refresh();
    }, box);
    parent.append(box);
  }
  async function submit(kind, target, paid) {
    if (paid && !confirm((kind === "section" ? "本章沿用现有撰写与评审流程，最多六次模型请求。" :
        kind === "figure" ? "本次生成一张图片。" : "本次调用一次文字模型拟定候选方案。") +
        "平台模型按现有积分规则结算，自定义模型由服务商收费；不自动付费重绘。是否确认？")) return null;
    const job = await request("/jobs", "POST", {
      revision: data.context.revision, kind, target, idempotency_key: crypto.randomUUID(),
      llm_config: paid ? { ...host.state.llmConfig } : null, confirm_paid: Boolean(paid),
    });
    await refresh(); host.toast("任务已保存，刷新页面后仍可查询。");
    return job;
  }
  async function section(sid, editor) {
    const loadedRevision = host.state.project.material_revision;
    const original = editor?.value;
    await refresh();
    if (editor && original !== (host.state.project.sections?.[sid] || "")) {
      if (loadedRevision !== data.context.revision)
        throw new Error("项目已在其他操作中变化，请先保存并核对当前章节，未覆盖您的编辑");
      await host.api(`/api/projects/${projectId}/sections/${sid}`, {
        method: "PUT", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content: original, expected_revision: loadedRevision,
          base_content: host.state.project.sections?.[sid] || "" }),
      });
      host.state.project.sections[sid] = original;
      await refresh();
    }
    const baseRevision = data.context.revision;
    const job = await submit("section", sid, true);
    if (!job) throw new Error("已取消模型调用");
    const id = projectId;
    for (let i = 0; i < 120; i++) {
      await new Promise(resolve => setTimeout(resolve, 2500));
      if (host.state.project?.id !== id) throw new Error("任务继续运行，可返回项目查询");
      const current = await request(`/jobs/${job.id}`);
      if (current.status === "completed") {
        if (editor && editor.value !== original && editor.value !== host.state.project.sections?.[sid]) {
          await host.api(`/api/projects/${id}/sections/${sid}`, { method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ content: editor.value, expected_revision: baseRevision,
              base_content: host.state.project.sections?.[sid] || "" }) });
          host.state.project.sections[sid] = editor.value;
        }
        const result = await request(`/jobs/${job.id}/apply`, "POST");
        await refresh();
        return { ...result, material_applied: true };
      }
      if (["failed", "cancelled", "needs_review"].includes(current.status)) throw new Error(current.error || current.status);
    }
    throw new Error("任务仍在后台执行，请稍后刷新任务列表，不必重复提交");
  }
  async function flushEdits() {
    // Save visible edits before freezing an export snapshot; never discard them by reloading.
    for (const area of document.querySelectorAll(".draft-section textarea")) {
      const sid = area.closest(".draft-section").id.slice("draft-sec-".length);
      if (area.value !== (host.state.project.sections?.[sid] || "")) {
        const result = await host.api(`/api/projects/${projectId}/sections/${sid}`, { method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ content: area.value, expected_revision: host.state.project.material_revision,
            base_content: host.state.project.sections?.[sid] || "" }) });
        host.state.project.material_revision = result.material_revision;
        host.state.project.sections[sid] = area.value;
      }
    }
  }
  async function exportDocument() {
    await flushEdits();
    await refresh(); await submit("export", "", false);
  }
  async function outline() {
    await flushEdits();
    await refresh();
    const job = await submit("outline", "", true);
    if (!job) throw new Error("已取消目录模型调用");
    const id = projectId;
    for (let i = 0; i < 120; i++) {
      await new Promise(resolve => setTimeout(resolve, 2500));
      if (host.state.project?.id !== id) throw new Error("任务继续执行，请返回项目查询");
      const current = await request(`/jobs/${job.id}`);
      if (current.status === "completed") {
        await flushEdits();
        const result = await request(`/jobs/${job.id}/apply`, "POST");
        await refresh();
        return { ...result, warning: result.notice || "目录为候选方案，请核对后确认" };
      }
      if (["failed", "cancelled", "needs_review"].includes(current.status)) throw new Error(current.error || current.status);
    }
    throw new Error("目录仍在后台生成，请在任务区查询");
  }
  window.MaterialPilot = { mount, active, refresh, section, outline, exportDocument, flushEdits, blobUrl };
})();
