"""Altered Draft Tool — Streamlit UI."""

import streamlit as st
from collections import Counter

from draft_engine import (
    apply_pick,
    build_deck_summary,
    export_deck_text,
    generate_faction_choices,
    generate_hero_choices,
    generate_main_choices,
    has_bundled_data,
    init_draft_state,
    load_collection_from_data_dir,
    RARE_SLOTS,
    COMMON_EXALTED_SLOTS,
    _get_name,
    _get_faction,
    _get_rarity,
    _get_cost,
    _get_effect,
    _get_powers,
    _get_card_type,
    _get_ref,
)

# ---------------------------------------------------------------------------
# Faction colours
# ---------------------------------------------------------------------------
FACTION_COLORS = {
    "AX": "#5b8dd9",  # Axiom — blue
    "BR": "#e05555",  # Bravos — red
    "LY": "#d4a843",  # Lyra — gold
    "MU": "#6bbf6b",  # Muna — green
    "OR": "#b07cd8",  # Ordis — purple
    "YZ": "#3cbcc3",  # Yzmir — teal
}

FACTION_NAMES = {
    "AX": "Axiom",
    "BR": "Bravos",
    "LY": "Lyra",
    "MU": "Muna",
    "OR": "Ordis",
    "YZ": "Yzmir",
}

RARITY_LABELS = {
    "COMMON": "Commune",
    "RARE": "Rare",
    "EXALTED": "Exaltée",
    "HERO": "Héros",
}

TYPE_LABELS = {
    "CHARACTER": "Personnages",
    "SPELL": "Sorts",
    "PERMANENT": "Permanents",
    "LANDMARK_PERMANENT": "Permanents",
    "HERO": "Héros",
}

POWER_ICONS = {
    "MOUNTAIN_POWER": "🏔️",
    "OCEAN_POWER": "🌊",
    "FOREST_POWER": "🌲",
}

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(page_title="Altered Draft Tool", layout="wide")


# ---------------------------------------------------------------------------
# Session state helpers
# ---------------------------------------------------------------------------
def _state():
    return st.session_state


def _reset_draft():
    """Reset draft state but keep the collection."""
    collection = _state().get("raw_collection")
    if collection is not None:
        draft = init_draft_state(collection)
        for k, v in draft.items():
            _state()[k] = v
        _state()["pick_type"] = None
    else:
        for key in list(_state().keys()):
            if key != "raw_collection":
                del _state()[key]


# ---------------------------------------------------------------------------
# Card display component
# ---------------------------------------------------------------------------
def _get_image_url(card: dict) -> str | None:
    """Get the card image URL (FR preferred, fallback to imagePath)."""
    all_paths = card.get("allImagePath", {})
    if isinstance(all_paths, dict) and all_paths.get("fr-fr"):
        return all_paths["fr-fr"]
    return card.get("imagePath")


def render_card(card: dict, col, key_suffix: str, on_pick):
    """Render a single card in a Streamlit column with a pick button."""
    name = _get_name(card)
    image_url = _get_image_url(card)

    with col:
        if image_url:
            st.image(image_url, use_container_width=True)
        else:
            faction = _get_faction(card)
            rarity = _get_rarity(card)
            card_type = _get_card_type(card)
            color = FACTION_COLORS.get(faction, "#888")
            faction_name = FACTION_NAMES.get(faction, faction)
            rarity_label = RARITY_LABELS.get(rarity, rarity)
            cost = _get_cost(card)
            st.markdown(
                f"""
                <div style="
                    border: 3px solid {color};
                    border-radius: 12px;
                    padding: 16px;
                    text-align: center;
                    background: linear-gradient(180deg, {color}22 0%, #ffffff 40%);
                    min-height: 200px;
                ">
                    <div style="
                        background: {color};
                        color: white;
                        padding: 4px 12px;
                        border-radius: 20px;
                        display: inline-block;
                        font-size: 0.8em;
                        margin-bottom: 8px;
                    ">{faction_name}</div>
                    <h4 style="margin: 4px 0;">{name}</h4>
                    <p style="margin: 4px 0; color: #666; font-size: 0.85em;">
                        {"" if card_type == "HERO" else f"Coût : {cost} | "}{rarity_label}
                    </p>
                </div>
                """,
                unsafe_allow_html=True,
            )

        st.button(
            f"Choisir {name}",
            key=f"pick_{key_suffix}",
            on_click=on_pick,
            args=(card,),
            use_container_width=True,
            type="primary",
        )


