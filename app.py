"""Altered Draft Tool — Streamlit UI."""

import streamlit as st
import plotly.graph_objects as go
from collections import Counter, defaultdict

from draft_engine import (
    apply_group_pick,
    apply_pick,
    build_deck_summary,
    export_deck_text,
    export_deck_refs,
    generate_faction_choices,
    generate_faction_group_choices,
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
    _extract_keywords,
    _extract_synergy_tags,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
FACTION_COLORS = {
    "AX": "#5b8dd9",
    "BR": "#e05555",
    "LY": "#d4a843",
    "MU": "#6bbf6b",
    "OR": "#b07cd8",
    "YZ": "#3cbcc3",
}

FACTION_NAMES = {
    "AX": "Axiom",
    "BR": "Bravos",
    "LY": "Lyra",
    "MU": "Muna",
    "OR": "Ordis",
    "YZ": "Yzmir",
}

FACTION_ICONS = {
    "AX": "⚙️",
    "BR": "🔥",
    "LY": "🎵",
    "MU": "🌿",
    "OR": "🔮",
    "YZ": "💧",
}

RARITY_LABELS = {
    "COMMON": "Commune",
    "RARE": "Rare",
    "EXALTED": "Exaltée",
    "HERO": "Héros",
}

TYPE_LABELS = {
    "CHARACTER": "Personnage",
    "SPELL": "Sort",
    "PERMANENT": "Permanent",
    "LANDMARK_PERMANENT": "Repère Perm.",
    "HERO": "Héros",
}

TYPE_ICONS = {
    "Personnage": "👤",
    "Sort": "✨",
    "Permanent": "🏛️",
    "Repère Perm.": "🏛️",
    "Héros": "👑",
}

TYPE_CHART_COLORS = {
    "Personnage": "#4FC3F7",
    "Sort": "#CE93D8",
    "Permanent": "#FFB74D",
    "Repère Perm.": "#FFB74D",
}

TERRAIN_COLORS = {
    "FOREST_POWER": "#8BC34A",
    "MOUNTAIN_POWER": "#FF9800",
    "OCEAN_POWER": "#2196F3",
}

TERRAIN_LABELS = {
    "FOREST_POWER": "Forêt",
    "MOUNTAIN_POWER": "Montagne",
    "OCEAN_POWER": "Eau",
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
# Card display
# ---------------------------------------------------------------------------
def _get_image_url(card: dict) -> str | None:
    all_paths = card.get("allImagePath", {})
    if isinstance(all_paths, dict) and all_paths.get("fr-fr"):
        return all_paths["fr-fr"]
    return card.get("imagePath")


def _clean_cost(raw) -> int | None:
    try:
        return int(str(raw).replace("#", ""))
    except (ValueError, TypeError):
        return None


def render_card(card: dict, col, key_suffix: str, on_pick):
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
# Deck stats computation
# ---------------------------------------------------------------------------
def _compute_deck_stats(picks: list[dict]) -> dict:
    type_counts = Counter()
    main_cost_curve = Counter()
    reserve_cost_curve = Counter()
    terrain_totals = Counter()
    rarity_counts = Counter()

    for card in picks:
        ct = _get_card_type(card)
        rarity = _get_rarity(card)
        rarity_counts[rarity] += 1

        if ct == "HERO":
            continue

        type_label = TYPE_LABELS.get(ct, ct)
        type_counts[type_label] += 1

        elements = card.get("elements", {})

        mc = _clean_cost(elements.get("MAIN_COST", "?"))
        rc = _clean_cost(elements.get("RECALL_COST", "?"))
        if mc is not None:
            main_cost_curve[mc] += 1
        if rc is not None:
            reserve_cost_curve[rc] += 1

        for terrain_key in ("FOREST_POWER", "MOUNTAIN_POWER", "OCEAN_POWER"):
            val = elements.get(terrain_key, "")
            if val != "":
                try:
                    terrain_totals[terrain_key] += int(str(val).replace("#", ""))
                except (ValueError, TypeError):
                    terrain_totals[terrain_key] += 1

    return {
        "type_counts": dict(type_counts),
        "main_cost_curve": dict(sorted(main_cost_curve.items())),
        "reserve_cost_curve": dict(sorted(reserve_cost_curve.items())),
        "terrain_totals": dict(terrain_totals),
        "rarity_counts": dict(rarity_counts),
    }


# ---------------------------------------------------------------------------
# Sidebar: deck in progress
# ---------------------------------------------------------------------------
def _build_deck_by_type(picks: list[dict]) -> dict:
    """Group picks by card type, with counts and card data."""
    card_counts: dict[str, int] = {}
    card_map: dict[str, dict] = {}
    for c in picks:
        ref = _get_ref(c)
        card_counts[ref] = card_counts.get(ref, 0) + 1
        card_map[ref] = c

    grouped = defaultdict(list)
    for ref, count in card_counts.items():
        card = card_map[ref]
        ct = _get_card_type(card)
        type_label = TYPE_LABELS.get(ct, ct)
        grouped[type_label].append((card, count))

    # Sort each group by: main cost → reserve cost → alphabetical
    for type_label in grouped:
        grouped[type_label].sort(
            key=lambda x: (
                _clean_cost(x[0].get("elements", {}).get("MAIN_COST", "99")) or 99,
                _clean_cost(x[0].get("elements", {}).get("RECALL_COST", "99")) or 99,
                _get_name(x[0]).lower(),
            )
        )

    return dict(grouped)


def _make_single_mana_curve(curve: dict[int, int], title: str, color: str) -> go.Figure | None:
    """Build a single mana curve Plotly chart."""
    if not curve:
        return None

    max_cost = max(curve.keys())
    x = list(range(0, max_cost + 1))
    vals = [curve.get(c, 0) for c in x]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=x, y=vals,
        marker_color=color,
        text=vals, textposition="outside",
        textfont_size=10,
    ))
    fig.update_layout(
        title=dict(text=title, font_size=13, x=0.5, xanchor="center"),
        margin=dict(t=35, b=25, l=10, r=10),
        height=180,
        xaxis=dict(dtick=1, title=None, tickfont_size=10),
        yaxis=dict(visible=False),
        bargap=0.3,
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        showlegend=False,
    )
    return fig


