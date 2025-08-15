#!/usr/bin/env python3
"""
Update en.json from UEX API and generate/merge uk locales (no external deps).

Default (без аргументів):
  - тягне /2.0/categories
  - оновлює locales/en.json (identity: англ = дані API)
  - створює/оновлює locales/uk.todo.json тільки з відсутніми ключами

--merge-uk
  - зливає переклади з locales/uk.todo.json у locales/uk.json
  - пусті значення ігнорує (залишає старе uk.json)
  - робить бекап uk.json у uk.json.bak

--fill-empty-uk-from-en
  - додатково заповнює порожні значення в uk.json англійськими (як тимчасовий fallback)

Приклади:
  python3 scripts/update_locales.py
  python3 scripts/update_locales.py --merge-uk
  python3 scripts/update_locales.py --merge-uk --fill-empty-uk-from-en
"""
from __future__ import annotations
import json, os, sys
from pathlib import Path
from typing import Dict, Any, Set
import urllib.request

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOCALES_DIR = PROJECT_ROOT / "locales"
EN_JSON  = LOCALES_DIR / "en.json"
UK_JSON  = LOCALES_DIR / "uk.json"
UK_TODO  = LOCALES_DIR / "uk.todo.json"

def load_json(path: Path) -> Dict[str, Any]:
    if not path.exists(): return {}
    with path.open("r", encoding="utf-8") as f: return json.load(f)

def save_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f: json.dump(data, f, ensure_ascii=False, indent=2)

def fetch_categories() -> list[dict]:
    url = "https://api.uexcorp.space/2.0/categories"
    headers = {"Accept": "application/json", "User-Agent": "UEXLocaleTool/1.0"}
    token = os.getenv("UEX_API_TOKEN")
    if token: headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers, method="GET")
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.load(resp)
        return data.get("data", []) or []

def update_en_and_todo() -> None:
    cats = fetch_categories()
    types, sections, names = set(), set(), set()
    for c in cats:
        t = str(c.get("type","")).strip()
        s = str(c.get("section","")).strip()
        n = str(c.get("name","")).strip()
        if t: types.add(t)
        if s: sections.add(s)
        if n: names.add(n)

    # identity-блоки для en
    en_new = {
        "type_map":   {k: k for k in sorted(types)},
        "section_map":{k: k for k in sorted(sections)},
        "categories": {k: k for k in sorted(names)},
    }

    en = load_json(EN_JSON)
    for block in ("type_map","section_map","categories"):
        exist = en.get(block) if isinstance(en.get(block), dict) else {}
        merged = dict(exist or {})
        for k, v in en_new[block].items():
            merged.setdefault(k, v)
        en[block] = merged
    en.setdefault("ui", en.get("ui", {}))
    en.setdefault("labels", en.get("labels", {
        "id":"ID","name":"Name","type":"Type","section":"Section",
        "in_game":"In-game","mining_related":"Mining-related","yes":"yes","no":"no"
    }))
    save_json(EN_JSON, en)

    uk = load_json(UK_JSON)
    uk_types = uk.get("type_map", {}) if isinstance(uk.get("type_map"), dict) else {}
    uk_sections = uk.get("section_map", {}) if isinstance(uk.get("section_map"), dict) else {}
    uk_categories = uk.get("categories", {}) if isinstance(uk.get("categories"), dict) else {}
    missing = {
        "type_map":   {k: "" for k in sorted(types) if k not in uk_types},
        "section_map":{k: "" for k in sorted(sections) if k not in uk_sections},
        "categories": {k: "" for k in sorted(names) if k not in uk_categories},
    }
    missing = {k: v for k, v in missing.items() if v}
    save_json(UK_TODO, missing)

    print(f"[locales] en.json updated -> {EN_JSON.relative_to(PROJECT_ROOT)}")
    print(f"[locales] missing uk keys -> {UK_TODO.relative_to(PROJECT_ROOT)}" if missing else "[locales] uk.json is complete")

def merge_uk(fill_empty_from_en: bool = False) -> None:
    uk = load_json(UK_JSON)
    todo = load_json(UK_TODO)
    en = load_json(EN_JSON)

    # гарантуємо блоки
    for block in ("type_map","section_map","categories"):
        if not isinstance(uk.get(block), dict): uk[block] = {}
        if not isinstance(todo.get(block), dict): todo[block] = {}
        if not isinstance(en.get(block), dict): en[block] = {}

    changed = 0
    for block in ("type_map","section_map","categories"):
        for k, v in todo[block].items():
            if isinstance(v, str) and v.strip():  # беремо тільки заповнені
                if uk[block].get(k) != v:
                    uk[block][k] = v
                    changed += 1
            elif fill_empty_from_en and k in en[block]:
                # опційно: заповнюємо англійським, якщо лишили пусто
                if uk[block].get(k) != en[block][k]:
                    uk[block][k] = en[block][k]
                    changed += 1

    if changed:
        # бекап
        backup = UK_JSON.with_suffix(".json.bak")
        save_json(backup, load_json(UK_JSON))
        save_json(UK_JSON, uk)
        print(f"[locales] uk.json merged ({changed} entries). Backup: {backup.relative_to(PROJECT_ROOT)}")
    else:
        print("[locales] Nothing to merge (no filled values in uk.todo.json).")

if __name__ == "__main__":
    args = set(sys.argv[1:])
    if "--merge-uk" in args:
        merge_uk(fill_empty_from_en="--fill-empty-uk-from-en" in args)
    else:
        update_en_and_todo()