# ---------------------------------------------------------------------------
# Sidebar: deck in progress with tooltip images + stats
# ---------------------------------------------------------------------------
def _compute_deck_stats(picks: list[dict]) -> dict:
    """Compute type distribution and mana curve from picks."""
    type_counts = Counter()
    main_cost_curve = Counter()
    reserve_cost_curve = Counter()

    for card in picks:
        ct = _get_card_type(card)
        if ct == "HERO":
            continue
        type_label = TYPE_LABELS.get(ct, ct)
        type_counts[type_label] += 1

        elements = card.get("elements", {})
        main_cost = elements.get("MAIN_COST", "?")
        recall_cost = elements.get("RECALL_COST", "?")

        # Clean cost values (remove # markers from rare cards)
        main_cost_clean = str(main_cost).replace("#", "")
        recall_cost_clean = str(recall_cost).replace("#", "")

        try:
            mc = int(main_cost_clean)
            main_cost_curve[mc] += 1
        except (ValueError, TypeError):
            pass
        try:
            rc = int(recall_cost_clean)
            reserve_cost_curve[rc] += 1
        except (ValueError, TypeError):
            pass

    return {
        "type_counts": dict(type_counts),
        "main_cost_curve": dict(sorted(main_cost_curve.items())),
        "reserve_cost_curve": dict(sorted(reserve_cost_curve.items())),
    }


