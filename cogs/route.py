"""/route command: show trading routes and profit."""

from __future__ import annotations

import os
import asyncio
from typing import List, Optional, Tuple

import discord
from discord.ext import commands
from discord import app_commands

from utils.uex_api import UEXAPI
from utils.formatting import format_route_summary
from utils.utils import send_embed_factory
from utils.i18n import I18N, LangPrefs
from utils.cache import load_json_cache, save_json_cache


def _norm(text: str) -> str:
    return (text or "").strip().lower()


class Route(commands.Cog):
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

    async def _load_routes(
        self, commodity_id: int, from_id: Optional[int], to_id: Optional[int], scu: Optional[int]
    ) -> List[dict]:
        cache_name = f"routes_{commodity_id}_{from_id or 0}_{to_id or 0}_{scu or 0}"
        cached = load_json_cache(cache_name, 600)
        if cached:
            return cached
        params = {"id_commodity": commodity_id}
        if from_id:
            params["from_terminal"] = from_id
        if to_id:
            params["to_terminal"] = to_id
        if scu:
            params["scu"] = scu
        data = await self.api.get_commodities_routes(**params)
        entries = data.get("data", []) or []
        save_json_cache(cache_name, entries)
        return entries

    @app_commands.command(name="route", description="Маршрут трейду та прибуток")
    @app_commands.describe(
        commodity="Назва товару",
        from_terminal="Звідки (термінал)",
        to_terminal="Куди (термінал, опціонально)",
        scu="Скільки SCU",
    )
    @app_commands.rename(from_terminal="from", to_terminal="to")
    @app_commands.autocomplete(
        commodity=commodity_autocomplete,
        from_terminal=terminal_autocomplete,
        to_terminal=terminal_autocomplete,
    )
    async def route(
        self,
        interaction: discord.Interaction,
        commodity: str,
        from_terminal: Optional[str] = None,
        to_terminal: Optional[str] = None,
        scu: Optional[int] = None,
    ) -> None:
        lang = self.prefs.get(interaction.guild_id)
        try:
            comm = await self._find_commodity(commodity)
        except Exception as exc:
            await self._send_embed(
                interaction,
                self.i18n.t("ui.err_no_data", lang=lang),
                self.i18n.t("ui.err_route_fetch", lang=lang, msg=str(exc)),
            )
            return
        if not comm:
            await self._send_embed(
                interaction,
                self.i18n.t("ui.err_no_data", lang=lang),
                self.i18n.t("ui.err_no_matches", lang=lang),
            )
            return
        fid = int(from_terminal) if from_terminal else None
        tid = int(to_terminal) if to_terminal else None
        try:
            routes = await self._load_routes(int(comm.get("id")), fid, tid, scu)
        except Exception as exc:
            await self._send_embed(
                interaction,
                self.i18n.t("ui.err_no_data", lang=lang),
                self.i18n.t("ui.err_route_fetch", lang=lang, msg=str(exc)),
            )
            return
        if not routes:
            await self._send_embed(
                interaction,
                self.i18n.t("ui.err_no_data", lang=lang),
                self.i18n.t("ui.err_route_fetch", lang=lang, msg="empty"),
            )
            return

        if tid is None:
            routes = routes[:3]
        desc = "\n".join(format_route_summary(r, self.i18n, lang) for r in routes)
        title = f"{self.i18n.t('labels.commodity', lang=lang)}: {comm.get('name', '')}"
        await self._send_embed(interaction, title, desc)


async def setup(bot: commands.Bot) -> None:
    api = bot.api
    await bot.add_cog(Route(bot, api, bot.i18n, bot.lang_prefs))

