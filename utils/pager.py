"""Reusable pagination view."""
from __future__ import annotations

from typing import List

import discord

from utils.i18n import I18N


class BasePaginatorView(discord.ui.View):
    """Simple local paginator with prev/next buttons."""

    def __init__(
        self,
        *,
        items: List[dict],
        i18n: I18N,
        lang: str,
        user_id: int,
        page_size: int = 25,
        timeout: float = 120.0,
    ) -> None:
        super().__init__(timeout=timeout)
        self.items_all = items
        self.total = len(items)
        self.i18n = i18n
        self.lang = lang
        self.user_id = user_id
        self.page_size = page_size
        self.offset = 0

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
        raise NotImplementedError

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
        last_start = max(0, self.total - self.page_size)
        self.offset = min(self.offset + self.page_size, last_start)
        self._update_buttons()
        await interaction.response.edit_message(embed=self._embed(), view=self)

