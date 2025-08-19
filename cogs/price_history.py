"""/price_history command: show commodity price history."""

from __future__ import annotations

import os
import asyncio
from typing import List, Optional, Tuple

import discord
from discord.ext import commands
from discord import app_commands

from utils.uex_api import UEXAPI
from utils.utils import send_embed_factory
from utils.i18n import I18N, LangPrefs
from utils.cache import load_json_cache, save_json_cache


def _norm(text: str) -> str:
    return (text or "").strip().lower()


class PriceHistory(commands.Cog):
    def __init__(self, bot: commands.Bot, api: UEXAPI, i18n: I18N, prefs: LangPrefs) -> None:
        self.bot = bot
        self.api = api
        self.i18n = i18n
        self.prefs = prefs

        ephem_env = os.getenv("DEFAULT_EPHEMERAL", "1").lower()
        default_ephemeral = ephem_env in ("1", "true", "yes", "y", "on")
        self._send_embed = send_embed_factory(i18n, default_ephemeral=default_ephemeral)

        seeded_c = load_json_cache("commodities", 24 * 3600) or []
        self._commodities_cache: Tuple[float, List[dict]] = (
            asyncio.get_event_loop().time(), seeded_c
        )
        seeded_t = load_json_cache("terminals", 24 * 3600) or []
        self._terminals_cache: Tuple[float, List[dict]] = (
            asyncio.get_event_loop().time(), seeded_t
        )

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        print(f"Loaded cog: {self.__class__.__name__}")

    async def _load_commodities(self) -> List[dict]:
        now = asyncio.get_event_loop().time()
        ts, cached = self._commodities_cache
        if cached and (now - ts) < 86400:
            return cached
        data = await self.api.get("commodities")
        items = data.get("data", []) or []
        self._commodities_cache = (now, items)
        save_json_cache("commodities", items)
        return items

    async def _load_terminals(self) -> List[dict]:
        now = asyncio.get_event_loop().time()
        ts, cached = self._terminals_cache
        if cached and (now - ts) < 86400:
            return cached
        data = await self.api.get_terminals()
        items = data.get("data", []) or []
        self._terminals_cache = (now, items)
        save_json_cache("terminals", items)
        return items

    async def commodity_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        try:
            commodities = await self._load_commodities()
        except Exception:
            return []
        cur = _norm(current)
        subset = (
            commodities[:20]
            if not cur
            else (
                [c for c in commodities if _norm(c.get("name", "")).startswith(cur)]
                + [c for c in commodities if cur in _norm(c.get("name", ""))]
            )[:20]
        )
        lang = self.prefs.get(interaction.guild_id)
        return [
            app_commands.Choice(name=self.i18n.tc(c.get("name", ""), lang), value=str(c.get("id")))
            for c in subset
        ]

    async def terminal_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        try:
            terms = await self._load_terminals()
        except Exception:
            return []
        cur = _norm(current)
        subset = (
            terms[:20]
            if not cur
            else (
                [t for t in terms if _norm(t.get("name", "")).startswith(cur)]
                + [t for t in terms if cur in _norm(t.get("name", ""))]
            )[:20]
        )
        return [
            app_commands.Choice(name=t.get("name", ""), value=str(t.get("id")))
            for t in subset
        ]

    async def _find_commodity(self, query: str) -> Optional[dict]:
        commodities = await self._load_commodities()
        if not commodities:
            return None
        q = _norm(query)
        for c in commodities:
            if str(c.get("id")) == q:
                return c
        exact = [c for c in commodities if _norm(c.get("name", "")) == q]
        if exact:
            return exact[0]
        starts = [c for c in commodities if _norm(c.get("name", "")).startswith(q)]
        if starts:
            return starts[0]
        contains = [c for c in commodities if q in _norm(c.get("name", ""))]
        return contains[0] if contains else None

    async def _load_history(self, commodity_id: int, terminal_id: Optional[int]) -> List[dict]:
        cache_name = f"history_{commodity_id}_{terminal_id or 0}"
        cached = load_json_cache(cache_name, 21600)
        if cached:
            return cached
        params = {"id_commodity": commodity_id, "limit": 200}
        if terminal_id:
            params["id_terminal"] = terminal_id
        data = await self.api.get_commodities_prices_history(**params)
        entries = data.get("data", []) or []
        save_json_cache(cache_name, entries)
        return entries

    @app_commands.command(name="price_history", description="Історія цін товару")
    @app_commands.describe(
        commodity="Назва товару",
        terminal="Термінал (опціонально)",
    )
    @app_commands.autocomplete(commodity=commodity_autocomplete, terminal=terminal_autocomplete)
    async def price_history(self, interaction: discord.Interaction, commodity: str, terminal: Optional[str] = None) -> None:
        lang = self.prefs.get(interaction.guild_id)
        try:
            comm = await self._find_commodity(commodity)
        except Exception as exc:
            await self._send_embed(
                interaction,
                self.i18n.t("ui.err_no_data", lang=lang),
                self.i18n.t("ui.err_history_fetch", lang=lang, msg=str(exc)),
            )
            return
        if not comm:
            await self._send_embed(
                interaction,
                self.i18n.t("ui.err_no_data", lang=lang),
                self.i18n.t("ui.err_no_matches", lang=lang),
            )
            return
        tid = int(terminal) if terminal else None
        try:
            entries = await self._load_history(int(comm.get("id")), tid)
        except Exception as exc:
            await self._send_embed(
                interaction,
                self.i18n.t("ui.err_no_data", lang=lang),
                self.i18n.t("ui.err_history_fetch", lang=lang, msg=str(exc)),
            )
            return
        if not entries:
            await self._send_embed(
                interaction,
                self.i18n.t("ui.err_no_data", lang=lang),
                self.i18n.t("ui.err_history_fetch", lang=lang, msg="empty"),
            )
            return

        lines: List[str] = []
        prev = None
        for e in entries[-10:]:
            ts = e.get("timestamp") or e.get("created_at") or "?"
            buy = e.get("price_buy")
            sell = e.get("price_sell")
            arrow_b = arrow_s = ""
            if prev is not None:
                db = buy - prev[0]
                ds = sell - prev[1]
                arrow_b = "↑" if db > 0 else "↓" if db < 0 else "="
                arrow_s = "↑" if ds > 0 else "↓" if ds < 0 else "="
            lines.append(f"{ts}: B {buy} {arrow_b} | S {sell} {arrow_s}")
            prev = (buy, sell)

        title = f"{self.i18n.t('labels.commodity', lang=lang)}: {comm.get('name', '')}"
        desc = "\n".join(lines)
        await self._send_embed(interaction, title, desc)


async def setup(bot: commands.Bot) -> None:
    api = bot.api
    await bot.add_cog(PriceHistory(bot, api, bot.i18n, bot.lang_prefs))

