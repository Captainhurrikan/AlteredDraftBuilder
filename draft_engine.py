"""Draft engine for Altered TCG draft tool — pure logic, no Streamlit."""

import json
import os
import random
import re
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
GROUP_SIZE = 3  # Number of characters per faction group
NUM_GROUPS = 3  # Number of faction groups to propose

# Canonical synergy keyword mapping: pattern (lowercase) → display label.
# Variants (conjugation, gender) map to the same canonical keyword.
# Only bracketed keywords [like this] are matched — no free-text phrases.
SYNERGY_MAP: dict[str, str] = {
    # Core mechanics
    "fugace": "Fugace",
    "ancré": "Ancré",
    "sabotez": "Sabotage",
    "saboter": "Sabotage",
    "ravitaillez": "Ravitaillement",
    "ravitaille": "Ravitaillement",
    "ravitailler": "Ravitaillement",
    "ravitaillez épuisé": "Ravitaillement",
    "ravitaille épuisé": "Ravitaillement",
    "repérage": "Repérage",
    "endormi": "Endormi",
    "en contact": "En Contact",
    "boosté": "Boosté",
    "aguerri": "Aguerri",
    "aguerrie": "Aguerri",
    "s'élève": "Élévation",
    "don": "Don",
    # Named tokens — cards creating the same token truly share a synergy
    "recrue ordis": "Recrue Ordis",
    "graine de mana": "Graine de Mana",
    "scarabot": "Scarabot",
    "phalène de mana": "Phalène de Mana",
    "aérolithe": "Aérolithe",
}

# ---------------------------------------------------------------------------
# Effect-based synergy patterns (detected from free text, not just brackets)
# ---------------------------------------------------------------------------
# Each pattern is (compiled_regex, synergy_tag).
# These capture mechanical themes that create real gameplay synergies
# even when cards don't share the exact same bracketed keyword.

EFFECT_PATTERNS: list[tuple[re.Pattern, str]] = [
    # Boost manipulation — cards that give or consume boosts synergize
    (re.compile(r"gagne \d+ boosts?", re.IGNORECASE), "Boosts"),
    (re.compile(r"perd \d+ boosts?", re.IGNORECASE), "Boosts"),
    (re.compile(r"n'a (?:pas|aucun) (?:de )?boosts?", re.IGNORECASE), "Boosts"),
    # Token creation — cards creating creatures synergize with swarm strategies
    (re.compile(r"cr[ée]{1,2}(?:z|er?) (?:un|deux|trois|\d+) jetons?", re.IGNORECASE), "Création de Jetons"),
    (re.compile(r"create (?:a|two|three|\d+) .* tokens?", re.IGNORECASE), "Création de Jetons"),
    # Expedition movement — positional synergies
    (re.compile(r"exp[ée]dition (?:avance|recule)", re.IGNORECASE), "Mouvement"),
    (re.compile(r"recule d'une r[ée]gion", re.IGNORECASE), "Mouvement"),
    (re.compile(r"avance d'une r[ée]gion", re.IGNORECASE), "Mouvement"),
    # Exhaust / ready mechanics
    (re.compile(r"[ée]puisez|redressez", re.IGNORECASE), "Épuisement"),
    (re.compile(r"\{T\}", re.IGNORECASE), "Épuisement"),
    # Landmark interaction
    (re.compile(r"rep[èe]res?|landmarks?", re.IGNORECASE), "Repères"),
    # Reserve interaction
    (re.compile(r"(?:dans|de) (?:votre |ma )?r[ée]serve", re.IGNORECASE), "Réserve"),
    (re.compile(r"envoyez[- ](?:le|la) en r[ée]serve", re.IGNORECASE), "Réserve"),
    # Dice mechanics
    (re.compile(r"lancez un d[ée]", re.IGNORECASE), "Dé"),
    # Noon triggers
    (re.compile(r"[àa] midi", re.IGNORECASE), "À Midi"),
    # Hand interaction
    (re.compile(r"(?:dans|de) votre main", re.IGNORECASE), "Main"),
    (re.compile(r"piochez|draw", re.IGNORECASE), "Main"),
    # Sacrifice — cards that require sacrificing characters/objects
    (re.compile(r"sacrifiez", re.IGNORECASE), "Sacrifice"),
    # Cooldown spells — go to reserve exhausted
    (re.compile(r"[dD][ée]lai", re.IGNORECASE), "Cooldown Sort"),
]

# ---------------------------------------------------------------------------
# Rules-based synergy interactions
# ---------------------------------------------------------------------------
# Maps pairs of tags that create strong gameplay synergies based on the rules.
# When two cards have tags from the same interaction pair, they synergize
# even if they don't share the exact same tag.
# Format: frozenset({tag_a, tag_b}) → interaction label for display.

# Tags that only count as part of cross-tag interactions (SYNERGY_INTERACTIONS),
# never as direct synergies between two cards sharing the same tag.
COMBO_ONLY_TAGS: set[str] = {"Main", "Réserve", "Épuisement", "Repères"}

