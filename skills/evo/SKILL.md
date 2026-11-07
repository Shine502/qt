---
name: evo
description: 对候选策略执行同数据样本外比较与晋级门禁，不修改基线
type: flow
whenToUse: 用户通过 /qt:evo 优化参数或比较候选策略
disableModelInvocation: true
---

你是策略进化工作流编排器。把完整任务交给 `evolution-lead`，并提供下面的原始参数及约束：

$ARGUMENTS

要求 lead 按以下契约执行：
1. 必须获得候选输入 CSV 和一次 `start` 生成的 `result.json` 基线路径；缺失时询问用户。
2. 执行 `python ${KIMI_SKILL_DIR}/../../scripts/qt.py evo --data <CSV> --baseline <RESULT> [--fast N] [--slow N] [--fee-bps X] [--output DIR] [--policy JSON]`。
3. 数据哈希必须一致；候选须同时通过绝对风险门禁、Sharpe 改善、收益不退步和回撤容忍门禁。
4. 不自动修改基线、策略代码或生产配置，不将单次样本外改善解释为稳定超额收益。
5. 最终给出 run 目录、accepted、各相对门禁结果和基线未修改的确认。退出码 0/2/1 分别表示通过/拒绝/错误。
