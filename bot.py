# bot.py
"""
Main entry point for the Discord UEX bot.

Loads env vars, initializes Discord client, sets up UEX API client and i18n,
loads cogs, and syncs slash-commands (per-guild if DISCORD_GUILD_IDS is set).
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
CMD_PREFIX = "!"

class UEXBot(commands.Bot):
    def __init__(self) -> None:
        super().__init__(command_prefix=CMD_PREFIX, intents=INTENTS)
        self.api = get_api_from_env()
        default_locale = os.getenv("DEFAULT_LOCALE", "uk")
        self.i18n = I18N(default=default_locale)
        self.lang_prefs = LangPrefs(default=default_locale)

    async def setup_hook(self) -> None:
        # load cogs
        await self.load_extension("cogs.category")
        await self.load_extension("cogs.items_by_category")
        await self.load_extension("cogs.lang")
        await self.load_extension("cogs.sync")  # new: admin sync commands

        # fast per-guild sync if env provided (comma-separated list)
        gids = os.getenv("DISCORD_GUILD_IDS", "").strip()
        if gids:
            ids = [int(x) for x in gids.replace(" ", "").split(",") if x]
            for gid in ids:
                await self.tree.sync(guild=discord.Object(id=gid))
            print(f"[sync] commands -> guilds {ids}")
        else:
            # fallback to global sync (may take up to ~1h to propagate)
            await self.tree.sync()
            print("[sync] commands -> global")

    async def close(self) -> None:
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