SYNERGY_INTERACTIONS: dict[frozenset, str] = {
    # Ravitaillement exhausts a card to play from reserve → synergizes with
    # cards that care about exhausted state or reserve
    frozenset({"Ravitaillement", "Réserve"}): "Ravitaillement + Réserve",
    frozenset({"Ravitaillement", "Épuisement"}): "Ravitaillement + Épuisement",
    # Token creation + cards that count creatures or boost them
    frozenset({"Création de Jetons", "Boosts"}): "Jetons + Boosts",
    frozenset({"Recrue Ordis", "Boosts"}): "Ordis + Boosts",
    frozenset({"Scarabot", "Boosts"}): "Scarabot + Boosts",
    # Movement synergies
    frozenset({"Mouvement", "En Contact"}): "Mouvement + Contact",
    # Fugace (fleeting) cards pair well with noon triggers
    frozenset({"Fugace", "À Midi"}): "Fugace + Midi",
    # Anchor + reserve for persistent strategies
    frozenset({"Ancré", "Réserve"}): "Ancré + Réserve",
    # Boost-heavy strategies
    frozenset({"Aguerri", "Boosts"}): "Aguerri + Boosts",
    frozenset({"Boosté", "Boosts"}): "Boosté + Boosts",
    # Sacrifice + tokens = sacrifice fodder strategy
    frozenset({"Sacrifice", "Création de Jetons"}): "Sacrifice + Jetons",
    frozenset({"Sacrifice", "Aérolithe"}): "Sacrifice + Aérolithe",
    frozenset({"Sacrifice", "Graine de Mana"}): "Sacrifice + Graine de Mana",
    # Cooldown spells interact with exhaust/reserve themes
    frozenset({"Cooldown Sort", "Épuisement"}): "Cooldown + Épuisement",
    frozenset({"Cooldown Sort", "Réserve"}): "Cooldown + Réserve",
    # Scout sends to reserve → synergizes with reserve strategies
    frozenset({"Repérage", "Réserve"}): "Repérage + Réserve",
    # Asleep ignores stats at dusk → interacts with contact positioning
    frozenset({"Endormi", "En Contact"}): "Endormi + Contact",
}


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
# Keyword / synergy helpers
# ---------------------------------------------------------------------------

def _strip_parentheses(text: str) -> str:
    """Remove all parenthesized reminder text from an effect string."""
    return re.sub(r"\([^)]*\)", "", text)


def _extract_keywords(card: dict) -> set[str]:
    """Extract canonical synergy keywords from a card's bracketed abilities.

    Only considers text inside square brackets [like this].
    Parenthesized reminder text is stripped first.
    Token references like [1/1/1 Recrue Ordis] are normalized by stripping
    the stat prefix.
    Returns a set of canonical keyword labels (e.g. {"Sabotage", "Défenseur"}).
    """
    raw_effect = card.get("elements", {}).get("MAIN_EFFECT", "")
    effect = _strip_parentheses(raw_effect)
    found: set[str] = set()

    for match in re.findall(r"\[([^\]]+)\]", effect):
        # Strip leading '[' from double-bracket keywords like [[Fugace]]
        clean = match.lstrip("[").strip()
        # Strip stat prefix for token names: "1/1/1 Recrue Ordis" → "Recrue Ordis"
        clean_no_stats = re.sub(r"^\d+/\d+/\d+\s+", "", clean)

        clean_lower = clean_no_stats.lower()

        # Exact match first
        if clean_lower in SYNERGY_MAP:
            found.add(SYNERGY_MAP[clean_lower])
            continue

        # Partial match (for patterns like "Coriace 1" matching "coriace")
        for pattern, label in SYNERGY_MAP.items():
            if pattern in clean_lower or clean_lower in pattern:
                found.add(label)
                break

    return found


def _extract_synergy_tags(card: dict) -> set[str]:
    """Extract all synergy tags from a card: bracketed keywords + effect patterns.

    This combines the bracket-based keyword extraction with free-text effect
    pattern detection to capture deeper mechanical synergies.
    Also considers ECHO_EFFECT for additional synergy signals.
    """
    tags = _extract_keywords(card)

    # Scan full effect text (including ECHO_EFFECT) for effect-based patterns
    elements = card.get("elements", {})
    full_text = " ".join(
        elements.get(field, "") or ""
        for field in ("MAIN_EFFECT", "ECHO_EFFECT")
    )
    text = _strip_parentheses(full_text)

    for pattern, tag in EFFECT_PATTERNS:
        if pattern.search(text):
            tags.add(tag)

    return tags


def _compute_synergy_score(tags_a: set[str], tags_b: set[str]) -> int:
    """Compute a synergy score between two sets of tags.

    Scores:
    - +2 for each directly shared tag (same keyword/effect)
    - +1 for each rules-based interaction between their tags
    """
    direct_shared = (tags_a & tags_b) - COMBO_ONLY_TAGS
    score = len(direct_shared) * 2

    for pair, _label in SYNERGY_INTERACTIONS.items():
        if pair <= (tags_a | tags_b) and not pair <= tags_a and not pair <= tags_b:
            # One tag from each card
            score += 1

    return score


