# 模型交互记录

平台付费模型调用会保存一条与 `request_id` 对应的交互记录，包含最近一条用户可见输入、模型文字回复、模型名、项目、状态和时间。该 ID 可关联 `workbench_usage_events` 账单流水。

- 普通项目聊天仍保存在 `messages`；本记录补充章节生成、图片生成等非聊天调用。
- 不保存系统提示词、API 凭据、模型内部推理或图片二进制。常见密钥格式在写入前会脱敏。
- 项目所有者可通过 RLS 和 `GET /api/projects/{project_id}/model-interactions` 读取本项目记录；项目删除时交互记录随之删除。
- `started` 表示已预留并开始调用，`completed` 表示拿到模型回复，`failed` 表示确定失败，`unknown` 表示上游结果未确认。计费是否结算仍以独立账本为准。

生产启用前，先应用 `20261113090000_workbench_model_interactions.sql`，再发布应用代码。
