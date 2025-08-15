"""
Main entry point for the Discord UEX bot.

Loads env vars, initializes Discord client, sets up UEX API client and i18n,
loads cogs (each command = separate file), and syncs slash-commands.
"""

from __future__ import annotations
import os
import asyncio
import discord
from discord.ext import commands
from dotenv import load_dotenv

from utils.uex_api import get_api_from_env
from utils.i18n import I18N, LangPrefs

INTENTS = discord.Intents.none()
CMD_PREFIX = "!"  # not used by slash-commands

class UEXBot(commands.Bot):
    """Bot that holds API client and i18n services."""

    def __init__(self) -> None:
        super().__init__(command_prefix=CMD_PREFIX, intents=INTENTS)
        # API (token optional for /categories)
        self.api = get_api_from_env()
        # i18n
        default_locale = os.getenv("DEFAULT_LOCALE", "uk")
        self.i18n = I18N(default=default_locale)
        self.lang_prefs = LangPrefs(default=default_locale)

    async def setup_hook(self) -> None:
        """Load cogs and sync application commands."""
        # One command per file (SRP)
        await self.load_extension("cogs.category")
        await self.load_extension("cogs.items_by_category")
        await self.load_extension("cogs.lang")

        guild_id = os.getenv("DISCORD_GUILD_ID")
        if guild_id:
            await self.tree.sync(guild=discord.Object(id=int(guild_id)))
            print(f"[sync] commands -> guild {guild_id}")
        else:
            await self.tree.sync()
            print("[sync] commands -> global")

    async def close(self) -> None:
        """Ensure API session is closed on shutdown."""
        try:
            await self.api.close()
        finally:
            await super().close()

async def main() -> None:
    load_dotenv()
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise RuntimeError("DISCORD_TOKEN is not set in environment")
    bot = UEXBot()

    @bot.event
    async def on_ready() -> None:
        assert bot.user is not None
        print(f"Logged in as {bot.user} (ID: {bot.user.id})")

    async with bot:
        await bot.start(token)

if __name__ == "__main__":
    asyncio.run(main())
