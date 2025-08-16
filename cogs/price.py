"""/price command: show commodity prices with local pagination."""

from __future__ import annotations

import os
import asyncio
from typing import List, Optional, Tuple

import discord
from discord.ext import commands
from discord import app_commands

from utils.uex_api import UEXAPI
from utils.pager import BasePaginatorView
from utils.formatting import format_price_list
from utils.utils import send_embed_factory
from utils.i18n import I18N, LangPrefs
from utils.cache import load_json_cache, save_json_cache


def _norm(text: str) -> str:
    return (text or "").strip().lower()


class PricePaginatorView(BasePaginatorView):
    def __init__(
        self,
        *,
        entries: List[dict],
        i18n: I18N,
        lang: str,
        commodity_name: str,
        user_id: int,
        page_size: int = 25,
    ) -> None:
        super().__init__(items=entries, i18n=i18n, lang=lang, user_id=user_id, page_size=page_size)
        self.commodity_name = commodity_name

    def _embed(self) -> discord.Embed:
        title = f"{self.i18n.t('labels.commodity', lang=self.lang)}: {self.commodity_name}"
        desc = format_price_list(self._page_slice(), self.i18n, self.lang)
        embed = discord.Embed(title=title, description=desc, color=0x2b6cb0)
        page_num = (self.offset // self.page_size) + 1
        embed.set_footer(text=self.i18n.t("ui.page_n", lang=self.lang, n=page_num))
        return embed


class Price(commands.Cog):
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

    async def _load_prices(self, commodity_id: int) -> List[dict]:
        cache_name = f"prices_{commodity_id}"
        cached = load_json_cache(cache_name, 600)
        if cached:
            return cached
        data = await self.api.get_commodities_prices(id_commodity=commodity_id, limit=5000)
        entries = data.get("data", []) or []
        save_json_cache(cache_name, entries)
        return entries

    @app_commands.command(name="price", description="Показати ціни товару (термінал опціонально)")
    @app_commands.describe(
        commodity="Назва товару",
        terminal="Термінал (опціонально)",
    )
    @app_commands.autocomplete(commodity=commodity_autocomplete, terminal=terminal_autocomplete)
    async def price(self, interaction: discord.Interaction, commodity: str, terminal: Optional[str] = None) -> None:
        lang = self.prefs.get(interaction.guild_id)
        try:
            comm = await self._find_commodity(commodity)
        except Exception as exc:
            await self._send_embed(
                interaction,
                self.i18n.t("ui.err_no_data", lang=lang),
                self.i18n.t("ui.err_price_fetch", lang=lang, msg=str(exc)),
            )
            return
        if not comm:
            await self._send_embed(
                interaction,
                self.i18n.t("ui.err_no_data", lang=lang),
                self.i18n.t("ui.err_no_matches", lang=lang),
            )
            return
        try:
            entries = await self._load_prices(int(comm.get("id")))
        except Exception as exc:
            await self._send_embed(
                interaction,
                self.i18n.t("ui.err_no_data", lang=lang),
                self.i18n.t("ui.err_price_fetch", lang=lang, msg=str(exc)),
            )
            return
        if terminal:
            tid = int(terminal)
            entries = [e for e in entries if e.get("id_terminal") == tid]
        if not entries:
            await self._send_embed(
                interaction,
                self.i18n.t("ui.err_no_data", lang=lang),
                self.i18n.t("ui.err_price_fetch", lang=lang, msg="empty"),
            )
            return

        entries.sort(key=lambda x: x.get("price_sell", 0), reverse=True)
        view = PricePaginatorView(
            entries=entries,
            i18n=self.i18n,
            lang=lang,
            commodity_name=comm.get("name", ""),
            user_id=interaction.user.id if interaction.user else 0,
        )
        embed = view._embed()
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    api = bot.api
    await bot.add_cog(Price(bot, api, bot.i18n, bot.lang_prefs))

