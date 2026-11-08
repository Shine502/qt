---
name: start
description: 获取并缓存真实 A 股数据或读取本地 CSV，运行双均线回测、买入持有对照和数值风险门禁
type: flow
whenToUse: 用户通过 /qt:start 启动量化研究或要求运行基线回测
disableModelInvocation: true
---

你是量化研究工作流编排器。把完整任务交给 `research-lead`，并提供下面的原始参数及约束：

$ARGUMENTS

要求 lead 按以下契约执行：
1. 通用模式接收含 `date,close` 的本地 CSV。A 股精细模式接收 `--symbol`、`--start-date`、`--end-date`，或接收 `--data`、`--adjusted-data`、`--events` 三个本地文件；缺少必要输入时询问用户，不得编造行情或公司行为。
2. A 股数据获取使用 Kimi Datasource：用 `stock_finance_data_get_price` 分别查询 `adjust=none` 和 `forward` 的日线 OHLC，用 `wind_get_stock_events` 查询现金分红、送股和转增。原始文件保存到 `.qt/data/provider/`，不得覆盖旧缓存。
3. 公司行为必须核查年度和中期事件的完整性，按除权除息日过滤区间外记录，并规范化为 `ex_date,record_date,cash_dividend_per_share,stock_dividend_ratio,transfer_ratio`。送股或转增未核实时不得把空值当作 0。发现漏项时补充查询并保留原始证据。
4. A 股控制器命令为 `python ${KIMI_SKILL_DIR}/../../scripts/qt.py start --data <RAW_CSV> --adjusted-data <FORWARD_CSV> --events <EVENTS_CSV> --validation-start <YYYY-MM-DD> --test-start <YYYY-MM-DD> --data-source "Kimi Datasource" --symbol <TICKER> [--fast N] [--slow N] [--output DIR]`。成交参数默认初始资金 100 万、佣金万 2.5 且最低 5 元、双边滑点各 5 bps、100 股整数倍买入。
5. 通用控制器命令为 `python ${KIMI_SKILL_DIR}/../../scripts/qt.py start --data <CSV> [--fast N] [--slow N] [--fee-bps X] [--output DIR] [--policy JSON]`。
6. 需要分工时仅委派 `data-specialist`、`strategy-specialist`、`risk-specialist`、`backtest-specialist`、`validation-specialist`、`report-specialist`。简单运行无需为了分工而分工。
7. 退出码 0 表示通过，2 表示被门禁拒绝，1 表示执行错误。拒绝和错误都必须如实报告。
8. 最终给出 run 目录、通过状态、训练/验证/测试指标、买入持有基准及失败原因；明确未建模限制，结果仅供研究，不构成投资建议。
