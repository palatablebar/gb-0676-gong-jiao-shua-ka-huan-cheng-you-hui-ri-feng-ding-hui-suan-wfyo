# 接口

模块GET使用仓内样例，模块POST可传csv或rows与context，直接计算当前规则。/api/runs使用完整流水线并原子保存。每个阶段返回rows、quarantine、metrics；后续阶段还返回累计隔离。/api/upload接收multipart文件file。/api/runs/<id>/archive只导出一份带清单与证据的CSV（含 daily_ledger 行）。

## 方向规则与回退

`POST /api/runs` 的 `parameters` 支持 `direction_mode`（`both`/`feeder`）与 `feeder_links`（`[[支线,主干线]]`）。方向规则非法（`BAD_DIRECTION_RULE`）时不写新批次，响应 200 并携带 `fallback` 对象（`active`、`code`、`message`、`reused_run_id`、`rejected_parameters`），载荷为最近一次完整旧版日账；无历史批次时回退为 422 错误。M5 预览接口 `/api/discounts` 无历史可沿用，直接返回 422。卡日账落库于 `daily_ledgers` 表，`(run_id,card,business_day)` 唯一，重跑不新增占额。