def _compute_mana_curves(picks: list[dict]) -> tuple[dict[int, int], dict[int, int]]:
    """Compute main and reserve cost curves from picks."""
    main_curve: dict[int, int] = Counter()
    reserve_curve: dict[int, int] = Counter()

    for card in picks:
        if _get_card_type(card) == "HERO":
            continue
        elements = card.get("elements", {})
        mc = _clean_cost(elements.get("MAIN_COST"))
        rc = _clean_cost(elements.get("RECALL_COST"))
        if mc is not None:
            main_curve[mc] += 1
        if rc is not None:
            reserve_curve[rc] += 1

    return dict(main_curve), dict(reserve_curve)


def render_mana_curves():
    """Render Main and Reserve mana curves side by side below card selection."""
    picks = _state().get("picks", [])
    if not picks:
        return

    main_curve, reserve_curve = _compute_mana_curves(picks)
    if not main_curve and not reserve_curve:
        return

    col_left, col_right = st.columns(2)
    with col_left:
        fig = _make_single_mana_curve(main_curve, "Courbe Main", "#1976D2")
        if fig:
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    with col_right:
        fig = _make_single_mana_curve(reserve_curve, "Courbe Réserve", "#F57C00")
        if fig:
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


def _build_sidebar_card_list(picks: list[dict]) -> list[tuple[dict, int]]:
    """Build a flat card list sorted by main cost, with counts."""
    card_counts: dict[str, int] = {}
    card_map: dict[str, dict] = {}
    for c in picks:
        ref = _get_ref(c)
        card_counts[ref] = card_counts.get(ref, 0) + 1
        card_map[ref] = c

    result = []
    for ref, count in card_counts.items():
        result.append((card_map[ref], count))

    # Sort by main cost → reserve cost → name
    result.sort(
        key=lambda x: (
            _clean_cost(x[0].get("elements", {}).get("MAIN_COST", "99")) or 99,
            _clean_cost(x[0].get("elements", {}).get("RECALL_COST", "99")) or 99,
            _get_name(x[0]).lower(),
        )
    )
    return result


