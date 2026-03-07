"""Draft engine for Altered TCG draft tool — pure logic, no Streamlit."""

import json
import os
import random
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Any

# Path to the bundled card data
DATA_DIR = Path(__file__).parent / "data"

# Factions
FACTIONS = ["AX", "BR", "LY", "MU", "OR", "YZ"]

# Rarity references
RARITY_COMMON = "COMMON"
RARITY_RARE = "RARE"
RARITY_EXALTED = "EXALTED"
RARITY_UNIQUE = "UNIQUE"

# Card type
CARD_TYPE_HERO = "HERO"

# Draft constraints
TOTAL_PICKS = 40
RARE_SLOTS = 15
COMMON_EXALTED_SLOTS = 24
HERO_SLOTS = 1
MAX_COPIES = 3
CHOICES_PER_PICK = 3


def load_collection_from_zip(zip_bytes: bytes) -> list[dict[str, Any]]:
    """Parse a ZIP file containing JSON card files and return the card list."""
    cards: list[dict[str, Any]] = []
    with zipfile.ZipFile(BytesIO(zip_bytes), "r") as zf:
        for name in zf.namelist():
            if not name.endswith(".json"):
                continue
            try:
                data = json.loads(zf.read(name))
            except (json.JSONDecodeError, KeyError):
                continue
            # Handle both single-card files and list-of-cards files
            if isinstance(data, list):
                cards.extend(data)
            elif isinstance(data, dict):
                cards.append(data)
    return cards


def load_collection_from_data_dir() -> list[dict[str, Any]]:
    """Load card collection from the bundled data/ directory.

    Supports:
    - A ZIP file in data/ (first .zip found)
    - Individual JSON files in data/ (and subdirectories)
    """
    cards: list[dict[str, Any]] = []

    # Try ZIP first
    zip_files = list(DATA_DIR.glob("*.zip"))
    if zip_files:
        with open(zip_files[0], "rb") as f:
            return load_collection_from_zip(f.read())

    # Otherwise, load all JSON files recursively
    for json_path in DATA_DIR.rglob("*.json"):
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue
        if isinstance(data, list):
            cards.extend(data)
        elif isinstance(data, dict):
            cards.append(data)

    return cards


def has_bundled_data() -> bool:
    """Check if card data exists in the data/ directory."""
    if not DATA_DIR.exists():
        return False
    has_zip = any(DATA_DIR.glob("*.zip"))
    has_json = any(DATA_DIR.rglob("*.json"))
    return has_zip or has_json


def _get_ref(card: dict) -> str:
    return card.get("reference", "")


def _get_faction(card: dict) -> str:
    faction = card.get("mainFaction")
    if isinstance(faction, dict):
        return faction.get("reference", "")
    return ""


def _get_rarity(card: dict) -> str:
    rarity = card.get("rarity")
    if isinstance(rarity, dict):
        return rarity.get("reference", "")
    return ""


def _get_card_type(card: dict) -> str:
    ct = card.get("cardType")
    if isinstance(ct, dict):
        return ct.get("reference", "")
    return ""


def _is_banned(card: dict) -> bool:
    return bool(card.get("isBanned", False))


def _get_name(card: dict) -> str:
    return card.get("name", "Unknown")


def _get_cost(card: dict) -> str:
    elements = card.get("elements", {})
    return elements.get("MAIN_COST", "?")


def _get_effect(card: dict) -> str:
    return card.get("mainEffect", "") or ""


def _get_powers(card: dict) -> dict[str, str]:
    elements = card.get("elements", {})
    powers = {}
    for key in ("MOUNTAIN_POWER", "OCEAN_POWER", "FOREST_POWER"):
        if key in elements:
            powers[key] = elements[key]
    return powers


def _is_alt_art(card: dict) -> bool:
    """Check if a card is an alternate art variant (A or P prefix)."""
    ref = _get_ref(card)
    parts = ref.split("_")
    # Pattern: ALT_CORE_[A|B|P]_FACTION_NUM_RARITY
    if len(parts) >= 3 and parts[2] in ("A", "P"):
        return True
    return False


def filter_collection(cards: list[dict]) -> list[dict]:
    """Remove banned cards, uniques, tokens, and alternate art from the collection."""
    return [
        c for c in cards
        if not _is_banned(c)
        and _get_rarity(c) != RARITY_UNIQUE
        and not _is_alt_art(c)
        and _get_card_type(c) not in ("TOKEN", "TOKEN_MANA")
    ]


def get_cards_by_faction_and_rarity(
    cards: list[dict],
    faction: str,
    rarities: list[str],
    exclude_heroes: bool = True,
) -> list[dict]:
    """Filter cards by faction and rarity set."""
    result = []
    for c in cards:
        if _get_faction(c) != faction:
            continue
        if _get_rarity(c) not in rarities:
            continue
        if exclude_heroes and _get_card_type(c) == CARD_TYPE_HERO:
            continue
        result.append(c)
    return result


def get_heroes(cards: list[dict], faction: str) -> list[dict]:
    """Get hero cards for a faction, deduplicated by name."""
    seen_names: set[str] = set()
    result = []
    for c in cards:
        if _get_faction(c) != faction or _get_card_type(c) != CARD_TYPE_HERO:
            continue
        name = _get_name(c)
        if name in seen_names:
            continue
        seen_names.add(name)
        result.append(c)
    return result


def available_for_pick(
    pool: list[dict], copies_picked: dict[str, int]
) -> list[dict]:
    """Return cards from pool that haven't reached MAX_COPIES yet."""
    return [c for c in pool if copies_picked.get(_get_ref(c), 0) < MAX_COPIES]


