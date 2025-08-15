"""
Utility functions for the UEX Discord bot. Uses i18n for UI texts.
"""
from typing import Dict, Any, List, Optional
import discord
from utils.i18n import I18N


def send_embed_factory(i18n: I18N, default_ephemeral: bool = True):
    """
    Create a sender that posts embeds. By default sends ephemeral (private) messages.

    Args:
        i18n: i18n service
        default_ephemeral: default privacy for messages

    Usage:
        send = send_embed_factory(i18n, default_ephemeral=True)
        await send(interaction, "Title", "Desc")                 # private
        await send(interaction, "Public", "Desc", ephemeral=False)  # public
    """
    async def send_embed(
        interaction: discord.Interaction,
        title: str,
        description: str,
        ephemeral: Optional[bool] = None,
    ) -> None:
        ephem = default_ephemeral if ephemeral is None else ephemeral
        embed = discord.Embed(title=title, description=description, color=0x2b6cb0)

        # If initial response already sent, use followup
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, ephemeral=ephem)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=ephem)

    return send_embed


def format_category(category: Dict[str, Any], i18n: I18N, lang: str) -> str:
    """Format category data for display using translations (type/section mapped)."""
    lbl = i18n.t
    yes = lbl("labels.yes", lang=lang)
    no  = lbl("labels.no",  lang=lang)

    cid = category.get("id", "-")
    name = i18n.tc(category.get("name", "-"), lang)

    # raw values from API
    raw_type = str(category.get("type", "-"))
    raw_section = str(category.get("section", "-"))

    # translate type/section; fallback to raw if key missing
    ctype = i18n.t(f"type_map.{raw_type}", lang=lang)
    if ctype == f"type_map.{raw_type}":
        ctype = raw_type

    section = i18n.t(f"section_map.{raw_section}", lang=lang)
    if section == f"section_map.{raw_section}":
        section = raw_section

    igr = yes if category.get("is_game_related", 0) else no
    miner = yes if category.get("is_mining", 0) else no

    return (
        f"{lbl('labels.id', lang=lang)}: **{cid}**\n"
        f"{lbl('labels.name', lang=lang)}: **{name}**\n"
        f"{lbl('labels.type', lang=lang)}: **{ctype}** | "
        f"{lbl('labels.section', lang=lang)}: **{section}**\n"
        f"{lbl('labels.in_game', lang=lang)}: **{igr}** | "
        f"{lbl('labels.mining_related', lang=lang)}: **{miner}**"
    )


def format_items_list(items: List[Dict[str, Any]]) -> str:
    """Format a list of items for display."""
    lines: List[str] = []
    for it in items[:50]:  # limit to keep embeds compact
        iid = it.get("id", "-")
        name = it.get("name", "Unnamed")
        code = it.get("code") or ""
        code_part = f" (`{code}`)" if code else ""
        lines.append(f"• **{name}**{code_part} — ID: `{iid}`")
    return "\n".join(lines) or "—"
