"""/about command: show bot and game version info."""

from __future__ import annotations

import os
import datetime as dt

import discord
from discord.ext import commands
from discord import app_commands

from utils.uex_api import UEXAPI
from utils.utils import send_embed_factory
from utils.i18n import I18N, LangPrefs
from utils import cache as cache_utils

BOT_VERSION = "0.1"
START_TIME = dt.datetime.utcnow()


class About(commands.Cog):
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

    async def _load_versions(self) -> list[dict]:
        cache_name = "game_versions"
        cached = cache_utils.load_json_cache(cache_name, 86400)
        if cached:
            return cached
        data = await self.api.get_game_versions()
        if (data or {}).get("status") != "ok":
            return []
        entries = data.get("data", []) or []
        cache_utils.save_json_cache(cache_name, entries)
        return entries

    @app_commands.command(name="about", description="Про бота і версію гри")
    async def about(self, interaction: discord.Interaction) -> None:
        lang = self.prefs.get(interaction.guild_id)
        try:
            versions = await self._load_versions()
        except Exception as exc:
            await self._send_embed(
                interaction,
                self.i18n.t("ui.err_no_data", lang=lang),
                self.i18n.t("ui.err_history_fetch", lang=lang, msg=str(exc)),
            )
            return
        cache_file = cache_utils._path("game_versions")
        ts = dt.datetime.fromtimestamp(os.path.getmtime(cache_file)) if os.path.exists(cache_file) else dt.datetime.utcnow()
        ver = versions[0].get("version") if versions else "?"
        uptime = dt.datetime.utcnow() - START_TIME
        desc = (
            f"{self.i18n.t('labels.game_version', lang=lang)}: {ver}\n"
            f"{self.i18n.t('labels.updated', lang=lang)}: {ts.isoformat()}\n"
            f"{self.i18n.t('labels.uptime', lang=lang)}: {str(uptime).split('.', 1)[0]}\n"
            f"Bot: {BOT_VERSION}"
        )
        title = self.i18n.t("ui.cmd_about_desc", lang=lang)
        await self._send_embed(interaction, title, desc)


async def setup(bot: commands.Bot) -> None:
    api = bot.api
    await bot.add_cog(About(bot, api, bot.i18n, bot.lang_prefs))

