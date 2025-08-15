# cogs/sync.py
from __future__ import annotations
import discord
from discord.ext import commands
from discord import app_commands

class SyncCog(commands.Cog):
    """Admin-only helpers to sync app commands."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="sync_here", description="Синхронізувати слеш-команди в цьому сервері")
    @commands.has_permissions(administrator=True)
    @app_commands.guild_only()
    async def sync_here(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        await self.bot.tree.sync(guild=interaction.guild)
        await interaction.followup.send("Синхронізовано команди для цього сервера ✅", ephemeral=True)

    @app_commands.command(name="sync_global", description="Синхронізувати команди глобально (може кешуватись до 1 год)")
    @commands.has_permissions(administrator=True)
    async def sync_global(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        await self.bot.tree.sync()
        await interaction.followup.send("Глобальну синхронізацію виконано ✅", ephemeral=True)

    @sync_here.error
    @sync_global.error
    async def _perm_error(self, interaction: discord.Interaction, error: Exception) -> None:
        if isinstance(error, commands.MissingPermissions):
            await interaction.response.send_message("Потрібні права адміністратора.", ephemeral=True)
        else:
            await interaction.response.send_message(f"Помилка: {error}", ephemeral=True)

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(SyncCog(bot))
