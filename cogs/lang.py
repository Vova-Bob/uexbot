"""
Language management (DRY/KISS):
- /lang <uk|en>       -> set guild language
- /lang_show          -> show current guild language
- /i18n_reload        -> hot-reload locale JSON files (admins only)
All replies are ephemeral by default (config via env DEFAULT_EPHEMERAL).
"""

from __future__ import annotations

import os
import discord
from discord.ext import commands
from discord import app_commands

from utils.i18n import I18N, LangPrefs


def _default_ephemeral_from_env() -> bool:
    """Read DEFAULT_EPHEMERAL=1/true/yes to decide ephemeral replies."""
    v = os.getenv("DEFAULT_EPHEMERAL", "1").lower()
    return v in ("1", "true", "yes", "y", "on")


class LangCog(commands.Cog):
    """Cog with language-related slash commands."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        # Injected by your custom Bot in bot.py
        self.i18n: I18N = bot.i18n
        self.prefs: LangPrefs = bot.lang_prefs
        self._ephemeral = _default_ephemeral_from_env()

    # ---------------- small util to reply safely ----------------
    async def _reply(self, interaction: discord.Interaction, content: str) -> None:
        """Send ephemeral reply whether response is already used or not."""
        if interaction.response.is_done():
            await interaction.followup.send(content, ephemeral=self._ephemeral)
        else:
            await interaction.response.send_message(content, ephemeral=self._ephemeral)

    # ---------------- /lang ----------------
    @app_commands.command(name="lang", description="Встановити мову бота для цього сервера")
    @app_commands.describe(code="Код мови (en, uk)")
    @app_commands.choices(
        code=[
            app_commands.Choice(name="Українська", value="uk"),
            app_commands.Choice(name="English", value="en"),
        ]
    )
    async def lang(self, interaction: discord.Interaction, code: app_commands.Choice[str]) -> None:
        """Set guild language (stored in data/lang_prefs.json)."""
        # Super fast op -> no defer needed
        if interaction.guild:
            self.prefs.set(interaction.guild.id, code.value)
            # lang=... selects translation file, {code} is inserted into template
            msg = self.i18n.t("ui.ok_lang_set", lang=code.value, code=code.value)
        else:
            # DMs: do not persist, just inform
            msg = self.i18n.t("ui.lang_current", lang=code.value, code=code.value)
        await self._reply(interaction, msg)

    # ---------------- /lang_show ----------------
    @app_commands.command(name="lang_show", description="Показати поточну мову сервера")
    async def lang_show(self, interaction: discord.Interaction) -> None:
        """Show saved language for this guild (or default in DMs)."""
        code = self.prefs.get(interaction.guild_id if interaction.guild else None)
        msg = self.i18n.t("ui.lang_current", lang=code, code=code)
        await self._reply(interaction, msg)

    # ---------------- /i18n_reload ----------------
    @app_commands.command(name="i18n_reload", description="Перечитати локалізації з диска (адміністратори)")
    @commands.has_permissions(administrator=True)
    async def i18n_reload(self, interaction: discord.Interaction) -> None:
        """Hot-reload locales/ *.json; defer to avoid 3s timeout."""
        await interaction.response.defer(ephemeral=True)  # acknowledge immediately
        maps = self.i18n.reload()
        langs = ", ".join(sorted(maps.keys())) or "—"
        await interaction.followup.send(f"Локалізацію оновлено. Доступні: {langs}", ephemeral=True)

    # Nice error message if user lacks admin perms for /i18n_reload
    @i18n_reload.error
    async def _i18n_reload_error(self, interaction: discord.Interaction, error: Exception) -> None:
        if isinstance(error, commands.MissingPermissions):
            await self._reply(interaction, "Потрібні права адміністратора для цієї команди.")
        else:
            await self._reply(interaction, f"Помилка: {error}")

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        print(f"Loaded cog: {self.__class__.__name__}")


async def setup(bot: commands.Bot) -> None:
    """Entry point for discord.py to load this cog."""
    await bot.add_cog(LangCog(bot))
