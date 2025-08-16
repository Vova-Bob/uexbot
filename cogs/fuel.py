"""/fuel command: show fuel prices."""

from __future__ import annotations

import os
from typing import List

import discord
from discord.ext import commands
from discord import app_commands

from utils.uex_api import UEXAPI
from utils.formatting import format_fuel_list
from utils.utils import send_embed_factory
from utils.i18n import I18N, LangPrefs
from utils.cache import load_json_cache, save_json_cache


def _norm(text: str) -> str:
    return (text or "").strip().lower()


class Fuel(commands.Cog):
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

    async def _load_fuel(self) -> List[dict]:
        cache_name = "fuel_prices"
        cached = load_json_cache(cache_name, 600)
        if cached:
            return cached
        data = await self.api.get_fuel_prices()
        entries = data.get("data", []) or []
        save_json_cache(cache_name, entries)
        return entries

    @app_commands.command(name="fuel", description="Ціни на паливо")
    @app_commands.describe(query="Система/станція (опціонально)")
    async def fuel(self, interaction: discord.Interaction, query: str = "") -> None:
        lang = self.prefs.get(interaction.guild_id)
        try:
            entries = await self._load_fuel()
        except Exception as exc:
            await self._send_embed(
                interaction,
                self.i18n.t("ui.err_no_data", lang=lang),
                self.i18n.t("ui.err_fuel_fetch", lang=lang, msg=str(exc)),
            )
            return
        q = _norm(query)
        if q:
            entries = [e for e in entries if q in _norm(e.get("location", ""))]
        if not entries:
            await self._send_embed(
                interaction,
                self.i18n.t("ui.err_no_data", lang=lang),
                self.i18n.t("ui.err_no_matches", lang=lang),
            )
            return
        desc = format_fuel_list(entries, self.i18n, lang)
        title = self.i18n.t("ui.cmd_fuel_desc", lang=lang)
        await self._send_embed(interaction, title, desc)


async def setup(bot: commands.Bot) -> None:
    api = bot.api
    await bot.add_cog(Fuel(bot, api, bot.i18n, bot.lang_prefs))

