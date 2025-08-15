"""
Category command (standalone cog) for the UEX API with i18n (uk/en).
- Autocomplete by category name (value passes category ID as string)
- Uses /categories list endpoint and filters locally (no /categories/{id})
"""

from __future__ import annotations

import os
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
    """Return True if text is integer-like."""
    return bool(re.fullmatch(r"\d+", (text or "").strip()))


def _norm(text: str) -> str:
    """Lowercase + trim for comparisons."""
    return (text or "").strip().lower()


class Category(commands.Cog):
    """Cog with a single localized /category command."""

    def __init__(self, bot: commands.Bot, api: UEXAPI, i18n: I18N, prefs: LangPrefs) -> None:
        self.bot = bot
        self.api = api
        self.i18n = i18n
        self.prefs = prefs

        # Default privacy from env (DEFAULT_EPHEMERAL=1/true/on)
        ephem_env = os.getenv("DEFAULT_EPHEMERAL", "1").lower()
        default_ephemeral = ephem_env in ("1", "true", "yes", "y", "on")

        self._send_embed = send_embed_factory(i18n, default_ephemeral=default_ephemeral)
        self._categories_cache: Tuple[float, List[dict]] = (0.0, [])  # (timestamp, data)

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        """Log that cog is loaded."""
        print(f"Loaded cog: {self.__class__.__name__}")

    # ---------------- internal helpers ----------------
    async def _load_categories(self) -> List[dict]:
        """Load categories with a tiny 60s cache (be gentle to the API)."""
        now = asyncio.get_event_loop().time()
        ts, cached = self._categories_cache
        if cached and (now - ts) < 60:
            return cached
        cats = await self.api.get_categories()
        self._categories_cache = (now, cats)
        return cats

    async def _find_category(self, query: str) -> Optional[dict]:
        """Find category by numeric ID or by name (exact, startswith, contains)."""
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

    # ---------------- autocomplete ----------------
    async def category_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> List[app_commands.Choice[str]]:
        """Autocomplete by category name; value passed is category ID as string."""
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

    # ---------------- slash command ----------------
    @app_commands.command(
        name="category",
        description="Показати інформацію про категорію (ID або назва; є автодоповнення)",
    )
    @app_commands.describe(
        category="ID або назва категорії (виберіть зі списку або введіть)"
    )
    @app_commands.autocomplete(category=category_autocomplete)
    async def category(self, interaction: discord.Interaction, category: str) -> None:
        """Show details about a chosen category (list endpoint + local filter)."""
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
    """Register this cog with the bot."""
    api = bot.api  # provided by UEXBot
    await bot.add_cog(Category(bot, api, bot.i18n, bot.lang_prefs))
