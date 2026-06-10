# app.py — REIV Market Scorer v3.0
# UX simplifiée : page d'accueil · sidebar allégée · tab Données guidé

import copy
import json
import uuid
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from data import (
    DIMS, MARKETS_DEFAULT, PROFILES, REGION_COLORS, REGION_LABELS,
    VARIABLE_BOUNDS, ONEILL_RSD_CLASS, ONEILL_RSD_PROPTYPE, ONEILL_RSD_LOCTYPE,
)
from scoring import (
    compute_scores, default_var_weights, score_color, risk_color, confidence_color,
    score_to_rating, apply_gate0,
)
from scoring_advanced import (
    full_analysis, sensitivity_analysis,
    compute_momentum, compute_caprate_spread,
    risk_penetration_index, CYCLE_PHASES,
    stress_test_markets,
)
from report import generate_fiche, generate_comparatif

# ── Config ────────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="REIV — Scoring Marchés Hôteliers",
    page_icon="🏨",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
[data-testid="stSidebar"] { background: #0d1117; }
.block-container { padding-top: 1.5rem; }
.stMetric label { font-size: 11px !important; color: #8b92a8 !important; }
div[data-testid="stMetricValue"] { font-size: 1.2rem !important; }
.profile-pill {
    display: inline-block;
    padding: 6px 18px;
    border-radius: 20px;
    font-size: 13px;
    font-weight: 600;
    cursor: pointer;
    border: 1.5px solid;
    margin-right: 6px;
}
</style>
""", unsafe_allow_html=True)

# ── Session state ─────────────────────────────────────────────────────────────

if "markets_pool"  not in st.session_state:
    st.session_state.markets_pool  = copy.deepcopy(MARKETS_DEFAULT)
if "active_ids"    not in st.session_state:
    st.session_state.active_ids    = [m["id"] for m in MARKETS_DEFAULT]
if "dim_weights"   not in st.session_state:
    st.session_state.dim_weights   = dict(PROFILES["Value-add"])
if "var_weights"   not in st.session_state:
    st.session_state.var_weights   = default_var_weights()
if "profile_name"  not in st.session_state:
    st.session_state.profile_name  = "Value-add"
if "norm_method"   not in st.session_state:
    st.session_state.norm_method   = "absolute"

# ── Helpers ───────────────────────────────────────────────────────────────────

def get_active_markets():
    pool = {m["id"]: m for m in st.session_state.markets_pool}
    return [pool[i] for i in st.session_state.active_ids if i in pool]

def blank_market(name, region):
    m = {"id": f"custom_{uuid.uuid4().hex[:8]}", "name": name, "region": region}
    for d in DIMS:
        m[d["id"]] = {v["id"]: 0.0 for v in d["vars"]}
    return m

def badge(text, color, size="10px"):
    return (f"<span style='background:{color}22;color:{color};font-size:{size};"
            f"padding:2px 8px;border-radius:10px;font-weight:600;display:inline-block;'>"
            f"{text}</span>")

# ── SIDEBAR ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("### 🏨 REIV Market Scorer")
    st.caption("v3.0 · Scoring absolu · HVS + CBRE + O'Neill 2023")
    st.divider()

    # ── Profil : 3 boutons bien visibles ──
    st.markdown("**Profil investisseur**")
    profile_cols = st.columns(3)
    for i, (pname, pcols) in enumerate(zip(PROFILES.keys(), profile_cols)):
        colors = {"Core": "#1fbd7e", "Value-add": "#4f7fff", "Opportuniste": "#f0a030"}
        col = colors[pname]
        active = st.session_state.profile_name == pname
        with pcols:
            if st.button(
                pname,
                key=f"profile_btn_{pname}",
                use_container_width=True,
                type="primary" if active else "secondary",
            ):
                st.session_state.profile_name = pname
                st.session_state.dim_weights  = dict(PROFILES[pname])
                st.rerun()

    st.divider()

    # ── Poids dimensions ──
    st.markdown("**Poids des dimensions (%)**")
    for d in DIMS:
        val = st.slider(
            d["label"], 0, 60,
            value=st.session_state.dim_weights.get(d["id"], 0),
            step=1, key=f"dw_{d['id']}",
        )
        st.session_state.dim_weights[d["id"]] = val

    total_w = sum(st.session_state.dim_weights.values())
    delta   = total_w - 100
    if total_w == 100:
        st.caption("Total : **100%** ✅")
    else:
        st.warning(f"Total : **{total_w}%** — {'−' if delta < 0 else '+'}{abs(delta)}% à ajuster", icon="⚠️")

    st.divider()

    # ── Options avancées (cachées par défaut) ──
    with st.expander("⚙️ Options avancées"):
        st.markdown("**Poids intra-dimension**")
        for d in DIMS:
            st.markdown(
                f"<span style='color:{d['color']};font-size:11px;font-weight:500;'>● {d['label']}</span>",
                unsafe_allow_html=True,
            )
            for v in d["vars"]:
                val = st.slider(
                    v["label"], 0, 100,
                    value=st.session_state.var_weights[d["id"]].get(v["id"], 25),
                    step=1, key=f"vw_{d['id']}_{v['id']}",
                )
                st.session_state.var_weights[d["id"]][v["id"]] = val

        st.divider()
        st.markdown("**Moteur de normalisation**")
        norm_method = st.radio(
            "Normalisation", key="norm_radio",
            options=["absolute", "percentile"],
            format_func=lambda x: {
                "absolute":   "Absolu — bornes fixes ✅ (recommandé)",
                "percentile": "Relatif — rang dans le panel",
            }[x],
            index=0,
        )
        st.session_state.norm_method = norm_method

        st.divider()
        st.markdown("**Options moteur**")
        use_nonlinear   = st.toggle("Transformations non-linéaires", value=True)
        use_reliability = st.toggle("Pondération fiabilité source",  value=True)
        use_corr_adjust = st.toggle("Correction corrélations",       value=True)
        run_mc          = st.toggle("Monte Carlo (IC scores)",        value=False,
                                    help="~500 simulations · quelques secondes")
        n_sim           = st.slider("Simulations MC", 100, 2000, 500, 100, disabled=not run_mc)

        st.divider()
        st.markdown("**Paramètres dette**")
        debt_cost = st.number_input("Coût dette hôtelière (%)", 1.0, 12.0, 5.5, 0.1)
        risk_free = st.number_input("Taux sans risque (%)",      0.0,  8.0, 3.2, 0.1)

    st.divider()
    nm = st.session_state.norm_method
    st.caption(
        f"**{len(st.session_state.active_ids)}** marchés actifs · "
        f"{'Absolu' if nm == 'absolute' else 'Relatif'}"
    )

# Valeurs par défaut si options avancées non ouvertes
if "debt_cost" not in dir():
    debt_cost       = 5.5
    risk_free       = 3.2
    use_nonlinear   = True
    use_reliability = True
    use_corr_adjust = True
    run_mc          = False
    n_sim           = 500

# ── Calcul ────────────────────────────────────────────────────────────────────

active_markets = get_active_markets()
if len(active_markets) < 2:
    st.warning("Sélectionnez au moins 2 marchés dans l'onglet **🌍 Marchés**.")
    st.stop()

with st.spinner("Calcul du scoring..."):
    result = full_analysis(
        active_markets,
        st.session_state.dim_weights,
        st.session_state.var_weights,
        norm_method=st.session_state.norm_method,
        debt_cost=debt_cost,
        risk_free=risk_free,
        run_monte_carlo=run_mc,
        n_simulations=n_sim if run_mc else 0,
    )

scores      = result["scores"]
sensitivity = result["sensitivity"]

# ── TABS ──────────────────────────────────────────────────────────────────────

tab_home, tab_markets, tab_rank, tab_rating, tab_matrix, tab_cycle, tab_sensitivity, tab_rpi, tab_data, tab_report = st.tabs([
    "🏠 Accueil", "🌍 Marchés", "📊 Classement", "🎯 Notation & Stress", "🗺️ Matrice",
    "📈 Cycle & Spread", "🎛️ Sensibilité", "🏨 Risque O'Neill",
    "📋 Données", "📄 Rapport",
])

# ── TAB 0 : ACCUEIL ──────────────────────────────────────────────────────────

with tab_home:
    st.markdown("## 🏨 REIV Market Scorer — Guide rapide")
    st.markdown(f"**Profil actif : {st.session_state.profile_name}** · "
                f"{len(active_markets)} marchés · "
                f"Scoring {'absolu' if st.session_state.norm_method == 'absolute' else 'relatif'}")
    st.divider()

    c1, c2 = st.columns([1, 1])
    with c1:
        st.markdown("### Méthodologie")
        st.markdown("""
**7 dimensions de scoring** couvrant le cycle complet d'analyse :

| Dimension | Poids Value-add | Sources |
|-----------|----------------|---------|
| 🔵 Performance hôtelière | 22% | STR Global 2024 |
| 🟢 Pipeline & croissance | 20% | STR Pipeline Report |
| 🟡 Liquidité transactionnelle | 18% | HVS 2025, JLL Hotels |
| 🟣 Fondamentaux macro | 13% | CBRE 2025, Eurostat, FMI |
| 🔴 Risque opérationnel & pays | 9% | O'Neill et al. 2023, Coface |
| 🩷 ESG & durabilité | 5% | BREEAM, EU Taxonomy |
| 🩵 Faisabilité développement | 13% | HVS, Cushman & Wakefield |

**Scoring absolu** (défaut) : chaque variable est normalisée sur des bornes fixes
documentées par source — les scores sont **stables dans le temps** et comparables
entre deux analyses à des dates différentes.
        """)

    with c2:
        st.markdown("### Sources académiques & institutionnelles")
        st.markdown("""
**O'Neill et al. (2023)** — *Cornell Hospitality Quarterly*
→ GOPPAR RSD par classe hôtelière, type de propriété et localisation
→ Risk Penetration Index (Table 21)
→ 3 219 hôtels US, 2015-2020

**HVS 2025 European Hotel Valuation Index**
→ Valeur €/chambre indexée (base 1993=1.000) pour 31 villes européennes
→ CAGR 2015-2024 par marché

**CBRE European Hotels Destination Index (Déc. 2025)**
→ 66 destinations européennes scorées sur 11 facteurs
→ Labour costs (Eurostat), Hospitality Workforce Elasticity

**Choi 1999** — Cycle hôtelier 7.3 ans
**Corgel 2004** — Spread cap rate / coût dette, signal d'entrée
        """)
        st.divider()
        st.markdown("### Guide d'utilisation")
        st.markdown("""
1. **Choisir un profil** (sidebar) → pondérations prédéfinies
2. **Sélectionner les marchés** (onglet Marchés)
3. **Lire le classement** (onglet Classement)
4. **Explorer la matrice** attractivité/risque (onglet Matrice)
5. **Ajuster les pondérations** dans la sidebar si besoin
6. **Générer un rapport HTML** (onglet Rapport)

*Pour des données réelles, remplacer les valeurs indicatives
dans l'onglet Données (export/import JSON).*
        """)

    st.divider()
    st.markdown("### Aperçu du classement actuel")
    k1, k2, k3, k4, k5 = st.columns(5)
    with k1: st.metric("Marchés scorés", len(scores))
    with k2: st.metric("🥇 N°1", scores[0]["name"], f"{scores[0]['total']}/100")
    with k3:
        avg = round(sum(s["total"] for s in scores) / len(scores))
        st.metric("Score moyen panel", avg)
    with k4:
        top3 = ", ".join([s["name"] for s in scores[:3]])
        st.metric("Top 3", top3)
    with k5:
        most_sensitive = max(sensitivity.items(), key=lambda x: x[1]["sensitivity_index"])
        st.metric("Dim. la + sensible", most_sensitive[1]["dim_label"][:18],
                  f"Δ {most_sensitive[1]['sensitivity_index']} rangs")

    # Mini-classement visuel
    st.markdown("#### Classement rapide")
    for i, s in enumerate(scores):
        c = score_color(s["total"])
        region_color = REGION_COLORS.get(s["region"], "#888")
        rt = score_to_rating(s["total"])
        bar_width = s["total"]
        st.markdown(f"""
        <div style="display:flex;align-items:center;gap:10px;margin-bottom:5px;">
          <span style="font-family:monospace;font-size:11px;color:#555e78;width:18px;">{i+1}</span>
          <span style="font-size:13px;font-weight:{'600' if i<3 else '400'};width:100px;">{s['name']}</span>
          <span style="background:{rt['color']}22;color:{rt['color']};font-size:10px;font-weight:700;
                font-family:monospace;padding:1px 7px;border-radius:8px;width:36px;text-align:center;">{rt['rating']}</span>
          <div style="flex:1;height:6px;background:#1c2130;border-radius:3px;overflow:hidden;">
            <div style="width:{bar_width}%;height:100%;background:{c};border-radius:3px;"></div>
          </div>
          <span style="font-family:monospace;font-size:13px;font-weight:500;color:{c};width:32px;">{s['total']}</span>
          {badge(REGION_LABELS.get(s['region'],''), region_color)}
        </div>""", unsafe_allow_html=True)

# ── TAB 1 : GESTION MARCHÉS ──────────────────────────────────────────────────

with tab_markets:
    st.markdown("#### Sélection et gestion des marchés")
    col_sel, col_add = st.columns([1.4, 1])

    with col_sel:
        st.markdown("**Marchés disponibles**")
        region_groups = {}
        for m in st.session_state.markets_pool:
            region_groups.setdefault(m["region"], []).append(m)

        new_active = []
        for region_id, region_markets in sorted(region_groups.items()):
            rc = REGION_COLORS.get(region_id, "#888")
            st.markdown(
                f"<span style='color:{rc};font-size:11px;font-weight:600;"
                f"text-transform:uppercase;letter-spacing:.08em;'>"
                f"● {REGION_LABELS.get(region_id, region_id)}</span>",
                unsafe_allow_html=True,
            )
            for m in region_markets:
                checked = m["id"] in st.session_state.active_ids
                col_cb, col_name, col_del = st.columns([0.08, 0.7, 0.22])
                with col_cb:
                    val = st.checkbox("", value=checked, key=f"cb_{m['id']}",
                                      label_visibility="collapsed")
                with col_name:
                    new_name = st.text_input("Nom", value=m["name"],
                                             key=f"rename_{m['id']}",
                                             label_visibility="collapsed")
                    if new_name != m["name"]:
                        m["name"] = new_name
                with col_del:
                    if st.button("🗑", key=f"del_{m['id']}"):
                        st.session_state.markets_pool = [
                            x for x in st.session_state.markets_pool if x["id"] != m["id"]
                        ]
                        st.session_state.active_ids = [
                            x for x in st.session_state.active_ids if x != m["id"]
                        ]
                        st.rerun()
                if val:
                    new_active.append(m["id"])

        st.session_state.active_ids = [
            mid for mid in [m["id"] for m in st.session_state.markets_pool]
            if mid in new_active
        ]
        st.caption(f"**{len(st.session_state.active_ids)}** marchés sélectionnés")

    with col_add:
        st.markdown("**Ajouter un marché**")
        with st.form("add_market_form"):
            new_name   = st.text_input("Nom de la ville", placeholder="ex: Istanbul")
            new_region = st.selectbox("Région", options=list(REGION_LABELS.keys()),
                                      format_func=lambda x: REGION_LABELS[x])
            if st.form_submit_button("➕ Ajouter", use_container_width=True):
                if new_name.strip():
                    existing = [m["name"].lower() for m in st.session_state.markets_pool]
                    if new_name.strip().lower() in existing:
                        st.error(f"'{new_name}' existe déjà.")
                    else:
                        nm = blank_market(new_name.strip(), new_region)
                        st.session_state.markets_pool.append(nm)
                        st.session_state.active_ids.append(nm["id"])
                        st.success(f"'{new_name}' ajouté — renseignez ses données dans l'onglet **Données**.")
                        st.rerun()

        st.divider()
        ca, cb = st.columns(2)
        with ca:
            if st.button("✅ Tout", key="sel_all", use_container_width=True):
                st.session_state.active_ids = [m["id"] for m in st.session_state.markets_pool]
                st.rerun()
        with cb:
            if st.button("☐ Aucun", key="sel_none", use_container_width=True):
                st.session_state.active_ids = []
                st.rerun()
        for region_id, region_label in REGION_LABELS.items():
            ids = [m["id"] for m in st.session_state.markets_pool if m["region"] == region_id]
            if ids and st.button(f"● {region_label}", key=f"sel_region_{region_id}",
                                  use_container_width=True):
                existing = set(st.session_state.active_ids)
                for rid in ids:
                    existing.add(rid)
                st.session_state.active_ids = [
                    m["id"] for m in st.session_state.markets_pool if m["id"] in existing
                ]
                st.rerun()
        st.divider()
        if st.button("🔄 Réinitialiser pool", key="reset_markets_tab", use_container_width=True):
            st.session_state.markets_pool = copy.deepcopy(MARKETS_DEFAULT)
            st.session_state.active_ids   = [m["id"] for m in MARKETS_DEFAULT]
            st.rerun()

# ── TAB 2 : CLASSEMENT ───────────────────────────────────────────────────────

with tab_rank:
    col_left, col_right = st.columns([1, 1])

    with col_left:
        st.markdown("#### Classement enrichi")
        rows = []
        for i, s in enumerate(scores):
            cluster = s.get("cluster", {})
            mc_d    = s.get("mc", {})
            rows.append({
                "Rang":      i + 1,
                "Marché":    s["name"],
                "Région":    REGION_LABELS.get(s["region"], s["region"]),
                "Score":     s["total"],
                "IC P10-P90":f"{mc_d.get('ci_low','?')}–{mc_d.get('ci_high','?')}" if mc_d else "—",
                "Cluster":   cluster.get("label", "—"),
                "Confiance": round(s["confidence"] * 100),
                **{d["label"][:14]: s["dims"][d["id"]] for d in DIMS},
                "Risque":    s["risk_raw"],
            })
        df_rank = pd.DataFrame(rows)
        st.dataframe(
            df_rank, use_container_width=True, hide_index=True,
            column_config={
                "Score":     st.column_config.ProgressColumn("Score",    min_value=0, max_value=100),
                "Risque":    st.column_config.ProgressColumn("Risque",   min_value=0, max_value=100),
                "Confiance": st.column_config.ProgressColumn("Confiance %", min_value=0, max_value=100),
            },
        )

    with col_right:
        st.markdown("#### Fiche marché")
        sel_name = st.selectbox("Marché", [s["name"] for s in scores], key="fiche_sel")
        sel      = next((s for s in scores if s["name"] == sel_name), scores[0])
        c        = score_color(sel["total"])
        rc       = risk_color(sel["risk_raw"])
        cc       = confidence_color(sel["confidence"])
        region_color = REGION_COLORS.get(sel["region"], "#888")
        mc_d    = sel.get("mc", {})
        cluster = sel.get("cluster", {})

        st.markdown(f"""
        <div style="background:#141720;border:1px solid #252b3b;border-radius:10px;padding:16px;">
          <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:10px;">
            <div>
              <div style="font-size:17px;font-weight:600;">{sel['name']}</div>
              {badge(REGION_LABELS.get(sel['region'],''), region_color)}
              {(' ' + badge(cluster.get('label',''), cluster.get('color','#888'))) if cluster else ''}
            </div>
            <div style="text-align:right;">
              <div style="font-size:30px;font-weight:600;font-family:monospace;color:{c};">{sel['total']}</div>
              <div style="font-size:10px;color:#555e78;">/ 100</div>
              {'<div style="font-size:10px;color:#555e78;">IC P10-P90 : ' + str(mc_d.get('ci_low','?')) + '–' + str(mc_d.get('ci_high','?')) + '</div>' if mc_d else ''}
            </div>
          </div>
        """, unsafe_allow_html=True)

        for d in DIMS:
            v  = sel["dims"][d["id"]]
            dc = score_color(v)
            # Borne max pour affichage relatif dans la fiche
            bound_info = f"{v}/100"
            st.markdown(f"""
            <div style="margin-bottom:7px;">
              <div style="display:flex;justify-content:space-between;font-size:11px;color:#8b92a8;margin-bottom:2px;">
                <span><span style="display:inline-block;width:6px;height:6px;border-radius:50%;
                  background:{d['color']};margin-right:4px;vertical-align:middle;"></span>{d['label']}</span>
                <span style="font-weight:500;color:{dc};">{bound_info}</span>
              </div>
              <div style="height:3px;background:#1c2130;border-radius:2px;overflow:hidden;">
                <div style="width:{v}%;height:100%;background:{d['color']};border-radius:2px;"></div>
              </div>
            </div>""", unsafe_allow_html=True)

        outliers    = sel.get("outlier_flags", {})
        outlier_str = ", ".join(outliers.keys()) if outliers else "Aucun"
        st.markdown(f"""
          <div style="border-top:1px solid #252b3b;padding-top:8px;margin-top:6px;font-size:10px;color:#8b92a8;">
            <div style="display:flex;justify-content:space-between;margin-bottom:3px;">
              <span>Risque brut composite</span>
              <span style="font-weight:500;color:{rc};font-family:monospace;">{sel['risk_raw']}/100</span>
            </div>
            <div style="display:flex;justify-content:space-between;margin-bottom:3px;">
              <span>Indice de confiance</span>
              <span style="font-weight:500;color:{cc};font-family:monospace;">{round(sel['confidence']*100)}%</span>
            </div>
            <div style="display:flex;justify-content:space-between;">
              <span>Variables outliers détectés</span>
              <span style="color:#f0a030;">{outlier_str}</span>
            </div>
          </div>
        </div>
        """, unsafe_allow_html=True)

# ── TAB : NOTATION & STRESS ──────────────────────────────────────────────────

with tab_rating:
    st.markdown("#### Notation AAA-CCC · Gate 0 politique · Stress tests")
    st.caption(
        f"Profil **{st.session_state.profile_name}** — "
        "Gate 0 = filtre éliminatoire de stabilité politique avant scoring. "
        "Haircut politique appliqué post-scoring. "
        "Stress : Base (50%) / Upside (20%) / Downside (30%) — chocs calibrés récession 2008-09 hôtelière."
    )

    with st.spinner("Stress test en cours..."):
        stress = stress_test_markets(
            active_markets,
            st.session_state.dim_weights,
            st.session_state.var_weights,
            profile_name=st.session_state.profile_name,
        )

    # ── Marchés éliminés Gate 0 ──
    eliminated = {mid: r for mid, r in stress.items() if not r["gate0"]["passed"]}
    if eliminated:
        st.markdown("##### 🚪 Gate 0 — marchés éliminés")
        for mid, r in eliminated.items():
            reasons = " · ".join(r["gate0"]["reasons"])
            st.markdown(
                f"<div style='background:#e2504a15;border-left:3px solid #e2504a;"
                f"border-radius:4px;padding:8px 12px;margin-bottom:6px;'>"
                f"<span style='font-size:13px;font-weight:600;color:#e2504a;'>❌ {r['name']}</span>"
                f"<span style='font-size:11px;color:#8b92a8;margin-left:10px;'>{reasons}</span>"
                f"</div>",
                unsafe_allow_html=True,
            )
        st.caption(
            f"Le profil {st.session_state.profile_name} exige une stabilité politique minimale "
            "— aucune pondération ne peut compenser un risque pays rédhibitoire."
        )
        st.divider()

    # ── Matrice de stress ──
    st.markdown("##### Matrice de stress — notation par scénario")

    rows_stress = []
    for mid, r in sorted(stress.items(),
                          key=lambda x: -x[1]["scenarios"].get("base", {}).get("score_final", 0)):
        b = r["scenarios"].get("base", {})
        u = r["scenarios"].get("upside", {})
        d = r["scenarios"].get("downside", {})
        rows_stress.append({
            "Marché":        r["name"],
            "Gate 0":        "✅" if r["gate0"]["passed"] else "❌ Éliminé",
            "Haircut pol.":  f"−{b.get('haircut_pct', 0)}%" if b.get("haircut_pct", 0) > 0 else "—",
            "Base":          b.get("score_final", 0),
            "Note base":     b.get("rating", "—"),
            "Upside":        u.get("score_final", 0),
            "Note upside":   u.get("rating", "—"),
            "Downside":      d.get("score_final", 0),
            "Note downside": d.get("rating", "—"),
            "Δ crans":       r["delta_downside"],
            "Résilience":    r["resilience"],
            "Zone interdite":"🚫" if r["forbidden"] else "",
        })

    df_stress = pd.DataFrame(rows_stress)
    st.dataframe(
        df_stress, use_container_width=True, hide_index=True,
        column_config={
            "Base":     st.column_config.ProgressColumn("Base",     min_value=0, max_value=70),
            "Upside":   st.column_config.ProgressColumn("Upside",   min_value=0, max_value=70),
            "Downside": st.column_config.ProgressColumn("Downside", min_value=0, max_value=70),
        },
    )

    st.divider()
    col_s1, col_s2 = st.columns([1.3, 1])

    with col_s1:
        st.markdown("##### Vue par marché — barres base / downside")
        # Tri par score base
        sorted_stress = sorted(
            [(mid, r) for mid, r in stress.items() if r["gate0"]["passed"]],
            key=lambda x: -x[1]["scenarios"].get("base", {}).get("score_final", 0),
        )
        for mid, r in sorted_stress:
            b = r["scenarios"].get("base", {})
            d = r["scenarios"].get("downside", {})
            u = r["scenarios"].get("upside", {})
            base_score = b.get("score_final", 0)
            down_score = d.get("score_final", 0)
            up_score   = u.get("score_final", 0)
            res_color  = r["resilience_color"]
            forbidden  = " 🚫" if r["forbidden"] else ""

            st.markdown(f"""
            <div style="margin-bottom:10px;">
              <div style="display:flex;justify-content:space-between;font-size:12px;margin-bottom:3px;">
                <span style="font-weight:500;">{r['name']}{forbidden}</span>
                <span>
                  <span style="background:{d.get('color','#888')}22;color:{d.get('color','#888')};
                        font-size:10px;padding:1px 6px;border-radius:8px;font-family:monospace;">
                    {d.get('rating','—')}</span>
                  <span style="color:#555e78;font-size:10px;">←</span>
                  <span style="background:{b.get('color','#888')}22;color:{b.get('color','#888')};
                        font-size:10px;padding:1px 6px;border-radius:8px;font-weight:600;font-family:monospace;">
                    {b.get('rating','—')}</span>
                  <span style="color:#555e78;font-size:10px;">→</span>
                  <span style="background:{u.get('color','#888')}22;color:{u.get('color','#888')};
                        font-size:10px;padding:1px 6px;border-radius:8px;font-family:monospace;">
                    {u.get('rating','—')}</span>
                  <span style="color:{res_color};font-size:10px;font-weight:500;margin-left:8px;">
                    {r['resilience']}</span>
                </span>
              </div>
              <div style="position:relative;height:8px;background:#1c2130;border-radius:4px;overflow:hidden;">
                <div style="position:absolute;left:0;width:{up_score}%;height:100%;
                     background:#1fbd7e22;border-radius:4px;"></div>
                <div style="position:absolute;left:0;width:{base_score}%;height:100%;
                     background:{b.get('color','#4f7fff')}66;border-radius:4px;"></div>
                <div style="position:absolute;left:0;width:{down_score}%;height:100%;
                     background:{b.get('color','#4f7fff')};border-radius:4px;"></div>
              </div>
              <div style="display:flex;justify-content:space-between;font-size:9px;color:#555e78;font-family:monospace;">
                <span>down {down_score}</span><span>base {base_score}</span><span>up {up_score}</span>
              </div>
            </div>""", unsafe_allow_html=True)

    with col_s2:
        st.markdown("##### Grille de notation")
        from data import RATING_SCALE, GATE0_THRESHOLDS, STRESS_SCENARIOS
        df_scale = pd.DataFrame([
            {"Note": r[1], "Seuil": f"≥ {r[0]}" if r[0] > 0 else "< 33", "Interprétation": r[2]}
            for r in RATING_SCALE
        ])
        st.dataframe(df_scale, hide_index=True, use_container_width=True)
        st.caption(
            "Seuils calibrés sur la distribution empirique du scoring absolu "
            "(bornes mondiales → panel EU/MENA entre ~30 et ~58)."
        )

        st.markdown("##### Seuils Gate 0 par profil")
        df_gate = pd.DataFrame([
            {"Profil": p, "Risque pol. max": f"{t['pol_risk_max']}/5",
             "Expo géo max": f"{t['geo_exp_max']}/5"}
            for p, t in GATE0_THRESHOLDS.items()
        ])
        st.dataframe(df_gate, hide_index=True, use_container_width=True)

        st.markdown("##### Chocs downside appliqués")
        down = STRESS_SCENARIOS["downside"]["shocks"]
        shock_labels = {
            "revpar": "RevPAR", "occ": "Occupation", "adr": "ADR",
            "revpar_g": "Croissance RevPAR", "gdp_g": "Croissance PIB",
            "caprate": "Cap rate", "vol_tx": "Volume transactions",
            "nb_deals": "Nb deals", "tourists": "Arrivées",
            "pip_ratio": "Pipeline", "hvi_cagr": "HVI CAGR",
        }
        df_shocks = pd.DataFrame([
            {"Variable": shock_labels.get(k, k),
             "Choc": f"×{v[1]}" if v[0] == "mult" else f"{'+' if v[1] > 0 else ''}{v[1]}"}
            for k, v in down.items()
        ])
        st.dataframe(df_shocks, hide_index=True, use_container_width=True)

# ── TAB 3 : MATRICE ──────────────────────────────────────────────────────────

with tab_matrix:
    col_m1, col_m2 = st.columns([2, 1])

    with col_m1:
        st.markdown("#### Matrice attractivité / risque")
        df_matrix = pd.DataFrame([{
            "Marché":       s["name"],
            "Attractivité": s["total"],
            "Risque":       s["risk_raw"],
            "Région":       REGION_LABELS.get(s["region"], s["region"]),
            "Score":        s["total"],
            "Cluster":      s.get("cluster", {}).get("label", "—"),
        } for s in scores])

        color_map = {REGION_LABELS[k]: v for k, v in REGION_COLORS.items()}
        fig = px.scatter(
            df_matrix, x="Risque", y="Attractivité", text="Marché",
            color="Région", size="Score", size_max=28,
            color_discrete_map=color_map, template="plotly_dark",
            hover_data=["Cluster"],
        )
        fig.update_traces(textposition="top center", textfont_size=10)
        fig.update_layout(
            plot_bgcolor="#0d0f12", paper_bgcolor="#0d0f12", height=480,
            font=dict(family="Inter", size=11, color="#8b92a8"),
            xaxis=dict(title="← Faible risque   Risque élevé →",
                       gridcolor="#1c2130", range=[0, 100]),
            yaxis=dict(title="Attractivité →",
                       gridcolor="#1c2130", range=[20, 100]),
            legend=dict(bgcolor="#141720", bordercolor="#252b3b", borderwidth=1),
            margin=dict(l=40, r=20, t=20, b=40),
        )
        fig.add_shape(type="line", x0=50, x1=50, y0=20, y1=100,
                      line=dict(color="#252b3b", dash="dot"))
        fig.add_shape(type="line", x0=0,  x1=100, y0=50, y1=50,
                      line=dict(color="#252b3b", dash="dot"))
        fig.add_annotation(x=15, y=95, text="★ Core cibles",   showarrow=False, font=dict(size=9, color="#1fbd7e"))
        fig.add_annotation(x=78, y=95, text="⚡ Opportuniste", showarrow=False, font=dict(size=9, color="#f0a030"))
        fig.add_annotation(x=15, y=25, text="⚠ Éviter",        showarrow=False, font=dict(size=9, color="#555e78"))
        fig.add_annotation(x=78, y=25, text="🔍 Surveiller",   showarrow=False, font=dict(size=9, color="#555e78"))
        st.plotly_chart(fig, use_container_width=True)

    with col_m2:
        st.markdown("#### Clusters K-means")
        cluster_groups = {}
        for s in scores:
            cl    = s.get("cluster", {})
            label = cl.get("label", "—")
            cluster_groups.setdefault(label, {"color": cl.get("color", "#888"), "markets": []})
            cluster_groups[label]["markets"].append(s["name"])

        for label, data in cluster_groups.items():
            st.markdown(
                f"<div style='background:{data['color']}15;border-left:3px solid {data['color']};"
                f"border-radius:4px;padding:8px 10px;margin-bottom:8px;'>"
                f"<div style='font-size:12px;font-weight:500;color:{data['color']};margin-bottom:4px;'>"
                f"{label}</div>"
                f"<div style='font-size:11px;color:#8b92a8;'>{', '.join(data['markets'])}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )
        sil = scores[0].get("cluster", {}).get("silhouette", None)
        if sil:
            st.caption(f"Silhouette : **{sil}** {'✅' if sil > 0.4 else '(acceptable)'}")

# ── TAB 4 : CYCLE & SPREAD ───────────────────────────────────────────────────

with tab_cycle:
    st.markdown("#### Momentum hôtelier & Spread cap rate / coût dette")
    st.caption("Cycle hôtelier (Choi 1999) · Signal d'entrée spread (Corgel 2004)")

    rows_cycle = []
    for s in scores:
        m = next((mm for mm in active_markets if mm["id"] == s["id"]), None)
        if not m:
            continue
        mom = s.get("momentum", compute_momentum(m))
        spr = s.get("spread",   compute_caprate_spread(m, debt_cost, risk_free))
        rows_cycle.append({
            "Marché":        s["name"],
            "Score":         s["total"],
            "Phase cycle":   mom["cycle_label"],
            "Momentum":      mom["momentum_score"],
            "RevPAR growth": f"{mom['revpar_g']}%",
            "Occupation":    f"{mom['occ']}%",
            "Cap rate":      f"{spr['caprate']}%",
            "Spread":        f"{spr['spread']}%",
            "Signal entrée": spr["entry_signal"],
        })

    df_cycle = pd.DataFrame(rows_cycle)
    fig_cyc = px.scatter(
        df_cycle, x="Momentum", y="Score", text="Marché",
        color="Phase cycle",
        color_discrete_map={
            "Expansion": "#1fbd7e", "Peak":       "#f0a030",
            "Contraction": "#e2504a", "Creux":    "#4f7fff",
        },
        template="plotly_dark", title="Positionnement cycle hôtelier",
    )
    fig_cyc.update_traces(textposition="top center", textfont_size=9)
    fig_cyc.update_layout(
        plot_bgcolor="#0d0f12", paper_bgcolor="#0d0f12", height=380,
        font=dict(family="Inter", size=11, color="#8b92a8"),
        margin=dict(l=40, r=20, t=40, b=40),
    )
    st.plotly_chart(fig_cyc, use_container_width=True)
    st.markdown("#### Tableau cycle & spread")
    st.dataframe(df_cycle, use_container_width=True, hide_index=True)

# ── TAB 5 : SENSIBILITÉ ──────────────────────────────────────────────────────

with tab_sensitivity:
    st.markdown("#### Analyse de sensibilité des pondérations")
    st.caption("Impact d'une variation ±10% de chaque dimension sur le classement final.")

    dim_labels = [data["dim_label"][:18] for data in sensitivity.values()]
    dim_values = [data["sensitivity_index"] for data in sensitivity.values()]

    fig_radar = go.Figure()
    fig_radar.add_trace(go.Scatterpolar(
        r=dim_values + [dim_values[0]],
        theta=dim_labels + [dim_labels[0]],
        fill="toself",
        fillcolor="rgba(79,127,255,0.15)",
        line=dict(color="#4f7fff", width=2),
        name="Sensibilité",
    ))
    fig_radar.update_layout(
        polar=dict(
            bgcolor="#141720",
            radialaxis=dict(
                visible=True, range=[0, max(dim_values) * 1.2],
                gridcolor="#252b3b", tickcolor="#555e78",
                tickfont=dict(size=9, color="#8b92a8"),
            ),
            angularaxis=dict(tickfont=dict(size=10, color="#e8eaf0")),
        ),
        paper_bgcolor="#0d0f12", plot_bgcolor="#0d0f12",
        height=350, showlegend=False,
        margin=dict(l=60, r=60, t=30, b=30),
    )
    st.plotly_chart(fig_radar, use_container_width=True)

    st.markdown("#### Impact par dimension (Δ rang)")
    for dim_id, data in sensitivity.items():
        with st.expander(f"{data['dim_label']} — sensibilité {data['sensitivity_index']} rangs"):
            rows_s = []
            for s in scores:
                mid  = s["id"]
                rc_d = data["rank_changes"].get(mid, {})
                sc_d = data["score_changes"].get(mid, {})
                rows_s.append({
                    "Marché":            s["name"],
                    "Score base":        s["total"],
                    "Δ rang (+10%)":     rc_d.get("up", 0),
                    "Δ rang (−10%)":     rc_d.get("down", 0),
                    "Δ score (+10%)":    sc_d.get("up", 0),
                    "Δ score (−10%)":    sc_d.get("down", 0),
                    "Vulnérabilité max": rc_d.get("max_abs", 0),
                })
            st.dataframe(pd.DataFrame(rows_s), hide_index=True, use_container_width=True)

# ── TAB 6 : RISQUE O'NEILL ────────────────────────────────────────────────────

with tab_rpi:
    st.markdown("#### Risk Penetration Index — O'Neill et al. 2023 (Cornell)")
    st.caption(
        "Indice 100 = moyenne du panel. "
        "Source : GOPPAR RSD benchmarks — 3 219 hôtels US 2015-2020, Cornell Hospitality Quarterly."
    )

    rows_rpi = []
    for i, s in enumerate(scores):
        rpi    = s.get("rpi", {})
        oneill = s.get("oneill", {})
        if not rpi:
            continue
        rows_rpi.append({
            "Rang":            i + 1,
            "Marché":          s["name"],
            "Classe":          oneill.get("class", "—").replace("_", " ").title(),
            "Type":            oneill.get("proptype", "—").replace("_", " ").title(),
            "GOP Margin %":    rpi.get("gop_margin_raw", 0),
            "Margin Index":    rpi.get("gop_margin_idx", 100),
            "GOPPAR (€)":      rpi.get("goppar_raw", 0),
            "GOPPAR Index":    rpi.get("goppar_idx", 100),
            "GOPPAR RSD %":    rpi.get("goppar_rsd_raw", 0),
            "RSD Index":       rpi.get("goppar_rsd_idx", 100),
            "Verdict":         rpi.get("verdict", "—"),
        })

    if rows_rpi:
        st.dataframe(
            pd.DataFrame(rows_rpi), use_container_width=True, hide_index=True,
            column_config={
                "Margin Index": st.column_config.ProgressColumn("Margin Index", min_value=0, max_value=200),
                "GOPPAR Index": st.column_config.ProgressColumn("GOPPAR Index", min_value=0, max_value=200),
                "RSD Index":    st.column_config.NumberColumn("RSD Index", help="< 100 = moins risqué"),
            },
        )

    st.divider()
    col_r1, col_r2 = st.columns(2)

    with col_r1:
        st.markdown("#### Profil O'Neill par marché")
        for s in scores:
            oneill = s.get("oneill", {})
            rpi    = s.get("rpi", {})
            if not oneill or not rpi:
                continue
            vc    = rpi.get("verdict_color", "#888")
            verd  = rpi.get("verdict", "—")
            rsd   = rpi.get("goppar_rsd_raw", 0)
            rsd_c = "#1fbd7e" if rsd < 35 else "#f0a030" if rsd < 50 else "#e2504a"
            st.markdown(f"""
            <div style="background:#141720;border:1px solid #252b3b;border-radius:8px;
                        padding:8px 12px;margin-bottom:5px;display:flex;
                        justify-content:space-between;align-items:center;">
              <div>
                <span style="font-size:13px;font-weight:500;">{s['name']}</span>
                <span style="font-size:10px;color:#8b92a8;margin-left:8px;">
                  {oneill.get('class','').replace('_',' ').title()} ·
                  {oneill.get('proptype','').replace('_',' ').title()}
                </span>
              </div>
              <div style="display:flex;align-items:center;gap:10px;">
                <span style="font-family:monospace;font-size:11px;color:{rsd_c};">RSD {rsd}%</span>
                <span style="font-size:11px;font-weight:500;color:{vc};">{verd}</span>
              </div>
            </div>""", unsafe_allow_html=True)

    with col_r2:
        st.markdown("#### GOPPAR vs RSD")
        df_scatter = pd.DataFrame([{
            "Marché":       s["name"],
            "GOPPAR (€)":   s.get("rpi", {}).get("goppar_raw", 0),
            "GOPPAR RSD %": s.get("rpi", {}).get("goppar_rsd_raw", 0),
            "Score":        s["total"],
            "Verdict":      s.get("rpi", {}).get("verdict", "—"),
        } for s in scores if s.get("rpi")])

        if not df_scatter.empty:
            fig_rpi = px.scatter(
                df_scatter, x="GOPPAR RSD %", y="GOPPAR (€)",
                text="Marché", size="Score", size_max=22,
                color="Verdict",
                color_discrete_map={
                    "★ Attractif": "#1fbd7e", "◎ Correct": "#4f7fff",
                    "△ Mitigé": "#f0a030", "✗ Défavorable": "#e2504a",
                },
                template="plotly_dark",
            )
            fig_rpi.update_traces(textposition="top center", textfont_size=9)
            fig_rpi.update_layout(
                plot_bgcolor="#0d0f12", paper_bgcolor="#0d0f12", height=360,
                font=dict(family="Inter", size=11, color="#8b92a8"),
                xaxis=dict(title="GOPPAR RSD % →", gridcolor="#1c2130"),
                yaxis=dict(title="GOPPAR € →",     gridcolor="#1c2130"),
                margin=dict(l=40, r=20, t=20, b=40),
            )
            med_rsd    = df_scatter["GOPPAR RSD %"].median()
            med_goppar = df_scatter["GOPPAR (€)"].median()
            fig_rpi.add_shape(type="line", x0=med_rsd, x1=med_rsd,
                y0=0, y1=df_scatter["GOPPAR (€)"].max() * 1.1,
                line=dict(color="#252b3b", dash="dot"))
            fig_rpi.add_shape(type="line",
                x0=0, x1=df_scatter["GOPPAR RSD %"].max() * 1.1,
                y0=med_goppar, y1=med_goppar,
                line=dict(color="#252b3b", dash="dot"))
            fig_rpi.add_annotation(
                x=df_scatter["GOPPAR RSD %"].min() + 1,
                y=df_scatter["GOPPAR (€)"].max() * 1.05,
                text="★ Idéal", showarrow=False, font=dict(size=9, color="#1fbd7e"),
            )
            st.plotly_chart(fig_rpi, use_container_width=True)

    st.divider()
    st.markdown("#### Référentiels O'Neill 2023")
    col_ref1, col_ref2, col_ref3 = st.columns(3)
    with col_ref1:
        st.markdown("**Par classe**")
        st.dataframe(pd.DataFrame([
            {"Classe": k.replace("_", " ").title(), "RSD %": v}
            for k, v in sorted(ONEILL_RSD_CLASS.items(), key=lambda x: x[1])
        ]), hide_index=True, use_container_width=True)
    with col_ref2:
        st.markdown("**Par type de propriété**")
        st.dataframe(pd.DataFrame([
            {"Type": k.replace("_", " ").title(), "RSD %": v}
            for k, v in sorted(ONEILL_RSD_PROPTYPE.items(), key=lambda x: x[1])
        ]), hide_index=True, use_container_width=True)
    with col_ref3:
        st.markdown("**Par localisation**")
        st.dataframe(pd.DataFrame([
            {"Localisation": k.replace("_", " ").title(), "RSD %": v}
            for k, v in sorted(ONEILL_RSD_LOCTYPE.items(), key=lambda x: x[1])
        ]), hide_index=True, use_container_width=True)

# ── TAB 7 : DONNÉES ──────────────────────────────────────────────────────────

with tab_data:
    st.markdown("#### Données brutes — marchés actifs")

    # Guide de saisie
    with st.expander("📖 Guide de saisie — bornes et sources", expanded=False):
        bounds_rows = []
        for d in DIMS:
            for v in d["vars"]:
                b = VARIABLE_BOUNDS.get(v["id"])
                if b:
                    bounds_rows.append({
                        "Dimension":   d["label"],
                        "Variable":    v["label"],
                        "Min absolu":  b[0],
                        "Max absolu":  b[1],
                        "Unité":       v.get("unit", ""),
                        "Direction":   "↑ plus élevé = mieux" if v["dir"] == 1 else "↓ plus bas = mieux",
                    })
        st.dataframe(pd.DataFrame(bounds_rows), hide_index=True, use_container_width=True)
        st.caption("Les bornes absolues définissent l'espace de normalisation — "
                   "une valeur hors borne sera clampée. Sources : STR, HVS, CBRE, Eurostat, Coface.")

    # Tableau éditable
    rows_d = []
    for m in active_markets:
        row = {"Marché": m["name"], "Région": m["region"]}
        for d in DIMS:
            for v in d["vars"]:
                row[v["label"]] = m[d["id"]][v["id"]]
        rows_d.append(row)

    df_edit = pd.DataFrame(rows_d)

    # Configuration des colonnes avec bornes min/max
    col_config = {}
    for d in DIMS:
        for v in d["vars"]:
            b = VARIABLE_BOUNDS.get(v["id"])
            if b:
                col_config[v["label"]] = st.column_config.NumberColumn(
                    v["label"],
                    min_value=float(b[0]),
                    max_value=float(b[1]),
                    help=f"Source : {v.get('unit','—')} · Borne [{b[0]}, {b[1]}]",
                )

    edited = st.data_editor(
        df_edit, use_container_width=True, hide_index=True,
        key="data_editor", column_config=col_config,
    )

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        if st.button("✅ Appliquer", key="apply_data", use_container_width=True):
            for i, m in enumerate(active_markets):
                for d in DIMS:
                    for v in d["vars"]:
                        try:
                            m[d["id"]][v["id"]] = float(edited.at[i, v["label"]])
                        except Exception:
                            pass
            st.success("Données mises à jour.")
            st.rerun()
    with c2:
        if st.button("🔄 Réinitialiser", key="reset_data_tab", use_container_width=True):
            st.session_state.markets_pool = copy.deepcopy(MARKETS_DEFAULT)
            st.session_state.active_ids   = [m["id"] for m in MARKETS_DEFAULT]
            st.rerun()
    with c3:
        json_data = json.dumps(st.session_state.markets_pool, ensure_ascii=False, indent=2)
        st.download_button(
            "⬇️ Export JSON", data=json_data,
            file_name="reiv_markets_pool.json", mime="application/json",
            use_container_width=True,
        )
    with c4:
        uploaded = st.file_uploader("Import JSON", type="json", label_visibility="collapsed")
        if uploaded:
            try:
                imported = json.load(uploaded)
                st.session_state.markets_pool = imported
                st.session_state.active_ids   = [m["id"] for m in imported]
                st.success(f"{len(imported)} marchés importés.")
                st.rerun()
            except Exception as e:
                st.error(f"Erreur : {e}")

# ── TAB 8 : RAPPORT ──────────────────────────────────────────────────────────

with tab_report:
    st.markdown("#### Génération de rapport HTML")
    st.caption("Le rapport est téléchargeable et s'ouvre dans tout navigateur.")

    report_type = st.radio(
        "Type de rapport",
        ["Fiche individuelle", "Rapport comparatif Top N"],
        horizontal=True,
    )

    if report_type == "Fiche individuelle":
        sel_r      = st.selectbox("Marché à exporter", [s["name"] for s in scores], key="rep_mkt")
        sel_score  = next((s for s in scores if s["name"] == sel_r), scores[0])
        sel_data   = next((m for m in active_markets if m["name"] == sel_r), active_markets[0])
        if st.button("📄 Générer la fiche", key="gen_fiche", type="primary"):
            html = generate_fiche(
                sel_data, sel_score,
                st.session_state.dim_weights,
                st.session_state.profile_name,
            )
            st.download_button(
                f"⬇️ fiche_{sel_r.replace(' ','_').lower()}.html",
                data=html.encode("utf-8"),
                file_name=f"reiv_fiche_{sel_r.replace(' ','_').lower()}.html",
                mime="text/html",
            )
            with st.expander("Aperçu"):
                st.components.v1.html(html, height=600, scrolling=True)

    else:
        top_n = st.slider("Nombre de marchés", 2, len(scores), min(5, len(scores)))
        st.caption(f"Top {top_n} : {', '.join([s['name'] for s in scores[:top_n]])}")
        if st.button("📄 Générer le comparatif", key="gen_comparatif", type="primary"):
            html = generate_comparatif(
                scores, top_n,
                st.session_state.dim_weights,
                st.session_state.profile_name,
            )
            st.download_button(
                f"⬇️ comparatif_top{top_n}.html",
                data=html.encode("utf-8"),
                file_name=f"reiv_comparatif_top{top_n}.html",
                mime="text/html",
            )
            with st.expander("Aperçu"):
                st.components.v1.html(html, height=600, scrolling=True)
