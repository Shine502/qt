---
name: start
description: 运行本地 CSV 双均线回测，执行数值风险门禁并保存完整审计产物
type: flow
whenToUse: 用户通过 /qt:start 启动量化研究或要求运行基线回测
disableModelInvocation: true
---

你是量化研究工作流编排器。把完整任务交给 `research-lead`，并提供下面的原始参数及约束：

$ARGUMENTS

要求 lead 按以下契约执行：
1. 输入必须是包含 `date,close` 的本地 CSV；缺少数据路径时向用户询问，不得编造行情。
2. 将参数映射为 `python ${KIMI_SKILL_DIR}/../../scripts/qt.py start --data <CSV> [--fast N] [--slow N] [--fee-bps X] [--output DIR] [--policy JSON]`。
3. 需要分工时仅委派 `data-specialist`、`strategy-specialist`、`risk-specialist`、`backtest-specialist`、`validation-specialist`、`report-specialist`。简单运行无需为了分工而分工。
4. 退出码 0 表示通过，2 表示被门禁拒绝，1 表示执行错误。拒绝和错误都必须如实报告。
5. 最终给出 run 目录、通过状态、测试集收益/Sharpe/最大回撤及失败原因；明确结果仅供研究，不构成投资建议。