def draw_choices(pool: list[dict], n: int = CHOICES_PER_PICK) -> list[dict]:
    """Draw n distinct cards from pool (by name), randomly.

    Ensures no two proposed cards share the same name (e.g. R1 vs R2 variants).
    """
    if not pool:
        return []
    # Group by name to avoid proposing variants of the same card
    by_name: dict[str, list[dict]] = {}
    for c in pool:
        by_name.setdefault(_get_name(c), []).append(c)
    names = list(by_name.keys())
    if len(names) <= n:
        return [random.choice(by_name[name]) for name in names]
    chosen_names = random.sample(names, n)
    return [random.choice(by_name[name]) for name in chosen_names]


# ---------------------------------------------------------------------------
# Draft state helpers
# ---------------------------------------------------------------------------

def init_draft_state(collection: list[dict]) -> dict[str, Any]:
    """Create initial draft state after collection is loaded."""
    filtered = filter_collection(collection)
    return {
        "collection": filtered,
        "faction": None,
        "phase": "FACTION_PICK",
        "pick_index": 1,
        "rare_slots": RARE_SLOTS,
        "common_exalted_slots": COMMON_EXALTED_SLOTS,
        "copies_picked": {},
        "picks": [],
        "current_choices": None,
    }


def generate_faction_choices(state: dict) -> list[dict]:
    """Generate 3 rare cards from 3 random factions for pick 1."""
    factions = random.sample(FACTIONS, 3)
    choices = []
    for f in factions:
        pool = get_cards_by_faction_and_rarity(
            state["collection"], f, [RARITY_RARE]
        )
        pool = available_for_pick(pool, state["copies_picked"])
        if pool:
            choices.append(random.choice(pool))
    return choices


def determine_pick_type(state: dict) -> str:
    """Determine if the next pick (2-39) is RARE or COMMON_EXALTED."""
    rare_left = state["rare_slots"]
    ce_left = state["common_exalted_slots"]
    if rare_left <= 0:
        return "COMMON_EXALTED"
    if ce_left <= 0:
        return "RARE"
    return random.choice(["RARE", "COMMON_EXALTED"])


def generate_main_choices(state: dict) -> tuple[str, list[dict]]:
    """Generate choices for picks 2-39. Returns (pick_type, choices)."""
    pick_type = determine_pick_type(state)
    faction = state["faction"]

    if pick_type == "RARE":
        pool = get_cards_by_faction_and_rarity(
            state["collection"], faction, [RARITY_RARE]
        )
    else:
        pool = get_cards_by_faction_and_rarity(
            state["collection"], faction, [RARITY_COMMON, RARITY_EXALTED]
        )

    pool = available_for_pick(pool, state["copies_picked"])
    choices = draw_choices(pool)
    return pick_type, choices


def generate_hero_choices(state: dict) -> list[dict]:
    """Generate ALL hero choices for pick 40."""
    pool = get_heroes(state["collection"], state["faction"])
    return pool  # Return all heroes, not just 3


def apply_pick(state: dict, card: dict, pick_type: str | None = None) -> None:
    """Apply a pick: update copies, slots, picks list, and advance phase."""
    ref = _get_ref(card)
    state["copies_picked"][ref] = state["copies_picked"].get(ref, 0) + 1
    state["picks"].append(card)

    phase = state["phase"]

    if phase == "FACTION_PICK":
        state["faction"] = _get_faction(card)
        state["rare_slots"] -= 1
        state["pick_index"] = 2
        if state["pick_index"] <= 39:
            state["phase"] = "MAIN_DRAFT"
        else:
            state["phase"] = "HERO_PICK"

    elif phase == "MAIN_DRAFT":
        if pick_type == "RARE":
            state["rare_slots"] -= 1
        else:
            state["common_exalted_slots"] -= 1
        state["pick_index"] += 1
        if state["pick_index"] > 39:
            state["phase"] = "HERO_PICK"

    elif phase == "HERO_PICK":
        state["pick_index"] = 40
        state["phase"] = "DONE"

    state["current_choices"] = None


# ---------------------------------------------------------------------------
# Deck summary helpers
# ---------------------------------------------------------------------------

def build_deck_summary(picks: list[dict]) -> dict[str, list[tuple[str, str, int]]]:
    """Group picks by rarity. Returns {rarity: [(name, ref, count), ...]}."""
    counts: dict[str, int] = {}
    card_map: dict[str, dict] = {}
    for c in picks:
        ref = _get_ref(c)
        counts[ref] = counts.get(ref, 0) + 1
        card_map[ref] = c

    grouped: dict[str, list[tuple[str, str, int]]] = {
        "HERO": [],
        "RARE": [],
        "EXALTED": [],
        "COMMON": [],
    }
    for ref, count in counts.items():
        card = card_map[ref]
        rarity = _get_rarity(card)
        name = _get_name(card)
        ct = _get_card_type(card)
        if ct == CARD_TYPE_HERO:
            grouped["HERO"].append((name, ref, count))
        elif rarity in grouped:
            grouped[rarity].append((name, ref, count))
        else:
            grouped.setdefault(rarity, []).append((name, ref, count))

    return grouped


def export_deck_text(picks: list[dict]) -> str:
    """Export deck as a text list."""
    summary = build_deck_summary(picks)
    lines = ["=== Altered Draft Deck ===", ""]
    for rarity in ("HERO", "RARE", "EXALTED", "COMMON"):
        entries = summary.get(rarity, [])
        if not entries:
            continue
        lines.append(f"--- {rarity} ---")
        for name, _ref, count in sorted(entries):
            if rarity == "HERO":
                lines.append(f"  {name}")
            else:
                lines.append(f"  {name} x{count}")
        lines.append("")
    lines.append(f"Total: {len(picks)} cards")
    return "\n".join(lines)
