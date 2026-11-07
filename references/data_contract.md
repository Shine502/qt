# 数据与计算契约

## 输入

- UTF-8 CSV，必须含 `date,close` 两列；其他列被忽略。
- 日期使用 ISO `YYYY-MM-DD`，严格递增且不可重复。
- 收盘价必须有限且大于 0。空值、非数字和非有限值直接报错，不自动填充。
- 文件 SHA-256 写入结果；`evo` 要求候选与基线哈希一致。
- 自带 fixture 是 synthetic 数据，不是真实行情。

## 回测

- 频率按日处理，年化常数为 252；不推断交易日历。
- 双均线仅做多或空仓，`fast >= 1`、`slow > fast`。
- 第 t 根收盘产生的信号在第 t+1 根收益区间生效，避免未来函数。
- 仓位变化按 `abs(new_position-old_position) * fee_bps / 10000` 扣费。
- 净收益为 `position * asset_return - transaction_cost`；组合净值为净收益连乘。
- 按时间顺序切分训练/测试段，默认 70%/30%，不随机打乱。测试段信号可使用此前历史作为均线暖机数据。

## 指标

- `total_return = final_equity - 1`。
- `annualized_volatility = population_std(daily_net_return) * sqrt(252)`。
- `sharpe = mean(daily_net_return) / population_std(daily_net_return) * sqrt(252)`，无风险利率为 0；零波动时记 0。
- `max_drawdown = max(1 - equity / historical_peak)`，为非负回撤幅度。
- `orders` 是发生仓位变化的 K 线数，`exposure` 是持有多头仓位的 K 线比例。

所有阈值见 `policies/default.json`。缺失或非有限指标一律不能通过。结果仅供离线研究，不构成投资建议。
