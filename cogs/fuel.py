"""/fuel command: show fuel prices with autocomplete (terminals & commodities).
- Uses /fuel_prices_all to build autocomplete lists (cached).
- Executes /fuel_prices with selected filters.
- Ephemeral replies; i18n-aware; DRY/KISS.
"""

from __future__ import annotations

import os
from typing import List, Optional

import discord
from discord.ext import commands
from discord import app_commands

from utils.uex_api import UEXAPI
from utils.formatting import format_fuel_list  # expects terminal_name, commodity_name, price_buy, price_buy_avg, ...
from utils.utils import send_embed_factory
from utils.i18n import I18N, LangPrefs
from utils.cache import load_json_cache, save_json_cache


def _norm(s: str) -> str:
    return (s or "").strip().lower()


class Fuel(commands.Cog):
    """Fuel prices (with autocomplete for commodity and terminal)."""

    def __init__(self, bot: commands.Bot, api: UEXAPI, i18n: I18N, prefs: LangPrefs) -> None:
        self.bot = bot
        self.api = api
        self.i18n = i18n
        self.prefs = prefs

        ephem_env = os.getenv("DEFAULT_EPHEMERAL", "1").lower()
        default_ephemeral = ephem_env in ("1", "true", "yes", "y", "on")
        self._send_embed = send_embed_factory(i18n, default_ephemeral=default_ephemeral)

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        print(f"Loaded cog: {self.__class__.__name__}")

    # ------- data & cache -------
    async def _load_fuel_all(self) -> List[dict]:
        """Load /fuel_prices_all and cache ~10 min (API TTL is 30 min)."""
        cache_name = "fuel_prices_all"
        cached = load_json_cache(cache_name, 600)
        if cached:
            return cached
        data = await self.api.get_fuel_prices_all()
        rows = (data or {}).get("data", []) or []
        save_json_cache(cache_name, rows)
        return rows

    # ------- autocomplete -------
    async def commodity_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> List[app_commands.Choice[str]]:
        try:
            rows = await self._load_fuel_all()
        except Exception:
            return []
        q = _norm(current)
        names = sorted({r.get("commodity_name", "") for r in rows if r.get("commodity_name")})
        if q:
            names = [n for n in names if q in _norm(n)]
        return [app_commands.Choice(name=n, value=n) for n in names[:20]]

    async def terminal_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> List[app_commands.Choice[str]]:
        try:
            rows = await self._load_fuel_all()
        except Exception:
            return []
        q = _norm(current)
        names = sorted({r.get("terminal_name", "") for r in rows if r.get("terminal_name")})
        if q:
            names = [n for n in names if q in _norm(n)]
        return [app_commands.Choice(name=n, value=n) for n in names[:20]]

    # ------- command -------
    @app_commands.command(name="fuel", description="Ціни на паливо")
    @app_commands.describe(
        commodity="Назва палива (наприклад, Quantum Fuel)",
        terminal="Назва терміналу/станції",
    )
    @app_commands.autocomplete(commodity=commodity_autocomplete, terminal=terminal_autocomplete)
    async def fuel(
        self,
        interaction: discord.Interaction,
        commodity: Optional[str] = None,
        terminal: Optional[str] = None,
    ) -> None:
        """Call /fuel_prices with chosen filters and show formatted list."""
        lang = self.prefs.get(interaction.guild_id if interaction.guild else None)

        # Build API params according to docs: any of terminal_* or commodity_*
        params = {}
        if commodity:
            params["commodity_name"] = commodity
        if terminal:
            params["terminal_name"] = terminal

        # If user didn't provide anything, show all (using fuel_prices_all)
        try:
            if not params:
                rows = await self._load_fuel_all()
            else:
                data = await self.api.get_fuel_prices(**params)
                rows = (data or {}).get("data", []) or []
        except Exception as exc:
            await self._send_embed(
                interaction,
                self.i18n.t("ui.err_no_data", lang=lang),
                self.i18n.t("ui.err_fuel_fetch", lang=lang, msg=str(exc)),
            )
            return

        if not rows:
            await self._send_embed(
                interaction,
                self.i18n.t("ui.err_no_data", lang=lang),
                self.i18n.t("ui.err_no_matches", lang=lang),
            )
            return

        # Sort by cheapest buy price (ascending)
        rows.sort(
            key=lambda r: (
                r.get("price_buy") if r.get("price_buy") is not None else float("inf")
            )
        )

        title = self.i18n.t("ui.cmd_fuel_desc", lang=lang)
        desc = format_fuel_list(rows[:50], self.i18n, lang)  # trim long outputs
        await self._send_embed(interaction, title, desc)


async def setup(bot: commands.Bot) -> None:
    api = bot.api
    await bot.add_cog(Fuel(bot, api, bot.i18n, bot.lang_prefs))

