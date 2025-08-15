"""
/category command (standalone cog) with i18n and private embeds.
- Autocomplete by category name
- Uses /categories list endpoint and filters locally
- Memory cache 60s (no disk cache, no env flags)
"""

from __future__ import annotations

import asyncio
import re
from typing import List, Optional, Tuple

import discord
from discord.ext import commands
from discord import app_commands

from utils.uex_api import UEXAPI
from utils.utils import format_category, send_embed_factory
from utils.i18n import I18N, LangPrefs


def _is_int(text: str) -> bool:
    return bool(re.fullmatch(r"\d+", (text or "").strip()))


def _norm(text: str) -> str:
    return (text or "").strip().lower()


class Category(commands.Cog):
    """Cog with a single localized /category command."""

    def __init__(self, bot: commands.Bot, api: UEXAPI, i18n: I18N, prefs: LangPrefs) -> None:
        self.bot = bot
        self.api = api
        self.i18n = i18n
        self.prefs = prefs
        # always send private embeds by default
        self._send_embed = send_embed_factory(i18n, default_ephemeral=True)
        # simple RAM cache (timestamp, data)
        self._categories_cache: Tuple[float, List[dict]] = (0.0, [])

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        print(f"Loaded cog: {self.__class__.__name__}")

    async def _load_categories(self) -> List[dict]:
        """Fetch categories; keep 60s cache in memory."""
        now = asyncio.get_event_loop().time()
        ts, cached = self._categories_cache
        if cached and (now - ts) < 60:
            return cached
        cats = await self.api.get_categories()
        self._categories_cache = (now, cats)
        return cats

    async def _find_category(self, query: str) -> Optional[dict]:
        """Find by numeric ID or by name (exact/startswith/contains)."""
        cats = await self._load_categories()
        if not cats:
            return None
        if _is_int(query):
            cid = int(query)
            for c in cats:
                if c.get("id") == cid:
                    return c
            return None
        q = _norm(query)
        exact = [c for c in cats if _norm(c.get("name", "")) == q]
        if exact:
            return exact[0]
        starts = [c for c in cats if _norm(c.get("name", "")).startswith(q)]
        if starts:
            return starts[0]
        contains = [c for c in cats if q in _norm(c.get("name", ""))]
        return contains[0] if contains else None

    async def category_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> List[app_commands.Choice[str]]:
        """Autocomplete by category name; pass category ID as value."""
        try:
            cats = await self._load_categories()
        except Exception:
            return []
        cur = _norm(current)
        subset = cats[:20] if not cur else (
            [c for c in cats if _norm(c.get("name", "")).startswith(cur)]
            + [c for c in cats if cur in _norm(c.get("name", ""))]
        )[:20]
        lang = self.prefs.get(interaction.guild_id if interaction.guild else None)
        return [
            app_commands.Choice(
                name=f'{self.i18n.tc(c.get("name", ""), lang)} (ID: {c.get("id")})',
                value=str(c.get("id")),
            )
            for c in subset
        ]

    @app_commands.command(
        name="category",
        description="Показати інформацію про категорію (ID або назва; є автодоповнення)",
    )
    @app_commands.describe(
        category="ID або назва категорії (виберіть зі списку або введіть)"
    )
    @app_commands.autocomplete(category=category_autocomplete)
    async def category(self, interaction: discord.Interaction, category: str) -> None:
        """Show details about a chosen category."""
        lang = self.prefs.get(interaction.guild_id if interaction.guild else None)
        try:
            cat = await self._find_category(category)
        except Exception as exc:
            await self._send_embed(
                interaction,
                self.i18n.t("ui.err_no_data", lang=lang),
                self.i18n.t("ui.err_category_fetch", lang=lang, msg=str(exc)),
            )
            return
        if not cat:
            await self._send_embed(
                interaction,
                self.i18n.t("ui.err_no_data", lang=lang),
                self.i18n.t("ui.err_category_not_found", lang=lang),
            )
            return

        title = self.i18n.t(
            "ui.category_title",
            lang=lang,
            name=self.i18n.tc(cat.get("name", ""), lang),
            id=cat.get("id"),
        )
        desc = format_category(cat, self.i18n, lang)
        await self._send_embed(interaction, title, desc)


async def setup(bot: commands.Bot) -> None:
    api = bot.api  # provided by UEXBot
    await bot.add_cog(Category(bot, api, bot.i18n, bot.lang_prefs))
