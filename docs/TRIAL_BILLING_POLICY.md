# 免费体验与积分计费规则

## 固定分界

用户于本次修复中确认：「截止现在，注册过的就是老用户」。

- 北京时间：**2026-10-18 16:51:47 +08:00**
- UTC：**2026-10-18 08:51:47 +00:00**
- 等于或早于该时间注册：老用户，仅使用积分；免费次数归零，积分及积分流水不变。
- 晚于该时间注册：符合原有邮箱/注册风控规则的新用户，总共获得 3 次免费对话。
- 发生充值/卡密积分入账后：永久使用积分，尚未使用的免费次数不再适用。
- 积分用尽不重新赠送免费次数；重新登录、刷新、新建项目均不重置次数。
- 失败免费调用恢复本次占用；充值前发起、充值后才失败的调用不得恢复免费资格。
- 失败付费调用按原账本流程退还该请求的预留，不调整其它请求及其它账号。
- BYOK / Ollama 仍保持独立，不扣平台免费次数或积分。

云端只使用 Auth 验证接口返回的 `created_at` 与数据库 `auth.users.created_at` 判断注册时间，
不信任浏览器传入的字段、用户可编辑的 metadata，或较晚创建的钱包时间。
缺少钱包或注册时间时按无免费资格处理，不自动制造 3 次免费。

## 代码与数据库约束

- `server/proposal/billing_policy.py`：固定时间、账号资格、对外可见免费次数。
- `server/proposal/storage.py`：本地 SQLite 同等规则；原子扣次与付款后的自动清零。
- `server/proposal/supabase_store.py`：云端双重校验，缺失记录不虚构免费次数。
- `20261018085406_workbench_registration_trial_cutoff.sql`：
  - 仅调整老用户/已入账用户的免费次数，不变更任何货币字段；
  - 充值防护触发器覆盖所有修改同一钱包的付款/卡密路径；
  - 新注册触发器只发放一次；复用已有注册触发器，不重复注册；
  - 免费扣次和恢复接口同时检查注册时间、积分历史；
  - 原始写接口仅服务端可调用；浏览器不能绕过后端身份和服务端能力密钥校验。

网络通道与计费解耦：免费与付费平台请求都使用平台专用传输配置，BYOK 不继承平台源站固定配置。

## 验证

```bash
.venv/bin/python -m pytest tests -q
RUN_POSTGRES_POLICY_TESTS=1 .venv/bin/python -m pytest tests/test_trial_policy_postgres.py -q
```

PostgreSQL 测试只使用本机已有的 `postgres:15-alpine` 镜像和隔离、无对外端口的临时容器：
覆盖真实触发器、老用户积分保持不变、三次并发扣减、先充值再失败、RLS、
匿名/跨用户 RPC 拒绝、已有/缺失注册触发器，以及重复执行迁移不重置额度。
默认不连接、不改写生产数据库。

## 发布顺序

1. 按协作守则在开发分支提测、确认代码及数据库测试通过。
2. 在生产部署前审查迁移，确认上述时间与业务口径一致。
3. 应用数据库迁移，再发布后端。旧后端兼容新数据库返回的 `-1`（非免费用户）。
4. 检查老用户剩余免费次数为 0，逐账号核对积分字段未变；检查新用户仅获得 3 次。
5. 检查 Supabase advisors；原始免费次数写接口不应再向匿名或普通登录用户开放：
   [SECURITY DEFINER 权限检查](https://supabase.com/docs/guides/database/database-linter?lint=0028_anon_security_definer_function_executable)、
   [search_path 检查](https://supabase.com/docs/guides/database/database-linter?lint=0011_function_search_path_mutable)。

后端回滚不能重新发放免费次数。数据库规则保留，避免恢复旧版的全员赠送漏洞。
