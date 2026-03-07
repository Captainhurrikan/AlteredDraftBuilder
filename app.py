"""Altered Draft Tool — Streamlit UI."""

import streamlit as st

from draft_engine import (
    apply_pick,
    build_deck_summary,
    export_deck_text,
    generate_faction_choices,
    generate_hero_choices,
    generate_main_choices,
    init_draft_state,
    load_collection_from_zip,
    RARE_SLOTS,
    COMMON_EXALTED_SLOTS,
    _get_name,
    _get_faction,
    _get_rarity,
    _get_cost,
    _get_effect,
    _get_powers,
    _get_card_type,
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
def render_card(card: dict, col, key_suffix: str, on_pick):
    """Render a single card in a Streamlit column with a pick button."""
    faction = _get_faction(card)
    rarity = _get_rarity(card)
    card_type = _get_card_type(card)
    color = FACTION_COLORS.get(faction, "#888")
    faction_name = FACTION_NAMES.get(faction, faction)
    rarity_label = RARITY_LABELS.get(rarity, rarity)
    name = _get_name(card)
    cost = _get_cost(card)
    effect = _get_effect(card)
    powers = _get_powers(card)

    with col:
        st.markdown(
            f"""
            <div style="
                border: 3px solid {color};
                border-radius: 12px;
                padding: 16px;
                text-align: center;
                background: linear-gradient(180deg, {color}22 0%, #ffffff 40%);
                min-height: 280px;
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
                <h3 style="margin: 8px 0;">{name}</h3>
                <p style="margin: 4px 0; color: #666;">
                    {"" if card_type == "HERO" else f"Coût : {cost} | "}{rarity_label}
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # Powers
        if powers:
            power_parts = []
            for pk, pv in powers.items():
                icon = POWER_ICONS.get(pk, "")
                power_parts.append(f"{icon} {pv}")
            st.caption(" — ".join(power_parts))

        # Effect (truncated)
        if effect:
            display_effect = effect[:120] + "…" if len(effect) > 120 else effect
            st.caption(display_effect)

        st.button(
            f"Choisir {name}",
            key=f"pick_{key_suffix}",
            on_click=on_pick,
            args=(card,),
            use_container_width=True,
            type="primary",
        )


# ---------------------------------------------------------------------------
# Sidebar: deck in progress
# ---------------------------------------------------------------------------
def render_sidebar():
    """Show the deck being built in the sidebar."""
    picks = _state().get("picks", [])
    if not picks:
        st.sidebar.markdown("*Aucune carte encore sélectionnée.*")
        return

    st.sidebar.markdown(f"### Deck ({len(picks)} cartes)")
    summary = build_deck_summary(picks)
    for rarity in ("HERO", "RARE", "EXALTED", "COMMON"):
        entries = summary.get(rarity, [])
        if not entries:
            continue
        label = RARITY_LABELS.get(rarity, rarity)
        st.sidebar.markdown(f"**{label}** ({len(entries)} différentes)")
        for name, _ref, count in sorted(entries):
            if rarity == "HERO":
                st.sidebar.markdown(f"- {name}")
            else:
                st.sidebar.markdown(f"- {name} ×{count}")


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
def screen_upload():
    st.title("Altered Draft Tool")
    st.markdown("Outil de draft interactif pour **Altered TCG**.")
    st.markdown("---")

    uploaded = st.file_uploader(
        "Uploade ton export de collection Altered (fichier ZIP)",
        type=["zip"],
    )

    if uploaded is not None:
        _state()["zip_data"] = uploaded.read()

    if st.button("Commencer le Draft", disabled=("zip_data" not in _state())):
        try:
            collection = load_collection_from_zip(_state()["zip_data"])
        except Exception as e:
            st.error(f"Erreur lors du chargement du ZIP : {e}")
            return

        if not collection:
            st.error("Aucune carte trouvée dans le ZIP.")
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

    cols = st.columns(len(choices))
    for i, card in enumerate(choices):
        render_card(card, cols[i], f"faction_{i}", on_faction_pick)


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
        # Force advance
        _state()["pick_index"] += 1
        if pick_idx >= 39:
            _state()["phase"] = "HERO_PICK"
        _state()["current_choices"] = None
        st.rerun()
        return

    cols = st.columns(len(choices))
    for i, card in enumerate(choices):
        render_card(card, cols[i], f"main_{pick_idx}_{i}", on_main_pick)


def screen_hero_pick():
    st.title("Pick 40 — Choisis ton héros")

    if _state().get("current_choices") is None:
        choices = generate_hero_choices(_state())
        _state()["current_choices"] = choices

    choices = _state()["current_choices"]

    if not choices:
        st.error("Aucun héros disponible pour ta faction.")
        return

    cols = st.columns(len(choices))
    for i, card in enumerate(choices):
        render_card(card, cols[i], f"hero_{i}", on_hero_pick)


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
                st.markdown(f"- {name} ×{count}")

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
        screen_upload()
    elif phase == "FACTION_PICK":
        screen_faction_pick()
    elif phase == "MAIN_DRAFT":
        screen_main_draft()
    elif phase == "HERO_PICK":
        screen_hero_pick()
    elif phase == "DONE":
        screen_done()
    else:
        screen_upload()


if __name__ == "__main__":
    main()
