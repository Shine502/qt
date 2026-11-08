from __future__ import annotations

import csv
import hashlib
import math
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

from .backtest import sma_signals


@dataclass(frozen=True)
class AShareBar:
    date: str
    open: float
    high: float
    low: float
    close: float
    adjusted_close: float


@dataclass(frozen=True)
class CorporateAction:
    ex_date: str
    record_date: str
    cash_dividend_per_share: float
    stock_dividend_ratio: float
    transfer_ratio: float

    def as_dict(self) -> dict[str, str | float]:
        return asdict(self)


@dataclass(frozen=True)
class AShareConfig:
    initial_cash: float = 1_000_000.0
    commission_rate: float = 0.00025
    min_commission: float = 5.0
    slippage_bps: float = 5.0
    lot_size: int = 100


@dataclass(frozen=True)
class Trade:
    date: str
    side: str
    shares: float
    price: float
    notional: float
    commission: float
    stamp_duty: float

    def as_dict(self) -> dict[str, str | float]:
        return asdict(self)


@dataclass(frozen=True)
class AShareBacktestRow:
    date: str
    close: float
    adjusted_close: float
    asset_return: float
    signal: int
    position: int
    turnover: float
    net_return: float
    equity: float
    open: float
    cash: float
    shares: float
    dividend_cash: float
    trade_notional: float
    fees: float


def _read_csv(path: str | Path) -> tuple[list[dict[str, str]], str]:
    source = Path(path)
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    with source.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError(f"CSV header is missing: {source}")
        return list(reader), digest


def _value(row: dict[str, str], *names: str) -> str:
    for name in names:
        if name in row:
            return (row[name] or "").strip()
    raise ValueError("missing required field: " + "/".join(names))


def _date(value: str) -> str:
    try:
        if len(value) == 8 and value.isdigit():
            return date(int(value[:4]), int(value[4:6]), int(value[6:])).isoformat()
        return date.fromisoformat(value).isoformat()
    except ValueError as error:
        raise ValueError(f"invalid date: {value}") from error


def _number(value: str, field: str, *, positive: bool = True) -> float:
    try:
        number = float(value)
    except ValueError as error:
        raise ValueError(f"invalid {field}: {value}") from error
    if not math.isfinite(number) or (number <= 0 if positive else number < 0):
        rule = "finite and positive" if positive else "finite and non-negative"
        raise ValueError(f"{field} must be {rule}: {value}")
    return number


def _price_rows(path: str | Path) -> tuple[dict[str, dict[str, float]], str, list[str]]:
    rows, digest = _read_csv(path)
    result: dict[str, dict[str, float]] = {}
    dates: list[str] = []
    previous: str | None = None
    for line_number, row in enumerate(rows, start=2):
        try:
            current = _date(_value(row, "date", "time"))
            values = {
                field: _number(_value(row, field), field)
                for field in ("open", "high", "low", "close")
            }
        except ValueError as error:
            raise ValueError(f"{path}: line {line_number}: {error}") from error
        if previous is not None and current <= previous:
            raise ValueError(f"{path}: dates must be unique and strictly increasing at line {line_number}")
        if values["high"] < max(values["open"], values["close"], values["low"]):
            raise ValueError(f"{path}: invalid high price at line {line_number}")
        if values["low"] > min(values["open"], values["close"], values["high"]):
            raise ValueError(f"{path}: invalid low price at line {line_number}")
        result[current] = values
        dates.append(current)
        previous = current
    if not rows:
        raise ValueError(f"CSV contains no price rows: {path}")
    return result, digest, dates


def load_a_share_data(
    raw_path: str | Path,
    adjusted_path: str | Path,
    events_path: str | Path,
) -> tuple[list[AShareBar], list[CorporateAction], dict[str, str]]:
    raw, raw_digest, dates = _price_rows(raw_path)
    adjusted, adjusted_digest, adjusted_dates = _price_rows(adjusted_path)
    if dates != adjusted_dates:
        raise ValueError("raw and adjusted price dates must match exactly")

    event_rows, events_digest = _read_csv(events_path)
    actions: list[CorporateAction] = []
    seen_events: set[str] = set()
    for line_number, row in enumerate(event_rows, start=2):
        try:
            ex_date = _date(_value(row, "ex_date"))
            record_date = _date(_value(row, "record_date"))
            action = CorporateAction(
                ex_date=ex_date,
                record_date=record_date,
                cash_dividend_per_share=_number(
                    _value(row, "cash_dividend_per_share"),
                    "cash_dividend_per_share",
                    positive=False,
                ),
                stock_dividend_ratio=_number(
                    _value(row, "stock_dividend_ratio"),
                    "stock_dividend_ratio",
                    positive=False,
                ),
                transfer_ratio=_number(
                    _value(row, "transfer_ratio"), "transfer_ratio", positive=False
                ),
            )
        except ValueError as error:
            raise ValueError(f"{events_path}: line {line_number}: {error}") from error
        if ex_date in seen_events:
            raise ValueError(f"duplicate corporate action ex_date: {ex_date}")
        if record_date >= ex_date:
            raise ValueError(f"record_date must precede ex_date: {ex_date}")
        seen_events.add(ex_date)
        if dates[0] <= ex_date <= dates[-1]:
            if ex_date not in raw:
                raise ValueError(f"corporate action ex_date is not a price date: {ex_date}")
            actions.append(action)
    actions.sort(key=lambda item: item.ex_date)
    bars = [
        AShareBar(
            date=current,
            open=raw[current]["open"],
            high=raw[current]["high"],
            low=raw[current]["low"],
            close=raw[current]["close"],
            adjusted_close=adjusted[current]["close"],
        )
        for current in dates
    ]
    dataset_digest = hashlib.sha256(
        (raw_digest + adjusted_digest + events_digest).encode("ascii")
    ).hexdigest()
    hashes = {
        "raw_sha256": raw_digest,
        "adjusted_sha256": adjusted_digest,
        "events_sha256": events_digest,
        "dataset_sha256": dataset_digest,
    }
    return bars, actions, hashes


