# 数据与计算契约

## 通用 CSV 模式

- UTF-8 CSV，必须含 `date,close` 两列；其他列被忽略。
- 日期使用 ISO `YYYY-MM-DD`，严格递增且不可重复。
- 收盘价必须有限且大于 0。空值、非数字和非有限值直接报错，不自动填充。
- 文件 SHA-256 写入结果；`evo` 要求候选与基线哈希一致。
- 双均线仅做多或空仓，`fast >= 1`、`slow > fast`。
- 第 t 根收盘产生的信号在第 t+1 根收益区间生效。
- 仓位变化按 `abs(new_position-old_position) * fee_bps / 10000` 扣费。
- 未指定验证区间时，按时间顺序进行默认 70%/30% 训练/测试切分，不随机打乱。

## A 股精细成交模式

同时提供以下三个文件才能启用：

1. 不复权日线：必须含 `date,open,high,low,close`，也接受数据源返回的 `time` 日期列和 `YYYYMMDD` 格式。
2. 前复权日线：字段相同，交易日期必须与不复权文件逐行一致；仅其 `close` 用于双均线信号。
3. 规范化公司行为：`ex_date,record_date,cash_dividend_per_share,stock_dividend_ratio,transfer_ratio`。

所有价格必须有限且大于 0；现金分红和股本比例必须有限且非负。公司行为空值、重复除权除息日、登记日不早于除权除息日、除权除息日不是交易日均直接报错。落在行情区间外的公司行为会被过滤，原始文件仍保留并参与数据集哈希。

### 成交与公司行为

- 第 t 日收盘后生成信号，第 t+1 个交易日开盘成交；不会在信号当日按已知收盘价成交。
- 默认初始资金 1,000,000 元，佣金率 0.00025、最低佣金 5 元、双边滑点各 5 bps、买入数量为 100 股整数倍。
- 买入成交价 `open * (1 + slippage_bps / 10000)`；卖出成交价 `open * (1 - slippage_bps / 10000)`。
- 买入数量必须使成交金额和佣金不超过可用现金；资金不足一手时不交易。
- 卖出为全部持仓，佣金为 `max(notional * commission_rate, min_commission)`。
- 卖出印花税：2023-08-28 之前为成交金额的 0.1%，自 2023-08-28 起为 0.05%；买入不收。
- 除权除息日开盘前，按此前持股计入税前现金分红，再按送股和转增比例增加持股；当日新买入不享受该次分红。
- 组合净值按 `cash + shares * raw_close` 计算，日净收益来自相邻交易日组合净值。
- 买入持有基准使用同一成交、费用和公司行为模型，在首个信号后的下一交易日开盘买入。

### 三段评价

同时提供 `--validation-start` 和 `--test-start` 时启用：

- `date < validation_start`：训练集。
- `validation_start <= date < test_start`：验证集。
- `date >= test_start`：最终测试集。
- 三段都必须非空；此前历史可用于均线暖机，但指标只在所属区间计算。
- `evo` 的绝对和相对门禁使用验证集；最终测试集只报告，不参与候选晋级。基线必须包含验证集指标。

## 指标

- `total_return = final_equity / initial_segment_equity - 1`，由区间内日净收益连乘。
- `annualized_volatility = population_std(daily_net_return) * sqrt(252)`。
- `sharpe = mean(daily_net_return) / population_std(daily_net_return) * sqrt(252)`，无风险利率为 0；零波动时记 0。
- `max_drawdown = max(1 - equity / historical_peak)`，为非负回撤幅度。
- `orders` 是发生交易的 K 线数，`exposure` 是持有多头仓位的 K 线比例。

所有阈值见 `policies/default.json`。缺失或非有限指标一律不能通过。A 股模式暂不模拟涨跌停无法成交、停牌期间撮合和分红税；公司行为完整性取决于规范化输入及工作流核查。结果仅供研究，不构成投资建议。
