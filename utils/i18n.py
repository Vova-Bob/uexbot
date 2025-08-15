"""
Lightweight i18n loader with JSON dictionaries and per-guild prefs.

- Loads <project_root>/locales/{lang}.json
- Fallback chain: requested -> default -> key-as-text
- Simple formatter: t("ui.category_title", name="...", id=123)
- Category name translation: tc("Power Plants", lang)
- Guild prefs persisted in <project_root>/data/lang_prefs.json
"""
from __future__ import annotations

import json
import os
import threading
from typing import Any, Dict, Optional

# Resolve paths relative to the project root (parent of utils/)
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_THIS_DIR)

_LOCALES_DIR = os.path.join(_PROJECT_ROOT, "locales")
_PREFS_DIR = os.path.join(_PROJECT_ROOT, "data")
_PREFS_PATH = os.path.join(_PREFS_DIR, "lang_prefs.json")


class I18N:
    """In-memory i18n store with JSON locales and simple formatting."""

    def __init__(self, default: str = "uk") -> None:
        self.default = default
        self._lock = threading.Lock()
        self._dicts: Dict[str, Dict[str, Any]] = {}
        # Preload known locales; add more codes if you ship more files
        for lang in ("en", "uk"):
            self._dicts[lang] = self._load(lang)

    def _load(self, lang: str) -> Dict[str, Any]:
        """Load one locale JSON; return empty dict on failure."""
        path = os.path.join(_LOCALES_DIR, f"{lang}.json")
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def available_languages(self) -> Dict[str, bool]:
        """Return a map of available language codes -> True/False."""
        out: Dict[str, bool] = {}
        try:
            for fn in os.listdir(_LOCALES_DIR):
                if fn.endswith(".json"):
                    out[os.path.splitext(fn)[0]] = True
        except Exception:
            pass
        return out

    def t(self, key: str, lang: Optional[str] = None, **vars: Any) -> str:
        """Translate UI key with optional str.format(**vars)."""
        lang = lang or self.default
        val = self._get(self._dicts.get(lang, {}), key)
        if val is None:
            val = self._get(self._dicts.get(self.default, {}), key)
        if val is None:
            return key  # last resort: show the key itself
        try:
            return val.format(**vars)
        except Exception:
            return val

    def tc(self, name: str, lang: Optional[str] = None) -> str:
        """Translate category/item name by exact key; fallback to original."""
        lang = lang or self.default
        mapping = self._dicts.get(lang, {}).get("categories", {})
        if isinstance(mapping, dict) and name in mapping:
            return mapping[name]
        return name

    def _get(self, obj: Dict[str, Any], dotted: str) -> Any | None:
        """Get nested value by dotted path, e.g. 'ui.category_title'."""
        cur: Any = obj
        for part in dotted.split("."):
            if not isinstance(cur, dict) or part not in cur:
                return None
            cur = cur[part]
        return cur


class LangPrefs:
    """Per-guild language storage persisted to JSON under <project_root>/data/."""

    def __init__(self, default: str = "uk") -> None:
        self.default = default
        os.makedirs(_PREFS_DIR, exist_ok=True)
        try:
            with open(_PREFS_PATH, "r", encoding="utf-8") as f:
                self._data = json.load(f)
        except Exception:
            self._data = {}

    def get(self, guild_id: int | None) -> str:
        """Return guild language or default if not set/DMs."""
        if not guild_id:
            return self.default
        return self._data.get(str(guild_id), self.default)

    def set(self, guild_id: int, lang: str) -> None:
        """Persist guild language to JSON atomically."""
        self._data[str(guild_id)] = lang
        tmp = _PREFS_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, _PREFS_PATH)
