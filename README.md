# QT Quant CN

一个可安装的 Kimi Code 离线量化研究插件：本地 CSV 数据校验、双均线回测、训练/测试切分、风险门禁、候选策略晋级比较，以及完整状态与结果留痕。**不连接券商，不执行实盘交易。**

## 安装与入口

```text
/plugins install <本仓库路径>
/reload
/qt:start --data tests/fixtures/prices.csv
/qt:evo --data tests/fixtures/prices.csv --baseline <start-run>/result.json --fast 3 --slow 15
```

也可显式调用 `/skill:qt:start` 和 `/skill:qt:evo`。两个 lead 与六个 specialist 位于 `agents/`，由工作流按需编排。

## 确定性控制器

仅依赖 Python 标准库，可直接运行：

```bash
python scripts/qt.py validate
python scripts/qt.py start --data tests/fixtures/prices.csv --output .qt/runs
python scripts/qt.py evo --data tests/fixtures/prices.csv --baseline .qt/runs/<run-id>/result.json --fast 3 --slow 15
python scripts/qt.py status --run .qt/runs/<run-id>
python scripts/check.py
```

`start`/`evo` 退出码：0 为通过，2 为门禁拒绝，1 为输入或执行错误。每次运行生成独立目录：

- `result.json`：参数、数据哈希、训练/测试指标、门禁和决定。
- `equity_curve.csv`：逐日信号、仓位、费用、净收益和净值。
- `state.json`：状态机及转换历史。

`evo` 只输出本次候选是否通过，不修改基线。默认阈值见 `references/policies/default.json`，指标定义见 `references/data_contract.md`。测试 fixture 是合成数据，结果不代表真实投资表现。

## 目录

```text
kimi.plugin.json
commands/{start,evo}.md
skills/{start,evo}/SKILL.md
agents/                         # 2 leads + 6 specialists
references/{schemas,policies}/  # 结果 schema、门禁策略与契约
runtime/quant_cn/               # 状态机、回测、数据与数值门禁
scripts/{qt,check}.py           # 控制器与测试入口
tests/                          # 单元、回归、CLI 端到端测试
```