def _group_synergy_score(cards: list[dict]) -> tuple[int, str]:
    """Compute total synergy score for a group and find the best label.

    Returns (total_score, best_label) where best_label is the most
    descriptive synergy tag shared by the group.
    """
    card_tags = [_extract_synergy_tags(c) for c in cards]
    total = 0
    for i in range(len(cards)):
        for j in range(i + 1, len(cards)):
            total += _compute_synergy_score(card_tags[i], card_tags[j])

    # Find the best label: prefer a directly shared keyword, then interaction
    shared = set.intersection(*card_tags) if card_tags else set()
    display_shared = shared - COMBO_ONLY_TAGS
    if display_shared:
        # Prefer bracket-based keywords over effect patterns for display
        keyword_shared = display_shared & set(SYNERGY_MAP.values())
        label = next(iter(keyword_shared)) if keyword_shared else next(iter(display_shared))
    else:
        # Check for interaction-based synergies
        all_tags = set.union(*card_tags) if card_tags else set()
        label = "synergie"
        for pair, interaction_label in SYNERGY_INTERACTIONS.items():
            if pair <= all_tags:
                label = interaction_label
                break

    return total, label


def _find_synergy_group(
    characters: list[dict], group_size: int = GROUP_SIZE
) -> tuple[list[dict], str] | None:
    """Find a group of characters with strong synergies.

    Uses both bracketed keywords and effect-based pattern analysis to find
    groups with deep mechanical synergies. Tries multiple candidate groups
    and picks the one with the highest synergy score.

    Returns (cards, synergy_label) or None if no group can be formed.
    """
    # Build tag → cards index using the enhanced synergy detection
    tag_to_cards: dict[str, list[dict]] = {}
    for card in characters:
        for tag in _extract_synergy_tags(card):
            if tag not in COMBO_ONLY_TAGS:
                tag_to_cards.setdefault(tag, []).append(card)

    # Find all tags with enough cards for a group
    viable = [
        (tag, cards) for tag, cards in tag_to_cards.items()
        if len(cards) >= group_size
    ]
    if not viable:
        return None

    random.shuffle(viable)

    best_group: list[dict] | None = None
    best_score = -1
    best_label = "synergie"

    # Try several candidate groups and keep the best one
    for tag, cards in viable[:5]:
        # Deduplicate by name to avoid variants
        by_name: dict[str, list[dict]] = {}
        for c in cards:
            by_name.setdefault(_get_name(c), []).append(c)

        unique_names = list(by_name.keys())
        if len(unique_names) < group_size:
            continue

        # Try a few random samples for this tag
        for _ in range(3):
            chosen_names = random.sample(unique_names, group_size)
            candidate = [random.choice(by_name[n]) for n in chosen_names]
            score, label = _group_synergy_score(candidate)
            if score > best_score:
                best_score = score
                best_group = candidate
                best_label = label

    if best_group is None:
        return None
    return best_group, best_label


def generate_faction_group_choices(
    state: dict,
) -> list[tuple[str, list[dict], str]]:
    """Generate 3 groups of 3 characters, each group from a different faction.

    Each group shares synergies detected via keyword matching AND effect-based
    pattern analysis (boosts, tokens, movement, etc.), scored using a
    rules-based interaction matrix.

    Returns a list of (faction_code, [card, card, card], shared_keyword) tuples.
    """
    factions = random.sample(FACTIONS, len(FACTIONS))  # Try all factions in random order
    groups: list[tuple[str, list[dict], str]] = []

    for faction in factions:
        if len(groups) >= NUM_GROUPS:
            break

        # Get all rare characters for this faction
        pool = get_cards_by_faction_and_rarity(
            state["collection"], faction, [RARITY_RARE]
        )
        # Only characters
        pool = [c for c in pool if _get_card_type(c) == "CHARACTER"]
        pool = available_for_pick(pool, state["copies_picked"])

        if len(pool) < GROUP_SIZE:
            continue

        result = _find_synergy_group(pool, GROUP_SIZE)
        if result is not None:
            group, keyword_label = result
            groups.append((faction, group, keyword_label))

    return groups


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


def apply_group_pick(state: dict, group: list[dict]) -> None:
    """Apply a faction group pick (3 cards at once) for pick 1."""
    for card in group:
        ref = _get_ref(card)
        state["copies_picked"][ref] = state["copies_picked"].get(ref, 0) + 1
        state["picks"].append(card)

    state["faction"] = _get_faction(group[0])
    state["rare_slots"] -= len(group)
    state["pick_index"] = len(group) + 1  # Next pick index
    state["phase"] = "MAIN_DRAFT"
    state["current_choices"] = None


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
