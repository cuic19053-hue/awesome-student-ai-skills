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

## 后续边界

此补丁尚未实现跨账号后台定时对账队列、持久的 HTTP 请求租约及重复提交去重。
现有余额查询仍会尝试对账；长期挂起需运维处理，不能声称此类问题不会再发生。
