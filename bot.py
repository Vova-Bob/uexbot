"""
Main entry point for the Discord UEX bot.

This script initializes the Discord client, loads environment variables for
configuration, sets up the UEX API client, loads all command cogs and starts
the bot. Slash commands are synchronised automatically on startup.
"""

from __future__ import annotations

import asyncio
import os
from typing import List

import discord
from discord.ext import commands
from dotenv import load_dotenv

from uex_api import UEXAPI


class UEXBot(commands.Bot):
    """Custom Bot class that holds a reference to the UEX API client."""

    def __init__(self, api: UEXAPI, *args: any, **kwargs: any) -> None:
        super().__init__(*args, **kwargs)
        self.api = api

    async def setup_hook(self) -> None:
        """Hook called before the bot logs in; load cogs here."""
        # Load all extensions (cogs) in the cogs package
        initial_extensions: List[str] = [
            "cogs.general",
        ]
        for ext in initial_extensions:
            await self.load_extension(ext)

        # Sync command tree globally
        # If you want faster updates, specify a guild ID here and sync to that guild only
        await self.tree.sync()


async def main() -> None:
    """Entrypoint for running the bot."""
    # Load environment variables from .env file if present
    load_dotenv()
    discord_token = os.getenv("DISCORD_TOKEN")
    uex_token = os.getenv("UEX_API_TOKEN")
    if not discord_token:
        raise RuntimeError("DISCORD_TOKEN environment variable not set")
    if not uex_token:
        raise RuntimeError("UEX_API_TOKEN environment variable not set")
    api = UEXAPI(uex_token)

    intents = discord.Intents.default()
    # Enable members intent if needed for your commands
    bot = UEXBot(api=api, command_prefix="!", intents=intents)

    @bot.event
    async def on_ready() -> None:
        """Event called when the bot is ready."""
        print(f"Logged in as {bot.user} (ID: {bot.user.id})")

    try:
        await bot.start(discord_token)
    finally:
        await api.close()


if __name__ == "__main__":
    asyncio.run(main())