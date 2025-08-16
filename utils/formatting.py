"""Formatting helpers for trading commands."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from utils.i18n import I18N


__all__ = [
    "format_price_entry",
    "format_price_list",
    "format_route_summary",
    "format_fuel_list",
    "format_alerts_list",
]


# ----- shared small helpers -----

def _shorten(text: str, limit: int = 40) -> str:
    """Shorten long location names."""
    t = text or ""
    return t if len(t) <= limit else t[: limit - 1] + "…"


def _fmt_money(val: Optional[float]) -> str:
    """Format currency value."""
    if val is None:
        return "-"
    return f"{val:,.0f}".replace(",", " ")


# ----- public helpers -----

def format_price_entry(entry: Dict[str, Any], i18n: I18N, lang: str) -> str:
    """Format single price entry."""
    term = _shorten(entry.get("terminal_name") or entry.get("terminal") or "-")
    loc = _shorten(entry.get("location") or entry.get("city") or "-")
    buy = _fmt_money(entry.get("price_buy"))
    sell = _fmt_money(entry.get("price_sell"))
    lbl = i18n.t
    return (
        f"• {term} ({loc}) — {lbl('labels.buy', lang=lang)}: {buy} | "
        f"{lbl('labels.sell', lang=lang)}: {sell}"
    )


def format_price_list(entries: List[Dict[str, Any]], i18n: I18N, lang: str) -> str:
    """Format list of price entries (up to 25)."""
    lines = [format_price_entry(e, i18n, lang) for e in entries[:25]]
    return "\n".join(lines) or "—"


def format_route_summary(route: Dict[str, Any], i18n: I18N, lang: str) -> str:
    """Format trading route summary."""
    frm = _shorten(route.get("from_terminal_name") or route.get("from") or "-")
    to = _shorten(route.get("to_terminal_name") or route.get("to") or "-")
    ppu = _fmt_money(route.get("profit_per_unit") or route.get("profit_unit"))
    total = _fmt_money(route.get("profit_total"))
    lbl = i18n.t
    return (
        f"• {frm} → {to} — {lbl('labels.profit_per_unit', lang=lang)}: {ppu} | "
        f"{lbl('labels.profit_total', lang=lang)}: {total}"
    )


def format_fuel_list(entries: List[Dict[str, Any]], i18n: I18N, lang: str) -> str:
    """Format fuel price list."""
    lines: List[str] = []
    for e in entries[:25]:
        loc = _shorten(e.get("location") or e.get("terminal") or "-")
        price = _fmt_money(e.get("price"))
        lines.append(f"• {loc}: {price}")
    return "\n".join(lines) or "—"


def format_alerts_list(entries: List[Dict[str, Any]], i18n: I18N, lang: str) -> str:
    """Format commodity alerts list."""
    lbl = i18n.t
    lines: List[str] = []
    for e in entries[:25]:
        comm = e.get("commodity_name") or e.get("commodity") or "-"
        term = _shorten(e.get("terminal_name") or "-")
        typ = e.get("type", "")
        price = _fmt_money(e.get("price"))
        lines.append(f"• {comm} @ {term} — {typ}: {price}")
    return "\n".join(lines) or "—"

