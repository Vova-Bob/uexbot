"""
General commands for interacting with the UEX API.

This cog defines slash commands with Ukrainian descriptions and autocomplete.
Important: UEX /categories has ONLY a list endpoint. We fetch the list and
filter locally (no /categories/{id}). For items, the API requires a category,
so we expose a command to list items by selected category.
"""

from __future__ import annotations

import asyncio
import re
from typing import List, Optional, Tuple

import discord
from discord.ext import commands
from discord import app_commands

from uex_api import UEXAPI
from utils import format_category, format_items_list, send_embed


def _is_int(text: str) -> bool:
    """Returns True if text contains only digits."""
    return bool(re.fullmatch(r"\d+", (text or "").strip()))

def _norm(text: str) -> str:
    """Simple lowercase trim for comparisons."""
    return (text or "").strip().lower()


class General(commands.Cog):
    """Cog containing general slash commands for the UEX bot."""

    def __init__(self, bot: commands.Bot, api: UEXAPI) -> None:
        self.bot = bot
        self.api = api
        self._categories_cache: Tuple[float, List[dict]] = (0.0, [])

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        """Event handler triggered when the bot is ready."""
        print(f"Loaded cog: {self.__class__.__name__}")

    # ---------------- categories helpers ----------------
    async def _load_categories(self) -> List[dict]:
        """Load categories with a tiny 60s cache to be gentle with the API."""
        now = asyncio.get_event_loop().time()
        ts, cached = self._categories_cache
        if cached and (now - ts) < 60:
            return cached
        cats = await self.api.get_categories()
        self._categories_cache = (now, cats)
        return cats

    async def _find_category(self, query: str) -> Optional[dict]:
        """Find category by numeric ID or name (exact, startswith, contains)."""
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
        """Autocomplete by category name; pass category ID as string value."""
        try:
            cats = await self._load_categories()
        except Exception:
            return []
        cur = _norm(current)
        if not cur:
            subset = cats[:20]
        else:
            starts = [c for c in cats if _norm(c.get("name", "")).startswith(cur)]
            contains = [c for c in cats if cur in _norm(c.get("name", "")) and c not in starts]
            subset = (starts + contains)[:20]
        return [
            app_commands.Choice(
                name=f'{c.get("name")} (ID: {c.get("id")})',
                value=str(c.get("id"))
            )
            for c in subset
        ]

    # ---------------- slash commands ----------------
    @app_commands.command(
        name="category",
        description="Показати інформацію про категорію (ID або назва; є автодоповнення)",
    )
    @app_commands.describe(
        category="ID або назва категорії (виберіть зі списку або введіть вручну)"
    )
    @app_commands.autocomplete(category=category_autocomplete)
    async def category(self, interaction: discord.Interaction, category: str) -> None:
        """Return details about a specific category using /categories list + local filter."""
        try:
            cat = await self._find_category(category)
        except Exception as exc:
            await send_embed(interaction, "Помилка", f"Не вдалося знайти категорію: {exc}")
            return
        if not cat:
            await send_embed(interaction, "Немає даних", "Категорію не знайдено")
            return
        await send_embed(
            interaction,
            f'Категорія: {cat.get("name")} (ID: {cat.get("id")})',
            format_category(cat),
        )

    @app_commands.command(
        name="items_by_category",
        description="Показати предмети за категорією (вибір із підказки)",
    )
    @app_commands.describe(
        category="ID або назва категорії (автодоповнення за назвою)"
    )
    @app_commands.autocomplete(category=category_autocomplete)
    async def items_by_category(self, interaction: discord.Interaction, category: str) -> None:
        """List items that belong to a chosen category (API requires id_category)."""
        try:
            cat = await self._find_category(category)
        except Exception as exc:
            await send_embed(interaction, "Помилка", f"Не вдалося знайти категорію: {exc}")
            return
        if not cat:
            await send_embed(interaction, "Немає даних", "Категорію не знайдено")
            return

        try:
            items = await self.api.get_items_by_category(int(cat["id"]))
        except Exception as exc:
            await send_embed(interaction, "Помилка", f"Не вдалося отримати предмети: {exc}")
            return

        if not items:
            await send_embed(
                interaction,
                "Немає даних",
                f'Для категорії **{cat.get("name")}** (ID: {cat.get("id")}) предмети відсутні.',
            )
            return

        await send_embed(
            interaction,
            f'Предмети категорії: {cat.get("name")} (ID: {cat.get("id")})',
            format_items_list(items[:25]),  # keep it compact
        )

    @app_commands.command(name="ping", description="Перевірити затримку бота")
    async def ping(self, interaction: discord.Interaction) -> None:
        """Simple ping command to check bot latency."""
        latency_ms = round(self.bot.latency * 1000)
        await interaction.response.send_message(f"Понг! Затримка: {latency_ms} мс")


async def setup(bot: commands.Bot) -> None:
    """Asynchronous setup function to load the General cog."""
    api = bot.get_cog("APIClient")  # type: ignore
    if api is None:
        from uex_api import get_api_from_env
        api_client = get_api_from_env()
    else:
        api_client = api.api  # type: ignore
    await bot.add_cog(General(bot, api_client))
