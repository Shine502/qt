from __future__ import annotations

import csv
import hashlib
import math
from datetime import date
from pathlib import Path

from .backtest import Bar


def load_bars(path: str | Path) -> tuple[list[Bar], str]:
    source = Path(path)
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    bars: list[Bar] = []
    previous_date: date | None = None
    with source.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or not {"date", "close"}.issubset(reader.fieldnames):
            raise ValueError("CSV header must contain date and close")
        for line_number, row in enumerate(reader, start=2):
            try:
                current_date = date.fromisoformat((row["date"] or "").strip())
                close = float((row["close"] or "").strip())
            except (TypeError, ValueError) as error:
                raise ValueError(f"invalid CSV value at line {line_number}") from error
            if not math.isfinite(close) or close <= 0:
                raise ValueError(f"close must be finite and positive at line {line_number}")
            if previous_date is not None and current_date <= previous_date:
                raise ValueError(f"dates must be unique and strictly increasing at line {line_number}")
            bars.append(Bar(current_date.isoformat(), close))
            previous_date = current_date
    if not bars:
        raise ValueError("CSV contains no price rows")
    return bars, digest