def render_sidebar():
    picks = _state().get("picks", [])
    if not picks:
        st.sidebar.markdown("*Aucune carte encore sélectionnée.*")
        return

    # --- Rarity summary ---
    stats = _compute_deck_stats(picks)
    rarity = stats["rarity_counts"]
    total = len(picks)
    n_common = rarity.get("COMMON", 0)
    n_rare = rarity.get("RARE", 0)
    n_exalted = rarity.get("EXALTED", 0)

    st.sidebar.markdown(
        f"""
        <style>
        .deck-header {{
            display: flex; align-items: center; gap: 12px;
            padding: 8px 4px; border-bottom: 2px solid #555;
            margin-bottom: 6px; font-size: 0.85em; font-weight: bold;
        }}
        .deck-header .dh-label {{ color: #aaa; }}
        .deck-header .dh-val {{ min-width: 20px; text-align: center; }}
        .rarity-icon {{
            display: inline-block; width: 12px; height: 12px;
            clip-path: polygon(50% 0%, 100% 50%, 50% 100%, 0% 50%);
            vertical-align: middle; margin-right: 2px;
        }}
        .ri-common {{ background: #9E9E9E; }}
        .ri-rare {{ background: #1976D2; }}
        .ri-exalted {{ background: #FFD700; }}

        .sb-card-row {{
            display: flex; align-items: center; gap: 0;
            padding: 0; font-size: 0.82em; position: relative;
            height: 32px; overflow: hidden;
        }}
        .sb-card-row:nth-child(odd) {{ background: rgba(255,255,255,0.03); }}
        .sb-card-row:nth-child(even) {{ background: rgba(255,255,255,0.07); }}
        .sb-card-row:hover {{ background: rgba(255,255,255,0.12); }}

        .sb-qty {{
            min-width: 22px; text-align: center; font-weight: bold;
            font-size: 0.9em; flex-shrink: 0; padding: 0 2px;
            color: #ddd;
        }}
        .sb-thumb {{
            width: 50px; height: 32px; flex-shrink: 0;
            object-fit: cover; object-position: center 20%;
        }}
        .sb-thumb-ph {{
            width: 50px; height: 32px; flex-shrink: 0;
            background: #333;
        }}
        .sb-faction-icon {{
            flex-shrink: 0; font-size: 0.8em; padding: 0 3px;
        }}
        .sb-name {{
            flex: 1; white-space: nowrap; overflow: hidden;
            text-overflow: ellipsis; padding: 0 4px; font-size: 0.85em;
            color: #ddd;
        }}
        .sb-card-wrap {{ position: relative; }}
        .sb-card-wrap .sb-hover-img {{
            display: none; position: fixed; z-index: 9999;
            width: 250px; border-radius: 12px;
            box-shadow: 0 4px 20px rgba(0,0,0,0.4);
            pointer-events: none; left: 310px; top: 80px;
        }}
        .sb-card-wrap:hover .sb-hover-img {{
            display: block;
        }}
        .sb-list {{
            border: 1px solid #444; border-radius: 6px; overflow: hidden;
        }}
        </style>

        <div class="deck-header">
            <span class="dh-label">Total</span>
            <span class="dh-val">{total}</span>
            <span><span class="rarity-icon ri-common"></span> {n_common}</span>
            <span><span class="rarity-icon ri-rare"></span> {n_rare}/{RARE_SLOTS}</span>
            <span><span class="rarity-icon ri-exalted"></span> {n_exalted}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # --- Card list ---
    card_list = _build_sidebar_card_list(picks)
    html_rows = []
    for card, count in card_list:
        name = _get_name(card)
        faction = _get_faction(card)
        faction_icon = FACTION_ICONS.get(faction, "")
        img_url = _get_image_url(card) or ""

        # Artwork thumbnail (horizontal banner crop)
        if img_url:
            thumb = f'<img class="sb-thumb" src="{img_url}" />'
            hover = f'<img class="sb-hover-img" src="{img_url}" />'
        else:
            thumb = '<div class="sb-thumb-ph"></div>'
            hover = ""

        html_rows.append(
            f'<div class="sb-card-row sb-card-wrap">'
            f'<span class="sb-qty">{count}</span>'
            f'{thumb}'
            f'<span class="sb-faction-icon">{faction_icon}</span>'
            f'<span class="sb-name">{name}</span>'
            f'{hover}'
            f'</div>'
        )

    st.sidebar.markdown(
        f'<div class="sb-list">{"".join(html_rows)}</div>',
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Charts for the done screen
# ---------------------------------------------------------------------------
def _make_type_pie(stats: dict) -> go.Figure:
    type_counts = stats["type_counts"]
    labels = []
    values = []
    colors = []
    for t_label in ("Personnage", "Sort", "Permanent", "Repère Perm."):
        if type_counts.get(t_label, 0) > 0:
            labels.append(t_label)
            values.append(type_counts[t_label])
            colors.append(TYPE_CHART_COLORS.get(t_label, "#999"))

    fig = go.Figure(data=[go.Pie(
        labels=labels, values=values,
        marker=dict(colors=colors),
        hole=0.0,
        textinfo="label+value",
        textfont_size=13,
    )])
    fig.update_layout(
        title="Répartition par Types",
        margin=dict(t=40, b=10, l=10, r=10),
        height=280,
        showlegend=True,
        legend=dict(orientation="h", y=-0.05),
    )
    return fig


def _make_mana_curve(stats: dict) -> go.Figure:
    main_curve = stats["main_cost_curve"]
    reserve_curve = stats["reserve_cost_curve"]

    all_costs = sorted(set(list(main_curve.keys()) + list(reserve_curve.keys())))
    if not all_costs:
        all_costs = [0]
    max_cost = max(all_costs)
    x = list(range(0, max_cost + 1))
    main_vals = [main_curve.get(c, 0) for c in x]
    reserve_vals = [reserve_curve.get(c, 0) for c in x]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        name="Main", x=x, y=main_vals,
        marker_color="#1976D2",
    ))
    fig.add_trace(go.Bar(
        name="Réserve", x=x, y=reserve_vals,
        marker_color="#F57C00",
        opacity=0.7,
    ))
    fig.update_layout(
        title="Coût en Mana",
        xaxis_title="Coût en Mana",
        yaxis_title="Nombre de Cartes",
        barmode="group",
        margin=dict(t=40, b=40, l=40, r=10),
        height=300,
        legend=dict(orientation="h", y=1.12),
    )
    fig.update_xaxes(dtick=1)
    return fig


def _make_terrain_pie(stats: dict) -> go.Figure:
    terrain = stats["terrain_totals"]
    labels = []
    values = []
    colors = []
    for key in ("FOREST_POWER", "MOUNTAIN_POWER", "OCEAN_POWER"):
        if terrain.get(key, 0) > 0:
            labels.append(TERRAIN_LABELS[key])
            values.append(terrain[key])
            colors.append(TERRAIN_COLORS[key])

    fig = go.Figure(data=[go.Pie(
        labels=labels, values=values,
        marker=dict(colors=colors),
        hole=0.0,
        textinfo="label+value",
        textfont_size=13,
    )])
    fig.update_layout(
        title="Répartition par Terrain",
        margin=dict(t=40, b=10, l=10, r=10),
        height=280,
        showlegend=True,
        legend=dict(orientation="h", y=-0.05),
    )
    return fig


# ---------------------------------------------------------------------------
# Callbacks
# ---------------------------------------------------------------------------
def on_faction_group_pick(group: list[dict]):
    apply_group_pick(_state(), group)
    _state()["pick_type"] = None


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


def _card_columns(n_cards: int, max_per_row: int = 5):
    """Create centered columns with padding for smaller card display."""
    n = min(n_cards, max_per_row)
    # Add spacer columns (weight 1) on each side, card columns (weight 2)
    widths = [1.5] + [2] * n + [1.5]
    all_cols = st.columns(widths)
    return all_cols[1:-1]  # Return only the card columns


def render_card_group(
    faction: str, cards: list[dict], keyword: str, group_idx: int
):
    """Render a group of 3 characters from the same faction with shared keyword."""
    color = FACTION_COLORS.get(faction, "#888")
    faction_name = FACTION_NAMES.get(faction, faction)
    faction_icon = FACTION_ICONS.get(faction, "")

    st.markdown(
        f"""
        <div style="
            border: 3px solid {color};
            border-radius: 16px;
            padding: 12px 8px 4px 8px;
            margin-bottom: 8px;
            background: linear-gradient(180deg, {color}18 0%, transparent 60%);
        ">
            <div style="text-align: center; margin-bottom: 8px;">
                <span style="
                    background: {color}; color: white;
                    padding: 4px 16px; border-radius: 20px;
                    font-weight: bold; font-size: 1.1em;
                ">{faction_icon} {faction_name}</span>
                <br/>
                <span style="
                    color: {color}; font-size: 0.85em; font-style: italic;
                    margin-top: 4px; display: inline-block;
                ">Synergie : {keyword.capitalize()}</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Show the 3 cards side by side
    card_cols = st.columns(len(cards))
    for i, card in enumerate(cards):
        with card_cols[i]:
            image_url = _get_image_url(card)
            if image_url:
                st.image(image_url, use_container_width=True)
            else:
                name = _get_name(card)
                rarity = _get_rarity(card)
                rarity_label = RARITY_LABELS.get(rarity, rarity)
                cost = _get_cost(card)
                st.markdown(
                    f"""
                    <div style="
                        border: 2px solid {color};
                        border-radius: 10px;
                        padding: 12px;
                        text-align: center;
                        min-height: 150px;
                    ">
                        <h5 style="margin: 4px 0;">{name}</h5>
                        <p style="margin: 2px 0; color: #666; font-size: 0.8em;">
                            Coût : {cost} | {rarity_label}
                        </p>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

    # Single button to pick the whole group
    st.button(
        f"Choisir le groupe {faction_icon} {faction_name}",
        key=f"pick_group_{group_idx}",
        on_click=on_faction_group_pick,
        args=(cards,),
        use_container_width=True,
        type="primary",
    )


def screen_faction_pick():
    st.title("Pick 1 — Quelle faction vas-tu jouer ?")
    st.markdown(
        "Choisis un **groupe de 3 personnages**. "
        "Leur faction sera ta faction pour tout le draft, "
        "et les 3 cartes rejoindront ton deck."
    )

    if _state().get("current_choices") is None:
        groups = generate_faction_group_choices(_state())
        _state()["current_choices"] = groups

    groups = _state()["current_choices"]
    if not groups:
        st.error("Pas assez de personnages dans la collection pour former des groupes.")
        return

    # Display groups side by side
    group_cols = st.columns(len(groups))
    for idx, (faction, cards, keyword) in enumerate(groups):
        with group_cols[idx]:
            render_card_group(faction, cards, keyword, idx)

    render_mana_curves()


def screen_main_draft():
    pick_idx = _state()["pick_index"]
    rare_left = _state()["rare_slots"]
    ce_left = _state()["common_exalted_slots"]

    if _state().get("current_choices") is None:
        pick_type, choices = generate_main_choices(_state())
        _state()["current_choices"] = choices
        _state()["pick_type"] = pick_type
    else:
        pick_type = _state().get("pick_type", "COMMON_EXALTED")
        choices = _state()["current_choices"]

    type_label = "Pick Rare" if pick_type == "RARE" else "Pick Commune / Exaltée"
    st.title(f"Pick {pick_idx}/39 — {type_label}")

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

    cols = _card_columns(len(choices))
    for i, card in enumerate(choices):
        render_card(card, cols[i % len(cols)], f"main_{pick_idx}_{i}", on_main_pick)

    render_mana_curves()


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
    n_cols = min(len(choices), 5)
    for row_start in range(0, len(choices), n_cols):
        row_cards = choices[row_start : row_start + n_cols]
        cols = _card_columns(len(row_cards))
        for i, card in enumerate(row_cards):
            render_card(card, cols[i], f"hero_{row_start + i}", on_hero_pick)

    render_mana_curves()


def screen_done():
    st.title("Draft terminé !")
    st.balloons()

    picks = _state().get("picks", [])
    stats = _compute_deck_stats(picks)
    deck_by_type = _build_deck_by_type(picks)
    faction = _state().get("faction", "")
    faction_name = FACTION_NAMES.get(faction, faction)
    faction_color = FACTION_COLORS.get(faction, "#888")

    # --- Layout: Hero image | Card list | Stats ---
    col_hero, col_list, col_stats = st.columns([1, 2, 2])

    # --- Hero card image ---
    with col_hero:
        hero_cards = deck_by_type.get("Héros", [])
        if hero_cards:
            hero_card = hero_cards[0][0]
            hero_img = _get_image_url(hero_card)
            if hero_img:
                st.image(hero_img, use_container_width=True)
            st.markdown(
                f'<div style="text-align:center; margin-top:4px;">'
                f'<span style="background:{faction_color}; color:white; '
                f'padding:4px 14px; border-radius:20px; font-weight:bold;">'
                f'{FACTION_ICONS.get(faction, "")} {faction_name}</span></div>',
                unsafe_allow_html=True,
            )

    # --- Card list by type ---
    with col_list:
        # Tooltip CSS
        st.markdown(
            """
            <style>
            .dl-card-row {
                display: flex; align-items: center; gap: 6px;
                padding: 4px 8px; font-size: 0.9em;
                border-radius: 6px; margin: 2px 0;
                background: #fafafa; color: #333;
            }
            .dl-card-row:hover { background: #f0f0f0; }
            .dl-card-row .qty {
                background: #e8e8e8; border-radius: 4px; padding: 2px 8px;
                font-weight: bold; min-width: 24px; text-align: center; color: #333;
            }
            .dl-card-row .fdot {
                width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0;
            }
            .dl-card-row .cname { flex: 1; font-weight: 500; }
            .dl-cost {
                display: inline-flex; width: 24px; height: 24px; border-radius: 50%;
                align-items: center; justify-content: center;
                font-size: 0.8em; font-weight: bold; color: white;
            }
            .dl-cost-m { background: #1976D2; }
            .dl-cost-r { background: #F57C00; }
            .dl-wrap { position: relative; }
            .dl-wrap .dl-hover {
                display: none; position: fixed; z-index: 9999;
                width: 250px; border-radius: 12px;
                box-shadow: 0 8px 30px rgba(0,0,0,0.35);
                pointer-events: none;
            }
            .dl-wrap:hover .dl-hover {
                display: block; left: 50%; top: 80px;
            }
            </style>
            """,
            unsafe_allow_html=True,
        )

        type_order = ["Personnage", "Sort", "Permanent", "Repère Perm.", "Héros"]
        for type_label in type_order:
            entries = deck_by_type.get(type_label, [])
            if not entries:
                continue
            total = sum(c for _, c in entries)
            icon = TYPE_ICONS.get(type_label, "")
            st.markdown(f"**{icon} {type_label} ({total})**")

            rows_html = []
            for card, count in entries:
                name = _get_name(card)
                f_code = _get_faction(card)
                color = FACTION_COLORS.get(f_code, "#888")
                elements = card.get("elements", {})
                mc = _clean_cost(elements.get("MAIN_COST"))
                rc = _clean_cost(elements.get("RECALL_COST"))
                img_url = _get_image_url(card) or ""

                costs = ""
                if mc is not None:
                    costs += f'<span class="dl-cost dl-cost-m">{mc}</span> '
                if rc is not None:
                    costs += f'<span class="dl-cost dl-cost-r">{rc}</span>'

                img_tag = ""
                if img_url:
                    img_tag = f'<img class="dl-hover" src="{img_url}" />'

                rows_html.append(
                    f'<div class="dl-card-row dl-wrap">'
                    f'<span class="qty">{count}</span>'
                    f'<span class="fdot" style="background:{color}"></span>'
                    f'<span class="cname">{name}</span>'
                    f'{costs}'
                    f'{img_tag}'
                    f'</div>'
                )

            st.markdown("\n".join(rows_html), unsafe_allow_html=True)

    # --- Stats column ---
    with col_stats:
        # Summary header
        rarity = stats["rarity_counts"]
        st.markdown("### Statistiques du Deck")

        total_non_hero = len(picks) - rarity.get("HERO", 0)
        st.markdown(
            f"**Total** {len(picks)} | "
            f"C {rarity.get('COMMON', 0)} | "
            f"R {rarity.get('RARE', 0)} | "
            f"E {rarity.get('EXALTED', 0)}"
        )

        # Type pie chart
        fig_type = _make_type_pie(stats)
        st.plotly_chart(fig_type, use_container_width=True)

        # Mana curve
        fig_mana = _make_mana_curve(stats)
        st.plotly_chart(fig_mana, use_container_width=True)

        # Terrain pie
        if stats["terrain_totals"]:
            fig_terrain = _make_terrain_pie(stats)
            st.plotly_chart(fig_terrain, use_container_width=True)

    # --- Export buttons ---
    st.markdown("---")
    col1, col2, col3 = st.columns(3)
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
    with col3:
        refs_text = export_deck_refs(picks)
        st.download_button(
            "Exporter refs",
            data=refs_text,
            file_name="altered_draft_refs.txt",
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
