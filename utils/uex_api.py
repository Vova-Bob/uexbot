"""
Simple asynchronous client for the UEX API.

- Uses aiohttp with a shared session
- Optional Bearer token (not needed for /categories)
- KISS/DRY: minimal surface, small helpers
- Gentle retry for HTTP 429 (rate limit)
"""

from __future__ import annotations

import os
import asyncio
from typing import Any, Dict, List, Optional

import aiohttp


__all__ = ["UEXAPI", "get_api_from_env"]


class UEXAPI:
    """Asynchronous wrapper for interacting with the UEX API."""

    BASE_URL = "https://api.uexcorp.space/2.0"
    TIMEOUT = aiohttp.ClientTimeout(total=15)  # seconds
    RETRIES = 3  # retries on 429

    def __init__(self, token: Optional[str] = None, base_url: Optional[str] = None) -> None:
        """Create a new UEXAPI client with optional bearer token."""
        self._token = token
        self._base = base_url or self.BASE_URL
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Ensure there is an aiohttp ClientSession and return it."""
        if self._session is None or self._session.closed:
            headers = {"Accept": "application/json", "User-Agent": "UEXDiscordBot/1.0"}
            if self._token:  # add Bearer only if present
                headers["Authorization"] = f"Bearer {self._token}"
            self._session = aiohttp.ClientSession(headers=headers, timeout=self.TIMEOUT)
        return self._session

    async def close(self) -> None:
        """Close the underlying aiohttp session."""
        if self._session and not self._session.closed:
            await self._session.close()

    # ------------------- low-level GET -------------------
    async def get(self, resource: str, **params: Any) -> Dict[str, Any]:
        """Perform a GET request against a specific resource with simple 429 retry."""
        session = await self._get_session()
        url = f"{self._base}/{resource}"

        for attempt in range(1, self.RETRIES + 1):
            async with session.get(url, params=params) as resp:
                if resp.status == 429 and attempt < self.RETRIES:
                    # Respect Retry-After if present; fallback to small backoff
                    retry_after = resp.headers.get("Retry-After")
                    delay = float(retry_after) if retry_after else 1.0 * attempt
                    await asyncio.sleep(delay)
                    continue
                resp.raise_for_status()
                return await resp.json()

        # If loop exits without return, raise last response error
        async with session.get(url, params=params) as resp:
            resp.raise_for_status()
            return await resp.json()

    # ------------------- categories -------------------
    async def get_categories(
        self,
        type: Optional[str] = None,
        section: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Fetch categories list. The API provides only list endpoint (no /categories/{id})."""
        params: Dict[str, Any] = {}
        if type:
            params["type"] = type
        if section:
            params["section"] = section
        data = await self.get("categories", **params)
        return data.get("data", []) or []

    async def search_categories(self, query: str, limit: int = 25) -> List[Dict[str, Any]]:
        """Local-search categories by name for autocomplete (case-insensitive)."""
        cats = await self.get_categories()
        q = (query or "").strip().lower()
        if not q:
            return cats[:limit]
        starts = [c for c in cats if c.get("name", "").lower().startswith(q)]
        contains = [c for c in cats if q in c.get("name", "").lower() and c not in starts]
        return (starts + contains)[:limit]

    async def get_category_by_id_local(self, category_id: int) -> Optional[Dict[str, Any]]:
        """Return one category by ID by filtering the /categories list locally."""
        cats = await self.get_categories()
        for c in cats:
            if c.get("id") == category_id:
                return c
        return None

    # ------------------- items -------------------
    # NOTE: /items requires id_category OR id_company OR uuid.
    # We expose helpers that respect this rule.
    async def get_items_by_category(
        self,
        category_id: int,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """Fetch items for a given category (respects API contract)."""
        params = {"id_category": category_id, "limit": limit, "offset": offset}
        data = await self.get("items", **params)
        return data.get("data", []) or []


# Helper to create UEXAPI client from environment
def get_api_from_env() -> UEXAPI:
    """Instantiate UEXAPI using token from the environment (UEX_API_TOKEN, optional)."""
    token = os.getenv("UEX_API_TOKEN")  # token is optional for /categories
    return UEXAPI(token)
