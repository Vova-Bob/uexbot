"""/alerts command: show commodity alerts."""

from __future__ import annotations

import os
import asyncio
from typing import List, Optional, Tuple

import discord
from discord.ext import commands
from discord import app_commands

from utils.uex_api import UEXAPI
from utils.formatting import format_alerts_list
from utils.utils import send_embed_factory
from utils.i18n import I18N, LangPrefs
from utils.cache import load_json_cache, save_json_cache


def _norm(text: str) -> str:
    return (text or "").strip().lower()


class Alerts(commands.Cog):
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

    async def _load_alerts(self, commodity_id: Optional[int]) -> List[dict]:
        cache_name = f"alerts_{commodity_id or 0}"
        cached = load_json_cache(cache_name, 1800)
        if cached:
            return cached
        params = {}
        if commodity_id:
            params["id_commodity"] = commodity_id
        data = await self.api.get_commodities_alerts(**params)
        entries = data.get("data", []) or []
        save_json_cache(cache_name, entries)
        return entries

    @app_commands.command(name="alerts", description="Алерти по цінах/наявності")
    @app_commands.describe(commodity="Назва товару (опціонально)")
    @app_commands.autocomplete(commodity=commodity_autocomplete)
    async def alerts(self, interaction: discord.Interaction, commodity: Optional[str] = None) -> None:
        lang = self.prefs.get(interaction.guild_id)
        cid = int(commodity) if commodity else None
        try:
            entries = await self._load_alerts(cid)
        except Exception as exc:
            await self._send_embed(
                interaction,
                self.i18n.t("ui.err_no_data", lang=lang),
                self.i18n.t("ui.err_price_fetch", lang=lang, msg=str(exc)),
            )
            return
        if not entries:
            await self._send_embed(
                interaction,
                self.i18n.t("ui.err_no_data", lang=lang),
                self.i18n.t("ui.err_no_matches", lang=lang),
            )
            return

        desc = format_alerts_list(entries, self.i18n, lang)
        title = self.i18n.t("ui.cmd_alerts_desc", lang=lang)
        await self._send_embed(interaction, title, desc)


async def setup(bot: commands.Bot) -> None:
    api = bot.api
    await bot.add_cog(Alerts(bot, api, bot.i18n, bot.lang_prefs))

