# 模型用量挂起排查

历史用量 `reserved` / `needs_review` 不再作为整个账号的新请求开关。
每笔新请求仍由数据库事务锁定钱包、检查可用余额并按请求 ID 幂等预留。
**不按记录年龄自动退款**：客户端断开、超时或暂时查不到收据，都不能证明上游没有计费。

## 单笔只读诊断

`POST /api/admin/provider-usage` 使用独立的服务端环境变量
`BILLING_DIAGNOSTIC_TOKEN` 验证 `x-billing-probe-token` 请求头。
未配置时关闭；不接受浏览器 JWT 代替该凭据。凭据不得放进 URL、前端代码或仓库。

请求体仅包含账本中的 `request_id`。服务端只查询已配置的工作台 Key ID，
按完整请求标记匹配收据；只返回固定状态、白名单数字字段和经价格规则验证的费用。
该接口不调用模型、不写账本，也不返回提示词、对话、用户账号或供应商凭据。

- `confirmed`：找到唯一匹配、归属一致且价格校验通过的收据。
- `receipt_not_found`：限定查询窗口内未找到，**不能据此认定失败或退款**。
- `ambiguous_receipts`：匹配多笔，需人工核对，不能只收取其中一笔。
- `invalid_receipt_pricing`：用量字段缺失或价格规则不匹配，不能猜测费用。

处理历史账单时须使用确认后的请求标识及费用，通过已有结算函数完成，
不得直接覆盖钱包余额。接口发布不代表用户对话恢复，必须区分数据库验证、
隔离账号真实模型验证和受影响用户自己的最新请求结果。

## 验证

```sh
.venv/bin/pytest -q
RUN_POSTGRES_POLICY_TESTS=1 .venv/bin/pytest -q tests/test_workbench_reconciliation_postgres.py
```

## 后台对账和告警

现有 GitHub Actions `Production Uptime` 约每五分钟触发一次后台对账，
GitHub 调度可能延迟；不是实时或必达。每次最多依次领取五笔，使用数据库租约和
退避重试，避免多个 Worker 对同一笔重复结算。仅唯一匹配并通过版本价格规则
校验的上游收据可结算；查不到、匹配不唯一、扫描未完成、上游故障均保留预留，
不得根据超时认定失败或退款。已恢复/人工处理的记录不能被旧租约再次更改。

逾期超过一小时或进入 `needs_review` 且已超过一小时的记录触发 Actions
失败告警，同一笔最多六小时提醒一次；实际通知依赖 GitHub Actions 通知设置。
动作失败、凭据缺失或对账 API 不可用也会使对应 Actions 运行失败。运维须检查
失败运行和受保护的诊断接口，不能假定存在短信或即时通知。

部署时需要：

1. 应用 `billing_reconciliation_worker` 数据库迁移，在不暴露原文的情况下
   将现有 `BILLING_DIAGNOSTIC_TOKEN` 的 SHA-256 摘要写入
   `billing_private.worker_capability`；数据库还独立验证 `WORKBENCH_BACKEND_SECRET`。
2. 在 GitHub 仓库的 Actions Secret `BILLING_RECONCILIATION_TOKEN` 中设置同一
   诊断令牌。不要把令牌写入仓库、URL 或日志。
3. 发布 Vercel 代码，再运行一次 `Production Uptime` workflow 并确认 worker
   状态、身份边界和告警。数据库函数不对外暴露原始账单或用户内容。
4. 只有实测后台 worker 工作后，设置并部署 Vercel 环境变量
   `BILLING_BACKGROUND_RECONCILIATION=true`，避免用户读取余额时同步等待上游。
   默认为关闭；关闭并重新部署可恢复原有按用户触发的重试，作为回滚路径。

## 后续边界

后台对账未启用时余额查询仍会尝试该用户的挂起账单；当前按最近五页查上游，如无法证明
完整扫描或超出窗口则保留并告警，不自动扣费或退款。尚未实现持久的 HTTP
请求租约及跨标签页的重复提交去重，也无法保证上游无故障时所有用户都收到回复。
长期缺失的收据仍需按平台人工兜底政策处理。
