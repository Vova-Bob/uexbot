"""
/items_by_category with i18n + ephemeral + real pagination.
Стратегія: один запит на всі елементи (великий limit), далі пагінація локально.
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
from utils.utils import format_items_list, send_embed_factory
from utils.i18n import I18N, LangPrefs
from utils.cache import load_json_cache, save_json_cache


def _norm(text: str) -> str:
    return (text or "").strip().lower()


def _is_int(text: str) -> bool:
    return bool(re.fullmatch(r"\d+", (text or "").strip()))


class ItemsPaginatorView(discord.ui.View):
    """Локальна пагінація (без додаткових запитів до API)."""

    def __init__(
        self,
        *,
        items_all: List[dict],
        i18n: I18N,
        lang: str,
        category_id: int,
        category_name: str,
        user_id: int,
        page_size: int = 25,
        timeout: float = 120.0,
    ) -> None:
        super().__init__(timeout=timeout)
        self.items_all = items_all
        self.total = len(items_all)
        self.i18n = i18n
        self.lang = lang
        self.category_id = category_id
        self.category_name = category_name
        self.user_id = user_id
        self.page_size = page_size
        self.offset = 0  # починаємо з першої сторінки

        # Кнопки
        self.prev_btn = discord.ui.Button(
            label=f"◀ {i18n.t('ui.nav_prev', lang=lang)}",
            style=discord.ButtonStyle.secondary,
        )
        self.next_btn = discord.ui.Button(
            label=f"{i18n.t('ui.nav_next', lang=lang)} ▶",
            style=discord.ButtonStyle.secondary,
        )
        self.prev_btn.callback = self.on_prev  # type: ignore
        self.next_btn.callback = self.on_next  # type: ignore
        self.add_item(self.prev_btn)
        self.add_item(self.next_btn)

        self._update_buttons()

    # ----- helpers -----
    def _page_slice(self) -> List[dict]:
        return self.items_all[self.offset : self.offset + self.page_size]

    def _update_buttons(self) -> None:
        self.prev_btn.disabled = self.offset <= 0
        self.next_btn.disabled = self.offset + self.page_size >= self.total

    def _embed(self) -> discord.Embed:
        title = self.i18n.t(
            "ui.items_title",
            lang=self.lang,
            name=self.i18n.tc(self.category_name, self.lang),
            id=self.category_id,
        )
        desc = format_items_list(self._page_slice())
        embed = discord.Embed(title=title, description=desc, color=0x2b6cb0)
        page_num = (self.offset // self.page_size) + 1
        embed.set_footer(text=self.i18n.t("ui.page_n", lang=self.lang, n=page_num))
        return embed

    async def _guard(self, interaction: discord.Interaction) -> bool:
        if interaction.user and interaction.user.id == self.user_id:
            return True
        await interaction.response.send_message(
            self.i18n.t("ui.nav_not_author", lang=self.lang), ephemeral=True
        )
        return False

    # ----- callbacks -----
    async def on_prev(self, interaction: discord.Interaction) -> None:
        if not await self._guard(interaction):
            return
        self.offset = max(0, self.offset - self.page_size)
        self._update_buttons()
        await interaction.response.edit_message(embed=self._embed(), view=self)

    async def on_next(self, interaction: discord.Interaction) -> None:
        if not await self._guard(interaction):
            return
        # Перехід на наступну сторінку, але не далі за останній валідний старт
        last_start = max(0, self.total - self.page_size)
        self.offset = min(self.offset + self.page_size, last_start)
        self._update_buttons()
        await interaction.response.edit_message(embed=self._embed(), view=self)


class ItemsByCategory(commands.Cog):
    """Вивід предметів за категорією з локальною пагінацією."""

    def __init__(self, bot: commands.Bot, api: UEXAPI, i18n: I18N, prefs: LangPrefs) -> None:
        self.bot = bot
        self.api = api
        self.i18n = i18n
        self.prefs = prefs

        ephem_env = os.getenv("DEFAULT_EPHEMERAL", "1").lower()
        default_ephemeral = ephem_env in ("1", "true", "yes", "y", "on")
        self._send_embed = send_embed_factory(i18n, default_ephemeral=default_ephemeral)

        seeded = load_json_cache("categories", 24 * 3600) or []
        self._categories_cache: Tuple[float, List[dict]] = (asyncio.get_event_loop().time(), seeded)

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        print(f"Loaded cog: {self.__class__.__name__}")

    async def _load_categories(self) -> List[dict]:
        now = asyncio.get_event_loop().time()
        ts, cached = self._categories_cache
        if cached and (now - ts) < 60:
            return cached
        cats = await self.api.get_categories()
        self._categories_cache = (now, cats)
        save_json_cache("categories", cats)
        return cats

    async def _find_category(self, query: str) -> Optional[dict]:
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
        self, interaction: discord.Interaction, current: str
    ) -> List[app_commands.Choice[str]]:
        try:
            cats = await self._load_categories()
        except Exception:
            return []
        cur = _norm(current)
        subset = (
            cats[:20]
            if not cur
            else (
                [c for c in cats if _norm(c.get("name", "")).startswith(cur)]
                + [c for c in cats if cur in _norm(c.get("name", ""))]
            )[:20]
        )
        lang = self.prefs.get(interaction.guild_id)  # ← фікс
        return [
            app_commands.Choice(
                name=f'{self.i18n.tc(c.get("name", ""), lang)} (ID: {c.get("id")})',
                value=str(c.get("id")),
            )
            for c in subset
        ]

    @app_commands.command(
        name="items_by_category", description="Показати предмети за категорією (вибір із підказки)"
    )
    @app_commands.describe(category="ID або назва категорії (автодоповнення за назвою)")
    @app_commands.autocomplete(category=category_autocomplete)
    async def items_by_category(self, interaction: discord.Interaction, category: str) -> None:
        lang = self.prefs.get(interaction.guild_id)  # ← фікс
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

        # ==== ОДИН РАЗ ТЯГНЕМО ВСЕ, ДАЛІ — ЛОКАЛЬНА ПАГІНАЦІЯ ====
        try:
            data = await self.api.get("items", id_category=int(cat["id"]), limit=5000)
            items_all = data.get("data", []) or []
        except Exception as exc:
            await self._send_embed(
                interaction,
                self.i18n.t("ui.err_no_data", lang=lang),
                self.i18n.t("ui.err_items_fetch", lang=lang, msg=str(exc)),
            )
            return

        if not items_all:
            await self._send_embed(
                interaction,
                self.i18n.t("ui.err_no_data", lang=lang),
                self.i18n.t("ui.err_items_fetch", lang=lang, msg="empty"),
            )
            return

        view = ItemsPaginatorView(
            items_all=items_all,
            i18n=self.i18n,
            lang=lang,
            category_id=int(cat["id"]),
            category_name=cat.get("name", ""),
            user_id=interaction.user.id if interaction.user else 0,
            page_size=25,
        )

        embed = view._embed()
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    api = bot.api
    await bot.add_cog(ItemsByCategory(bot, api, bot.i18n, bot.lang_prefs))