def render_sidebar():
    """Show the deck being built in the sidebar with hover images and stats."""
    picks = _state().get("picks", [])
    if not picks:
        st.sidebar.markdown("*Aucune carte encore sélectionnée.*")
        return

    st.sidebar.markdown(f"### Deck ({len(picks)} cartes)")

    # --- Deck stats ---
    stats = _compute_deck_stats(picks)

    # Type distribution
    type_counts = stats["type_counts"]
    if type_counts:
        st.sidebar.markdown("**Répartition par type :**")
        for t_label in ("Personnages", "Sorts", "Permanents"):
            count = type_counts.get(t_label, 0)
            if count:
                st.sidebar.markdown(f"- {t_label} : **{count}**")

    # Mana curve
    main_curve = stats["main_cost_curve"]
    reserve_curve = stats["reserve_cost_curve"]
    if main_curve:
        st.sidebar.markdown("**Courbe de mana (Main) :**")
        max_cost = max(main_curve.keys()) if main_curve else 0
        curve_parts = []
        for cost in range(0, max_cost + 1):
            count = main_curve.get(cost, 0)
            bar = "█" * count
            curve_parts.append(f"`{cost}` {bar} {count}")
        st.sidebar.markdown("  \n".join(curve_parts))

    if reserve_curve:
        st.sidebar.markdown("**Courbe de mana (Réserve) :**")
        max_cost = max(reserve_curve.keys()) if reserve_curve else 0
        curve_parts = []
        for cost in range(0, max_cost + 1):
            count = reserve_curve.get(cost, 0)
            bar = "█" * count
            curve_parts.append(f"`{cost}` {bar} {count}")
        st.sidebar.markdown("  \n".join(curve_parts))

    st.sidebar.markdown("---")

    # --- Card list with hover images ---
    summary = build_deck_summary(picks)

    # Build a map from ref -> image_url for tooltip
    ref_to_image = {}
    for card in picks:
        ref = _get_ref(card)
        if ref not in ref_to_image:
            ref_to_image[ref] = _get_image_url(card) or ""

    # CSS for hover tooltip
    st.sidebar.markdown(
        """
        <style>
        .card-tooltip {
            position: relative;
            cursor: pointer;
            display: inline-block;
        }
        .card-tooltip .card-tooltip-img {
            display: none;
            position: fixed;
            z-index: 9999;
            width: 250px;
            border-radius: 12px;
            box-shadow: 0 4px 20px rgba(0,0,0,0.4);
            pointer-events: none;
        }
        .card-tooltip:hover .card-tooltip-img {
            display: block;
            left: 300px;
            top: 50px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    for rarity in ("HERO", "RARE", "EXALTED", "COMMON"):
        entries = summary.get(rarity, [])
        if not entries:
            continue
        label = RARITY_LABELS.get(rarity, rarity)
        st.sidebar.markdown(f"**{label}** ({len(entries)})")
        for name, ref, count in sorted(entries):
            img_url = ref_to_image.get(ref, "")
            count_str = "" if rarity == "HERO" else f" x{count}"
            if img_url:
                st.sidebar.markdown(
                    f'<span class="card-tooltip">'
                    f"{name}{count_str}"
                    f'<img class="card-tooltip-img" src="{img_url}" />'
                    f"</span>",
                    unsafe_allow_html=True,
                )
            else:
                st.sidebar.markdown(f"- {name}{count_str}")


# ---------------------------------------------------------------------------
# Callbacks
# ---------------------------------------------------------------------------
def on_faction_pick(card):
    apply_pick(_state(), card, pick_type="RARE")
    _state()["pick_type"] = None


def on_main_pick(card):
    pick_type = _state().get("pick_type", "COMMON_EXALTED")
    apply_pick(_state(), card, pick_type=pick_type)
    _state()["pick_type"] = None


def on_hero_pick(card):
    apply_pick(_state(), card, pick_type=None)
    _state()["pick_type"] = None


# ---------------------------------------------------------------------------
# Screens
# ---------------------------------------------------------------------------
def screen_start():
    st.title("Altered Draft Tool")
    st.markdown("Outil de draft interactif pour **Altered TCG**.")
    st.markdown("---")

    if not has_bundled_data():
        st.error(
            "Aucune donnée de cartes trouvée dans le dossier `data/`. "
            "Place ton export Altered (ZIP ou fichiers JSON) dans le dossier `data/` du projet."
        )
        return

    if st.button("Commencer le Draft", type="primary"):
        try:
            collection = load_collection_from_data_dir()
        except Exception as e:
            st.error(f"Erreur lors du chargement des cartes : {e}")
            return

        if not collection:
            st.error("Aucune carte trouvée dans le dossier `data/`.")
            return

        _state()["raw_collection"] = collection
        draft = init_draft_state(collection)
        for k, v in draft.items():
            _state()[k] = v
        _state()["pick_type"] = None
        st.rerun()


def screen_faction_pick():
    st.title("Pick 1 — Quelle faction vas-tu jouer ?")
    st.markdown("Choisis une carte rare. Sa faction sera ta faction pour tout le draft.")

    # Generate choices once
    if _state().get("current_choices") is None:
        choices = generate_faction_choices(_state())
        _state()["current_choices"] = choices

    choices = _state()["current_choices"]

    if not choices:
        st.error("Pas assez de cartes rares dans la collection pour proposer un choix.")
        return

    # Use max 5 columns, cards won't be too wide
    cols = st.columns(min(len(choices), 5))
    for i, card in enumerate(choices):
        render_card(card, cols[i % len(cols)], f"faction_{i}", on_faction_pick)


def screen_main_draft():
    pick_idx = _state()["pick_index"]
    rare_left = _state()["rare_slots"]
    ce_left = _state()["common_exalted_slots"]

    # Generate choices once per pick
    if _state().get("current_choices") is None:
        pick_type, choices = generate_main_choices(_state())
        _state()["current_choices"] = choices
        _state()["pick_type"] = pick_type
    else:
        pick_type = _state().get("pick_type", "COMMON_EXALTED")
        choices = _state()["current_choices"]

    # Header
    type_label = "Pick Rare" if pick_type == "RARE" else "Pick Commune / Exaltée"
    st.title(f"Pick {pick_idx}/39 — {type_label}")

    # Progress bar
    progress = (pick_idx - 1) / 39
    st.progress(progress)
    st.markdown(
        f"**Rares restantes : {rare_left}/{RARE_SLOTS}** | "
        f"**Communes/Exaltées restantes : {ce_left}/{COMMON_EXALTED_SLOTS}**"
    )

    if not choices:
        st.warning("Plus de cartes disponibles dans ce pool.")
        _state()["pick_index"] += 1
        if pick_idx >= 39:
            _state()["phase"] = "HERO_PICK"
        _state()["current_choices"] = None
        st.rerun()
        return

    # Display in rows of 5 max for smaller cards
    cols = st.columns(min(len(choices), 5))
    for i, card in enumerate(choices):
        render_card(card, cols[i % len(cols)], f"main_{pick_idx}_{i}", on_main_pick)


def screen_hero_pick():
    st.title("Pick 40 — Choisis ton héros")

    if _state().get("current_choices") is None:
        choices = generate_hero_choices(_state())
        _state()["current_choices"] = choices

    choices = _state()["current_choices"]

    if not choices:
        st.error("Aucun héros disponible pour ta faction.")
        return

    st.markdown(f"**{len(choices)} héros disponibles :**")

    # Display all heroes in rows of 5
    n_cols = min(len(choices), 5)
    for row_start in range(0, len(choices), n_cols):
        row_cards = choices[row_start : row_start + n_cols]
        cols = st.columns(n_cols)
        for i, card in enumerate(row_cards):
            render_card(card, cols[i], f"hero_{row_start + i}", on_hero_pick)


def screen_done():
    st.title("Draft terminé !")
    st.balloons()

    picks = _state().get("picks", [])
    summary = build_deck_summary(picks)

    for rarity in ("HERO", "RARE", "EXALTED", "COMMON"):
        entries = summary.get(rarity, [])
        if not entries:
            continue
        label = RARITY_LABELS.get(rarity, rarity)
        st.subheader(f"{label} ({sum(c for _, _, c in entries)} cartes)")
        for name, _ref, count in sorted(entries):
            if rarity == "HERO":
                st.markdown(f"- **{name}**")
            else:
                st.markdown(f"- {name} x{count}")

    st.markdown(f"**Total : {len(picks)} cartes**")
    st.markdown("---")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Nouveau Draft"):
            _reset_draft()
            st.rerun()
    with col2:
        deck_text = export_deck_text(picks)
        st.download_button(
            "Exporter en .txt",
            data=deck_text,
            file_name="altered_draft_deck.txt",
            mime="text/plain",
        )


# ---------------------------------------------------------------------------
# Main routing
# ---------------------------------------------------------------------------
def main():
    render_sidebar()

    phase = _state().get("phase")

    if phase is None:
        screen_start()
    elif phase == "FACTION_PICK":
        screen_faction_pick()
    elif phase == "MAIN_DRAFT":
        screen_main_draft()
    elif phase == "HERO_PICK":
        screen_hero_pick()
    elif phase == "DONE":
        screen_done()
    else:
        screen_start()


main()
