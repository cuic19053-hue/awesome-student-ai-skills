# 已授权范文审查目录

当前没有已审核的真实历史范文。不得把仓库合成演示、获奖名单或公开网页中的个人作品冒充授权范文。

只有在取得允许公开再分发的权利证据、完成作者和所有个人信息去标识化、完成独立人工复核后，才能把最小必要的 Markdown/TXT 摘录放入本目录，并在 `../example_sources.json` 登记。来源必须注明原始来源、授权证据、学校、年份、适用范围和文件哈希；审核编号不得包含姓名、证件号或私有合同链接。范文只作为结构和论证方式参考，不得将范文成绩、经历、数据或成果写成当前用户事实。

未取得公开再分发许可的材料，应保留在用户各自的私有项目中，不得放在此目录或公共知识库。

## 审核登记格式

`../example_sources.json` 的 `sources` 可包含尚未批准的草稿（`approved: false`，系统忽略）。只有批准的记录才会校验并入库。示意字段如下；`source_sha256` 是原始公开作品字节的哈希，`excerpt_sha256` 是本目录去标识化摘录的哈希：

```json
{
  "id": "example:unique-id",
  "skill_id": "innovation-research",
  "kind": "example",
  "title": "去标识化范文标题",
  "source_url": "https://example.edu.cn/public-example",
  "rights_evidence_url": "https://example.edu.cn/public-license",
  "rights_review_status": "no_conflict",
  "rights_resolution_url": "",
  "license": "经核验允许公开再分发的许可证",
  "attribution": "许可证要求的公开作者署名及来源说明",
  "approval_reference": "review-opaque-id",
  "approved": true,
  "privacy_reviewed": true,
  "structure_reviewed": true,
  "public_redistribution": true,
  "example_match_type": "direct",
  "school": "适用学校",
  "application_year": 2026,
  "variant": "",
  "restrictions": {},
  "scope": "适用对象及已知局限",
  "verified_at": "2026-10-27",
  "source_sha256": "原始文件的64位十六进制哈希",
  "excerpt_path": "sample.md",
  "excerpt_sha256": "去标识化摘录的64位十六进制哈希",
  "example_structure": "经过人工审查的纯结构摘要，不含人物项目成果或数字"
}
```

`rights_review_status` 只能在人工核验后设为 `no_conflict` 或 `resolved`；后者必须提供公开的 `rights_resolution_url`。许可声明和原文保密条款存在未解决冲突时不得入库。`example_match_type` 使用 `direct` 表示有证据属于该赛道，或使用 `cross_track` 明确标记跨赛道参考；不能把比赛商业计划书冒充大创申报书。公开作者署名与许可信息保留在来源元数据中，以满足授权要求；摘录正文仍须去标识化。若授权要求署名与隐私承诺无法兼容，不得入库。`example_structure` 是给写作模型的唯一范文内容；具体摘录仅向用户展示，不能被作为用户事实喂给模型。历史范文默认不检索，只有用户明确选择参考时才会跨学校、跨年份召回，并保留原始学校、年份和类型。系统会检查常见电话、邮箱和身份证号，但无法可靠识别姓名、机构、隐私及事实，**不能代替人工脱敏与授权审查**。任何审核字段必须有真实证据，不得为凑覆盖率填假值。
