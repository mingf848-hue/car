from __future__ import annotations

from typing import Any, Dict, Tuple


PNL_KEYS = (
    "pnl",
    "profit",
    "realizedPnl",
    "realizedPnL",
    "netPnl",
    "profitLoss",
    "realizedProfit",
    "realizedProfitLoss",
    "cashPnl",
    "pnlAmount",
)


def _to_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def extract_pnl(raw: Dict[str, Any]) -> Tuple[float, bool, str]:
    for key in PNL_KEYS:
        if key not in raw:
            continue
        value = _to_float(raw.get(key))
        if value is not None:
            return value, True, key
    return 0.0, False, ""
