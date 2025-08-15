"""
Utility functions for the UEX Discord bot.

Contains helpers for embeds and formatting API responses.
"""

from typing import Dict, Any, List

import discord


async def send_embed(interaction: discord.Interaction, title: str, description: str) -> None:
    """Send a simple embed with title and description."""
    embed = discord.Embed(title=title, description=description, color=0x2b6cb0)
    await interaction.response.send_message(embed=embed)


def format_category(category: Dict[str, Any]) -> str:
    """Format a category object into a readable multiline string."""
    # Protect against missing keys
    cid = category.get("id", "-")
    ctype = category.get("type", "-")
    section = category.get("section", "-")
    name = category.get("name", "-")
    igr = category.get("is_game_related", 0)
    imine = category.get("is_mining", 0)
    return (
        f"ID: **{cid}**\n"
        f"Назва: **{name}**\n"
        f"Тип: **{ctype}** | Розділ: **{section}**\n"
        f"In-game: **{('так' if igr else 'ні')}** | Mining-related: **{('так' if imine else 'ні')}**"
    )


def format_items_list(items: List[Dict[str, Any]]) -> str:
    """Format a compact list of items (first N)."""
    lines: List[str] = []
    for it in items:
        iid = it.get("id", "-")
        name = it.get("name", "Без назви")
        code = it.get("code") or ""
        code_part = f" (`{code}`)" if code else ""
        lines.append(f"• **{name}**{code_part} — ID: `{iid}`")
    return "\n".join(lines[:50]) or "—"
