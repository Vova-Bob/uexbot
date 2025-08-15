#!/usr/bin/env python3
"""
Extract i18n keys from UEX API to help localization.

What it does:
- Fetches all categories from /2.0/categories
- Collects unique values for:
  * type_map   -> from category["type"]
  * section_map-> from category["section"]
  * categories -> from category["name"]
- Compares with existing locales/uk.json and writes missing keys to locales/uk.todo.json

Run:
  python scripts/extract_i18n_keys.py
"""

from __future__ import annotations
import json
from pathlib import Path
from typing import Dict, Any, Set

# Optional .env loading (does nothing if lib is absent)
try:
    from dotenv import load_dotenv  # type: ignore
    load_dotenv()
except Exception:
    pass

from utils.uex_api import get_api_from_env


PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOCALES_DIR = PROJECT_ROOT / "locales"
UK_JSON      = LOCALES_DIR / "uk.json"
TODO_JSON    = LOCALES_DIR / "uk.todo.json"


def load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def main() -> None:
    api = get_api_from_env()

    # 1) Fetch all categories
    #    /categories does not need token, but it's ok if present
    cats = []
    try:
        cats = __import__("asyncio").get_event_loop().run_until_complete(api.get_categories())
    finally:
        __import__("asyncio").get_event_loop().run_until_complete(api.close())

    # 2) Collect unique keys
    types: Set[str] = set()
    sections: Set[str] = set()
    names: Set[str] = set()

    for c in cats:
        t = str(c.get("type", "")).strip()
        s = str(c.get("section", "")).strip()
        n = str(c.get("name", "")).strip()
        if t: types.add(t)
        if s: sections.add(s)
        if n: names.add(n)

    # 3) Load existing uk.json (to preserve what is already translated)
    uk = load_json(UK_JSON)
    uk_types = (uk.get("type_map") or {}) if isinstance(uk.get("type_map"), dict) else {}
    uk_sections = (uk.get("section_map") or {}) if isinstance(uk.get("section_map"), dict) else {}
    uk_categories = (uk.get("categories") or {}) if isinstance(uk.get("categories"), dict) else {}

    # 4) Compute missing keys only
    missing = {
        "type_map": {k: "" for k in sorted(types) if k not in uk_types},
        "section_map": {k: "" for k in sorted(sections) if k not in uk_sections},
        "categories": {k: "" for k in sorted(names) if k not in uk_categories},
    }

    # 5) Drop empty groups to keep file clean
    missing = {k: v for k, v in missing.items() if v}

    # 6) Ensure locales dir exists and write todo json
    LOCALES_DIR.mkdir(parents=True, exist_ok=True)
    with TODO_JSON.open("w", encoding="utf-8") as f:
        json.dump(missing, f, ensure_ascii=False, indent=2)

    # 7) Print short summary
    print(f"[i18n] collected: types={len(types)} sections={len(sections)} categories={len(names)}")
    print(f"[i18n] missing -> {TODO_JSON.relative_to(PROJECT_ROOT)}")
    if not missing:
        print("[i18n] No missing keys. uk.json is up-to-date.")


if __name__ == "__main__":
    main()
