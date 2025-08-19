"""Trade summary for a commodity:
- Lists buy/sell locations from /commodities_prices
- Computes best route via /commodities_routes
- Profit for chosen ship (SCU from /vehicles) or custom SCU
"""

from __future__ import annotations

import os
import asyncio
from typing import List, Optional, Tuple

import discord
from discord.ext import commands
from discord import app_commands

from utils.uex_api import UEXAPI
from utils.utils import send_embed_factory
from utils.i18n import I18N, LangPrefs
from utils.cache import load_json_cache, save_json_cache


def _norm(text: str) -> str:
    return (text or "").strip().lower()


def _fmt_price(v: float) -> str:
    try:
        return f"{float(v):,.0f}"
    except Exception:
        return str(v)


def _fmt_money(v: float) -> str:
    try:
        return f"{float(v):,.0f} aUEC"
    except Exception:
        return str(v)


class Trade(commands.Cog):
    def __init__(self, bot: commands.Bot, api: UEXAPI, i18n: I18N, prefs: LangPrefs) -> None:
        self.bot = bot
        self.api = api
        self.i18n = i18n
        self.prefs = prefs

        ephem_env = os.getenv("DEFAULT_EPHEMERAL", "1").lower()
        default_ephemeral = ephem_env in ("1", "true", "yes", "y", "on")
        self._send_embed = send_embed_factory(i18n, default_ephemeral=default_ephemeral)

        # day-long caches for lists
        self._commodities_cache: Tuple[float, List[dict]] = (
            asyncio.get_event_loop().time(), load_json_cache("commodities", 24 * 3600) or []
        )
        self._vehicles_cache: Tuple[float, List[dict]] = (
            asyncio.get_event_loop().time(), load_json_cache("vehicles", 24 * 3600) or []
        )

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        print(f"Loaded cog: {self.__class__.__name__}")

    # ---------- data loaders ----------
    async def _load_commodities(self) -> List[dict]:
        now = asyncio.get_event_loop().time()
        ts, cached = self._commodities_cache
        if cached and (now - ts) < 86400:
            return cached
        data = await self.api.get("commodities")
        items = data.get("data", []) or []
        self._commodities_cache = (now, items)
        save_json_cache("commodities", items)
        return items

    async def _load_vehicles(self) -> List[dict]:
        now = asyncio.get_event_loop().time()
        ts, cached = self._vehicles_cache
        if cached and (now - ts) < 86400:
            return cached
        data = await self.api.get_vehicles()
        items = data.get("data", []) or []
        self._vehicles_cache = (now, items)
        save_json_cache("vehicles", items)
        return items

    async def _find_commodity(self, query: str) -> Optional[dict]:
        items = await self._load_commodities()
        if not items:
            return None
        q = _norm(query)
        for c in items:
            if str(c.get("id")) == q:
                return c
        exact = [c for c in items if _norm(c.get("name", "")) == q]
        if exact:
            return exact[0]
        starts = [c for c in items if _norm(c.get("name", "")).startswith(q)]
        if starts:
            return starts[0]
        contains = [c for c in items if q in _norm(c.get("name", ""))]
        return contains[0] if contains else None

    def _vehicle_scu(self, v: dict) -> int:
        """Try to extract cargo capacity (SCU) from vehicle dict using common keys."""
        for k in ("cargo", "cargo_scu", "scu", "cargo_capacity", "cargo_capacity_scu"):
            val = v.get(k)
            if isinstance(val, (int, float)) and val > 0:
                return int(val)
        return 0

    # ---------- autocomplete ----------
    async def commodity_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        try:
            items = await self._load_commodities()
        except Exception:
            return []
        cur = _norm(current)
        subset = (
            items[:20]
            if not cur
            else (
                [c for c in items if _norm(c.get("name", "")).startswith(cur)]
                + [c for c in items if cur in _norm(c.get("name", ""))]
            )[:20]
        )
        lang = self.prefs.get(interaction.guild_id if interaction.guild else None)
        return [
            app_commands.Choice(name=self.i18n.tc(c.get("name", ""), lang), value=str(c.get("id")))
            for c in subset
        ]

    async def ship_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        try:
            vehicles = await self._load_vehicles()
        except Exception:
            return []
        cur = _norm(current)
        names = [v.get("name", "") for v in vehicles if v.get("name")]
        if cur:
            names = [n for n in names if cur in _norm(n)]
        names = names[:20]
        return [app_commands.Choice(name=n, value=n) for n in names]

    # ---------- prices & routes ----------
    async def _load_prices(self, commodity_id: int) -> List[dict]:
        cache_name = f"prices_{commodity_id}"
        cached = load_json_cache(cache_name, 600)  # 10 min
        if cached:
            return cached
        data = await self.api.get_commodities_prices(id_commodity=commodity_id, limit=5000)
        rows = data.get("data", []) or []
        save_json_cache(cache_name, rows)
        return rows

    async def _load_routes(self, commodity_id: int) -> List[dict]:
        cache_name = f"routes_{commodity_id}"
        cached = load_json_cache(cache_name, 600)  # 10 min
        if cached:
            return cached
        data = await self.api.get_commodities_routes(id_commodity=commodity_id)
        rows = data.get("data", []) or []
        save_json_cache(cache_name, rows)
        return rows

    # ---------- helpers ----------
    def _loc_name_from_price(self, r: dict) -> str:
        t = r.get("terminal_name") or r.get("terminal_code") or "?"
        where = (
            r.get("city_name")
            or r.get("space_station_name")
            or r.get("outpost_name")
            or r.get("moon_name")
            or r.get("planet_name")
        )
        return t if not where else f"{t}: {where}"

    def _loc_name_from_route_origin(self, r: dict) -> str:
        t = r.get("origin_terminal_name") or r.get("origin_terminal_code") or "?"
        where = (
            r.get("origin_city_name")
            or r.get("origin_space_station_name")
            or r.get("origin_outpost_name")
            or r.get("origin_orbit_name")
            or r.get("origin_planet_name")
        )
        return t if not where else f"{t}: {where}"

    def _loc_name_from_route_dest(self, r: dict) -> str:
        t = r.get("destination_terminal_name") or r.get("destination_terminal_code") or "?"
        where = (
            r.get("destination_city_name")
            or r.get("destination_space_station_name")
            or r.get("destination_outpost_name")
            or r.get("destination_orbit_name")
            or r.get("destination_planet_name")
        )
        return t if not where else f"{t}: {where}"

    # ---------- command ----------
    @app_commands.command(
        name="trade",
        description="Зведення по товару: де купити/продати + найкращий маршрут (SCU з корабля або вручну).",
    )
    @app_commands.describe(
        commodity="Назва товару (автодоповнення)",
        ship="Корабель (для SCU; автодоповнення з /vehicles)",
        scu="SCU вручну (якщо корабель не обрано або не має даних)",
        top="Скільки локацій показати у списках (3..30, стандарт 10)",
    )
    @app_commands.autocomplete(commodity=commodity_autocomplete, ship=ship_autocomplete)
    async def trade(
        self,
        interaction: discord.Interaction,
        commodity: str,
        ship: Optional[str] = None,
        scu: Optional[int] = None,
        top: Optional[int] = 10,
    ) -> None:
        lang = self.prefs.get(interaction.guild_id if interaction.guild else None)
        top = max(3, min(int(top or 10), 30))

        # 1) resolve commodity
        try:
            comm = await self._find_commodity(commodity)
        except Exception as exc:
            await self._send_embed(
                interaction, self.i18n.t("ui.err_no_data", lang=lang),
                self.i18n.t("ui.err_category_fetch", lang=lang, msg=str(exc)),
            )
            return
        if not comm:
            await self._send_embed(
                interaction, self.i18n.t("ui.err_no_data", lang=lang),
                self.i18n.t("ui.err_no_matches", lang=lang),
            )
            return
        comm_id = int(comm["id"])
        comm_name = self.i18n.tc(comm.get("name", ""), lang)

        # 2) prices
        try:
            prices = await self._load_prices(comm_id)
        except Exception as exc:
            await self._send_embed(
                interaction, self.i18n.t("ui.err_no_data", lang=lang),
                self.i18n.t("ui.err_price_fetch", lang=lang, msg=str(exc)),
            )
            return

        buys = sorted(
            [r for r in prices if (r.get("price_buy") or 0) > 0],
            key=lambda r: r.get("price_buy", 10**9)
        )[:top]

        sells = sorted(
            [r for r in prices if (r.get("price_sell") or 0) > 0],
            key=lambda r: r.get("price_sell", 0), reverse=True
        )[:top]

        # 3) ship SCU (if provided)
        used_scu = 0
        ship_name_out = None
        if scu and int(scu) > 0:
            used_scu = int(scu)
        elif ship:
            try:
                vehicles = await self._load_vehicles()
            except Exception:
                vehicles = []
            for v in vehicles:
                if _norm(v.get("name", "")) == _norm(ship):
                    used_scu = self._vehicle_scu(v)
                    ship_name_out = v.get("name", ship)
                    break

        # 4) routes
        try:
            routes = await self._load_routes(comm_id)
        except Exception as exc:
            routes = []

        # pick best route: by (price_destination - price_origin) * SCU if SCU is known, else by API 'profit' or margin
        best_route = None
        if routes:
            if used_scu > 0:
                def route_profit_for_scu(r: dict) -> float:
                    pb = float(r.get("price_origin") or 0.0)
                    ps = float(r.get("price_destination") or 0.0)
                    return (ps - pb) * used_scu
                best_route = max(routes, key=route_profit_for_scu, default=None)
            else:
                def route_profit_default(r: dict) -> float:
                    # prefer API-calculated profit, fallback to delta price
                    if r.get("profit") is not None:
                        return float(r.get("profit") or 0.0)
                    return float(r.get("price_destination") or 0.0) - float(r.get("price_origin") or 0.0)
                best_route = max(routes, key=route_profit_default, default=None)

        # 5) build embed
        lines: List[str] = []

        # buy section
        lines.append(f"**{self.i18n.t('labels.buy_locations', lang=lang) or 'Локації купівлі:'}**")
        if not buys:
            lines.append(self.i18n.t("ui.no_buy_locations", lang=lang) or "Немає доступних локацій купівлі.")
        else:
            for r in buys:
                lines.append(
                    f"• **{self._loc_name_from_price(r)}** — {self.i18n.t('labels.buy', lang=lang) or 'Купівля'}: **{_fmt_price(r.get('price_buy', 0))}**"
                )

        lines.append("")

        # sell section
        lines.append(f"**{self.i18n.t('labels.sell_locations', lang=lang) or 'Локації продажу:'}**")
        if not sells:
            lines.append(self.i18n.t("ui.no_sell_locations", lang=lang) or "Немає доступних локацій продажу.")
        else:
            for r in sells:
                lines.append(
                    f"• **{self._loc_name_from_price(r)}** — {self.i18n.t('labels.sell', lang=lang) or 'Продаж'}: **{_fmt_price(r.get('price_sell', 0))}**"
                )

        # best route section
        if best_route:
            lines.append("")
            lines.append(f"**{self.i18n.t('labels.best_route', lang=lang) or 'Найприбутковіший маршрут:'}**")
            origin = self._loc_name_from_route_origin(best_route)
            dest = self._loc_name_from_route_dest(best_route)
            pb = float(best_route.get("price_origin") or 0.0)
            ps = float(best_route.get("price_destination") or 0.0)
            lines.append(f"{self.i18n.t('labels.buy', lang=lang) or 'Купити'} за **{_fmt_price(pb)}** у **{origin}**")
            lines.append(f"{self.i18n.t('labels.sell', lang=lang) or 'Продати'} за **{_fmt_price(ps)}** у **{dest}**")

            if used_scu > 0:
                cost = pb * used_scu
                profit = (ps - pb) * used_scu
                if ship_name_out:
                    lines.append(f"{self.i18n.t('labels.ship', lang=lang) or 'Корабель'}: **{ship_name_out}** ({used_scu} SCU)")
                else:
                    lines.append(f"SCU: **{used_scu}**")
                lines.append(f"{self.i18n.t('labels.total_cost', lang=lang) or 'Загальні витрати на закупівлю'}: **{_fmt_money(cost)}**")
                lines.append(f"{self.i18n.t('labels.total_profit', lang=lang) or 'Загальний прибуток'}: **{_fmt_money(profit)}**")
            else:
                lines.append(self.i18n.t("ui.route_no_scu", lang=lang) or "Вкажіть корабель або SCU, щоб порахувати прибуток.")
        else:
            lines.append("")
            lines.append(self.i18n.t("ui.no_profitable_route", lang=lang) or "Немає вигідних маршрутів або локації для купівлі та продажу збігаються.")

        embed = discord.Embed(title=comm_name, description="\n".join(lines), color=0x2b6cb0)

        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    api = bot.api
    await bot.add_cog(Trade(bot, api, bot.i18n, bot.lang_prefs))
