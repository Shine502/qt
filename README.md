# QT Quant CN

一个可安装的 Kimi Code 量化研究插件：通过 Kimi Datasource 获取并缓存真实行情，或使用本地 CSV；运行双均线回测、买入持有对照、训练/验证/测试切分、风险门禁和候选策略比较，并保存完整审计产物。**不连接券商，不执行实盘交易。**

## 安装与入口

```text
/plugins install <本仓库路径>
/reload
/qt:start --data tests/fixtures/prices.csv
/qt:evo --data tests/fixtures/prices.csv --baseline <start-run>/result.json --fast 3 --slow 15
```

也可显式调用 `/skill:qt:start` 和 `/skill:qt:evo`。两个 lead 与六个 specialist 位于 `agents/`，由工作流按需编排。

真实 A 股研究可通过 `/qt:start --symbol 600519.SH --start-date 2023-01-01 --end-date 2025-12-31` 启动。工作流使用 Kimi Datasource 查询不复权 OHLC、前复权 OHLC 和公司行为，缓存原始文件并核对完整性；Python 控制器本身不直接调用数据服务。

## 确定性控制器

仅依赖 Python 标准库，可直接运行：

```bash
python scripts/qt.py validate
python scripts/qt.py start --data tests/fixtures/prices.csv --output .qt/runs
python scripts/qt.py evo --data tests/fixtures/prices.csv --baseline .qt/runs/<run-id>/result.json --fast 3 --slow 15
python scripts/qt.py status --run .qt/runs/<run-id>
python scripts/check.py
```

A 股精细成交模式需要同时提供不复权行情、前复权行情和规范化公司行为文件：

```bash
python scripts/qt.py start \
  --data .qt/data/provider/600519_2023_2025_none.csv \
  --adjusted-data .qt/data/provider/600519_2023_2025_forward.csv \
  --events .qt/data/600519/events.csv \
  --validation-start 2024-01-01 --test-start 2025-01-01 \
  --data-source "Kimi Datasource" --symbol 600519.SH \
  --output .qt/runs
```

规范化公司行为 CSV 必须包含：

```text
ex_date,record_date,cash_dividend_per_share,stock_dividend_ratio,transfer_ratio
```

A 股模式默认初始资金 100 万元、佣金万 2.5（最低 5 元）、双边滑点各 5 bps、100 股整数倍买入；卖出印花税按日期切换。信号在收盘后生成，下一交易日开盘成交。公司行为在除权除息日开盘前处理。详见 `references/data_contract.md`。

`start`/`evo` 退出码：0 为通过，2 为门禁拒绝，1 为输入或执行错误。每次运行生成独立目录：

- `result.json`：参数、数据哈希、分段指标、门禁、基准和决定。
- `equity_curve.csv`：逐日信号、仓位、现金、持股、费用和净值。
- `state.json`：状态机及转换历史。
- A 股模式另存 `trades.csv`、`benchmark_equity_curve.csv`、`benchmark_trades.csv` 和 `corporate_actions.csv`。

提供验证区间时，`evo` 只根据验证集执行绝对和相对门禁，最终测试集仅用于报告，避免反复针对测试集调参。候选运行不修改基线。默认阈值见 `references/policies/default.json`。测试 fixture 是合成数据，结果不代表真实投资表现。

## 目录

```text
kimi.plugin.json
commands/{start,evo}.md
skills/{start,evo}/SKILL.md
agents/                         # 2 leads + 6 specialists
references/{schemas,policies}/  # 结果 schema、门禁策略与契约
runtime/quant_cn/               # 通用回测、A 股成交、状态机与数值门禁
scripts/{qt,check}.py           # 控制器与测试入口
tests/                          # fixtures、单元、回归与 CLI 端到端测试
```
