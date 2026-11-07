from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from typing import Iterable, Sequence

TRADING_DAYS = 252


@dataclass(frozen=True)
class Bar:
    date: str
    close: float


@dataclass(frozen=True)
class BacktestRow:
    date: str
    close: float
    asset_return: float
    signal: int
    position: int
    turnover: float
    net_return: float
    equity: float


def sma_signals(closes: Sequence[float], fast: int, slow: int) -> list[int]:
    if fast < 1 or slow <= fast:
        raise ValueError("window constraints: fast >= 1 and slow > fast")
    signals: list[int] = []
    for index in range(len(closes)):
        if index + 1 < slow:
            signals.append(0)
            continue
        fast_mean = statistics.fmean(closes[index - fast + 1 : index + 1])
        slow_mean = statistics.fmean(closes[index - slow + 1 : index + 1])
        signals.append(int(fast_mean > slow_mean))
    return signals


def run_backtest(
    bars: Sequence[Bar], fast: int = 5, slow: int = 20, fee_bps: float = 10.0
) -> list[BacktestRow]:
    if not bars:
        raise ValueError("at least one price bar is required")
    if not math.isfinite(fee_bps) or fee_bps < 0:
        raise ValueError("fee_bps must be a finite non-negative number")
    signals = sma_signals([bar.close for bar in bars], fast, slow)
    rows: list[BacktestRow] = []
    equity = 1.0
    previous_position = 0
    for index, bar in enumerate(bars):
        asset_return = 0.0 if index == 0 else bar.close / bars[index - 1].close - 1.0
        position = 0 if index == 0 else signals[index - 1]
        turnover = abs(position - previous_position)
        net_return = position * asset_return - turnover * fee_bps / 10_000.0
        equity *= 1.0 + net_return
        rows.append(
            BacktestRow(
                date=bar.date,
                close=bar.close,
                asset_return=asset_return,
                signal=signals[index],
                position=position,
                turnover=turnover,
                net_return=net_return,
                equity=equity,
            )
        )
        previous_position = position
    return rows


def calculate_metrics(rows: Iterable[BacktestRow]) -> dict[str, float | int]:
    selected = list(rows)
    if not selected:
        raise ValueError("cannot calculate metrics for an empty period")
    returns = [row.net_return for row in selected]
    equity = 1.0
    peak = 1.0
    max_drawdown = 0.0
    for value in returns:
        equity *= 1.0 + value
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, 1.0 - equity / peak)
    mean_return = statistics.fmean(returns)
    volatility = statistics.pstdev(returns) if len(returns) > 1 else 0.0
    sharpe = mean_return / volatility * math.sqrt(TRADING_DAYS) if volatility > 0 else 0.0
    return {
        "rows": len(selected),
        "total_return": equity - 1.0,
        "annualized_volatility": volatility * math.sqrt(TRADING_DAYS),
        "sharpe": sharpe,
        "max_drawdown": max_drawdown,
        "orders": sum(row.turnover > 0 for row in selected),
        "exposure": statistics.fmean(row.position for row in selected),
    }