def stamp_duty_rate(trade_date: str) -> float:
    return 0.0005 if trade_date >= "2023-08-28" else 0.001


def run_a_share_backtest(
    bars: list[AShareBar],
    actions: list[CorporateAction],
    fast: int = 5,
    slow: int = 20,
    config: AShareConfig | None = None,
    signals: list[int] | None = None,
) -> tuple[list[AShareBacktestRow], list[Trade]]:
    if not bars:
        raise ValueError("at least one price bar is required")
    config = config or AShareConfig()
    numeric_values = (
        config.initial_cash,
        config.commission_rate,
        config.min_commission,
        config.slippage_bps,
    )
    if any(not math.isfinite(value) for value in numeric_values):
        raise ValueError("A-share configuration values must be finite")
    if config.initial_cash <= 0:
        raise ValueError("initial_cash must be positive")
    if config.commission_rate < 0 or config.min_commission < 0 or config.slippage_bps < 0:
        raise ValueError("commission and slippage values must be non-negative")
    if isinstance(config.lot_size, bool) or config.lot_size < 1:
        raise ValueError("lot_size must be a positive integer")

    if signals is None:
        signals = sma_signals([bar.adjusted_close for bar in bars], fast, slow)
    if len(signals) != len(bars) or any(signal not in {0, 1} for signal in signals):
        raise ValueError("signals must contain one 0/1 value per price bar")

    actions_by_date = {action.ex_date: action for action in actions}
    cash = config.initial_cash
    shares = 0.0
    previous_equity = config.initial_cash
    rows: list[AShareBacktestRow] = []
    trades: list[Trade] = []

    for index, bar in enumerate(bars):
        dividend_cash = 0.0
        action = actions_by_date.get(bar.date)
        if action is not None and shares > 0:
            dividend_cash = shares * action.cash_dividend_per_share
            cash += dividend_cash
            shares *= 1.0 + action.stock_dividend_ratio + action.transfer_ratio

        trade_notional = 0.0
        fees = 0.0
        if index > 0:
            target = signals[index - 1]
            if target == 1 and shares == 0:
                price = bar.open * (1.0 + config.slippage_bps / 10_000.0)
                quantity = float(int(cash / (price * config.lot_size)) * config.lot_size)
                while quantity > 0:
                    notional = quantity * price
                    commission = max(notional * config.commission_rate, config.min_commission)
                    if notional + commission <= cash + 1e-9:
                        cash -= notional + commission
                        shares = quantity
                        trade_notional = notional
                        fees = commission
                        trades.append(
                            Trade(bar.date, "BUY", quantity, price, notional, commission, 0.0)
                        )
                        break
                    quantity -= config.lot_size
            elif target == 0 and shares > 0:
                price = bar.open * (1.0 - config.slippage_bps / 10_000.0)
                quantity = shares
                notional = quantity * price
                commission = max(notional * config.commission_rate, config.min_commission)
                duty = notional * stamp_duty_rate(bar.date)
                cash += notional - commission - duty
                shares = 0.0
                trade_notional = notional
                fees = commission + duty
                trades.append(
                    Trade(bar.date, "SELL", quantity, price, notional, commission, duty)
                )

        equity = cash + shares * bar.close
        if equity <= 0 or not math.isfinite(equity):
            raise ValueError(f"invalid portfolio equity on {bar.date}")
        asset_return = 0.0 if index == 0 else bar.close / bars[index - 1].close - 1.0
        net_return = equity / previous_equity - 1.0
        rows.append(
            AShareBacktestRow(
                date=bar.date,
                close=bar.close,
                adjusted_close=bar.adjusted_close,
                asset_return=asset_return,
                signal=signals[index],
                position=int(shares > 0),
                turnover=trade_notional / previous_equity if trade_notional else 0.0,
                net_return=net_return,
                equity=equity,
                open=bar.open,
                cash=cash,
                shares=shares,
                dividend_cash=dividend_cash,
                trade_notional=trade_notional,
                fees=fees,
            )
        )
        previous_equity = equity
    return rows, trades
