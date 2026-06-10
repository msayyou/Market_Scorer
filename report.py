# report.py — REIV Market Scorer
# Générateur de rapports HTML : fiche marché individuelle + rapport comparatif

from datetime import date
from data import DIMS, REGION_LABELS, REGION_COLORS
from scoring import score_color, risk_color


# ── CSS commun ──────────────────────────────────────────────────────────────

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');
*{box-sizing:border-box;margin:0;padding:0;}
body{font-family:'Inter',sans-serif;background:#0d0f12;color:#e8eaf0;font-size:13px;line-height:1.6;padding:32px;}
h1{font-size:22px;font-weight:600;color:#fff;margin-bottom:4px;}
h2{font-size:15px;font-weight:500;color:#e8eaf0;margin-bottom:12px;}
h3{font-size:12px;font-weight:600;letter-spacing:.08em;text-transform:uppercase;color:#555e78;margin-bottom:10px;}
.mono{font-family:'JetBrains Mono',monospace;}
.card{background:#141720;border:1px solid #252b3b;border-radius:10px;padding:18px;margin-bottom:16px;}
.row{display:flex;gap:16px;}
.col{flex:1;min-width:0;}
.tag{display:inline-block;font-size:10px;padding:2px 8px;border-radius:10px;font-weight:600;letter-spacing:.03em;}
.bar-bg{height:4px;background:#1c2130;border-radius:2px;overflow:hidden;margin-top:3px;}
.bar-fill{height:100%;border-radius:2px;}
.dim-row{margin-bottom:10px;}
.dim-label{display:flex;justify-content:space-between;font-size:11px;color:#8b92a8;margin-bottom:2px;}
.dim-val{font-weight:500;}
.dot{display:inline-block;width:7px;height:7px;border-radius:50%;margin-right:5px;vertical-align:middle;}
.footer{margin-top:32px;padding-top:12px;border-top:1px solid #252b3b;font-size:10px;color:#555e78;display:flex;justify-content:space-between;}
hr{border:none;border-top:1px solid #252b3b;margin:16px 0;}
table.vars{width:100%;border-collapse:collapse;font-size:11px;}
table.vars th{background:#1c2130;color:#555e78;padding:5px 8px;text-align:left;font-weight:500;border-bottom:1px solid #252b3b;}
table.vars td{padding:5px 8px;border-bottom:1px solid #1c2130;color:#e8eaf0;}
table.vars tr:hover td{background:#1c2130;}
.score-big{font-size:38px;font-weight:600;line-height:1;font-family:'JetBrains Mono',monospace;}
.score-label{font-size:10px;color:#555e78;margin-top:2px;}
.region-header{font-size:11px;margin-top:3px;}
.risk-block{display:flex;justify-content:space-between;align-items:center;padding-top:10px;margin-top:10px;border-top:1px solid #252b3b;font-size:11px;color:#8b92a8;}
/* Comparatif */
.compare-grid{display:grid;gap:12px;}
.mkt-card{background:#141720;border:1px solid #252b3b;border-radius:8px;padding:14px;}
.mkt-card-header{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:10px;}
.rank-circle{width:26px;height:26px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:600;font-family:'JetBrains Mono',monospace;flex-shrink:0;}
@media print{body{background:#fff;color:#111;padding:16px;}
  .card,.mkt-card{border-color:#ddd;background:#f9f9f9;}
  h3{color:#888;}
}
</style>
"""


# ── Rapport fiche individuelle ───────────────────────────────────────────────

def generate_fiche(market_data: dict, score_result: dict, dim_weights: dict, profile_name: str) -> str:
    """
    Génère une fiche HTML détaillée pour un marché.

    Args:
        market_data: données brutes du marché
        score_result: résultat calculé (total, dims, risk_raw)
        dim_weights: pondérations dimensions actives
        profile_name: nom du profil investisseur
    """
    s = score_result
    c = score_color(s["total"])
    rc = risk_color(s["risk_raw"])
    region_color = REGION_COLORS.get(s["region"], "#888")
    region_label = REGION_LABELS.get(s["region"], s["region"])
    today = date.today().strftime("%d %B %Y")

    # Blocs dimensions
    dims_html = ""
    for d in DIMS:
        dim_id = d["id"]
        v = s["dims"][dim_id]
        dc = score_color(v)
        dw = dim_weights.get(dim_id, 0)
        dims_html += f"""
        <div class="dim-row">
          <div class="dim-label">
            <span><span class="dot" style="background:{d['color']};"></span>{d['label']}
              <span style="color:#3a4258;margin-left:6px;font-size:10px;">({dw}%)</span>
            </span>
            <span class="dim-val mono" style="color:{dc};">{v}</span>
          </div>
          <div class="bar-bg"><div class="bar-fill" style="width:{v}%;background:{d['color']};"></div></div>
        </div>"""

    # Tableau variables brutes
    vars_rows = ""
    for d in DIMS:
        dim_id = d["id"]
        for var in d["vars"]:
            raw_val = market_data[dim_id][var["id"]]
            unit = var.get("unit", "")
            vars_rows += f"""
            <tr>
              <td><span class="dot" style="background:{d['color']};"></span>{d['label']}</td>
              <td>{var['label']}</td>
              <td class="mono" style="color:#e8eaf0;">{raw_val}{(' ' + unit) if unit else ''}</td>
            </tr>"""

    html = f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<title>REIV — Fiche marché : {s['name']}</title>
{CSS}
</head>
<body>

<div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:24px;">
  <div>
    <div style="font-size:10px;color:#555e78;font-family:'JetBrains Mono',monospace;margin-bottom:6px;">
      REIV · SCORING MARCHÉS HÔTELIERS · FICHE INDIVIDUELLE
    </div>
    <h1>{s['name']}</h1>
    <div class="region-header">
      <span class="tag" style="background:{region_color}22;color:{region_color};">{region_label}</span>
      <span style="color:#555e78;margin-left:8px;font-size:11px;">Profil : {profile_name}</span>
    </div>
  </div>
  <div style="text-align:right;">
    <div class="score-big" style="color:{c};">{s['total']}</div>
    <div class="score-label">Score attractivité / 100</div>
  </div>
</div>

<div class="row">
  <div class="col">
    <div class="card">
      <h3>Scores par dimension</h3>
      {dims_html}
      <div class="risk-block">
        <span>Indice risque brut</span>
        <span class="mono" style="font-weight:500;color:{rc};">{s['risk_raw']}/100</span>
      </div>
    </div>
  </div>
  <div class="col">
    <div class="card">
      <h3>Données brutes</h3>
      <table class="vars">
        <thead><tr><th>Dimension</th><th>Variable</th><th>Valeur</th></tr></thead>
        <tbody>{vars_rows}</tbody>
      </table>
    </div>
  </div>
</div>

<div class="footer">
  <span>REIV Hospitality — Scoring marchés hôteliers · Données indicatives</span>
  <span>{today}</span>
</div>

</body>
</html>"""
    return html


# ── Rapport comparatif Top N ─────────────────────────────────────────────────

def generate_comparatif(scores: list, top_n: int, dim_weights: dict, profile_name: str) -> str:
    """
    Génère un rapport comparatif HTML pour les top N marchés.

    Args:
        scores: liste triée de score_results (output de compute_scores)
        top_n: nombre de marchés à inclure
        dim_weights: pondérations dimensions actives
        profile_name: nom du profil investisseur
    """
    top = scores[:top_n]
    today = date.today().strftime("%d %B %Y")

    # Tableau de synthèse
    thead = "<tr><th>#</th><th>Marché</th><th>Région</th><th>Score</th>"
    for d in DIMS:
        thead += f"<th>{d['label'][:18]}</th>"
    thead += "<th>Risque</th></tr>"

    tbody = ""
    for i, s in enumerate(top):
        c = score_color(s["total"])
        rc = risk_color(s["risk_raw"])
        region_color = REGION_COLORS.get(s["region"], "#888")
        region_label = REGION_LABELS.get(s["region"], s["region"])
        tbody += f"<tr><td class='mono' style='color:#555e78;'>{i+1}</td>"
        tbody += f"<td style='font-weight:500;'>{s['name']}</td>"
        tbody += f"<td><span class='tag' style='background:{region_color}22;color:{region_color};'>{region_label}</span></td>"
        tbody += f"<td class='mono' style='color:{c};font-weight:600;'>{s['total']}</td>"
        for d in DIMS:
            dv = s["dims"][d["id"]]
            dc = score_color(dv)
            tbody += f"<td class='mono' style='color:{dc};'>{dv}</td>"
        tbody += f"<td class='mono' style='color:{rc};'>{s['risk_raw']}</td>"
        tbody += "</tr>"

    # Fiches compactes
    cards_html = ""
    for i, s in enumerate(top):
        c = score_color(s["total"])
        rc = risk_color(s["risk_raw"])
        region_color = REGION_COLORS.get(s["region"], "#888")
        region_label = REGION_LABELS.get(s["region"], s["region"])

        dim_bars = ""
        for d in DIMS:
            v = s["dims"][d["id"]]
            dim_bars += f"""
            <div style="margin-bottom:7px;">
              <div style="display:flex;justify-content:space-between;font-size:10px;color:#8b92a8;margin-bottom:2px;">
                <span><span class="dot" style="background:{d['color']};"></span>{d['label']}</span>
                <span class="mono" style="color:{score_color(v)};">{v}</span>
              </div>
              <div class="bar-bg"><div class="bar-fill" style="width:{v}%;background:{d['color']};"></div></div>
            </div>"""

        cards_html += f"""
        <div class="mkt-card">
          <div class="mkt-card-header">
            <div style="display:flex;align-items:center;gap:10px;">
              <div class="rank-circle" style="background:{c}22;color:{c};">{i+1}</div>
              <div>
                <div style="font-size:14px;font-weight:600;">{s['name']}</div>
                <span class="tag" style="background:{region_color}22;color:{region_color};margin-top:2px;">{region_label}</span>
              </div>
            </div>
            <div style="text-align:right;">
              <div class="mono" style="font-size:24px;font-weight:600;color:{c};">{s['total']}</div>
              <div style="font-size:9px;color:#555e78;">/ 100</div>
            </div>
          </div>
          {dim_bars}
          <div class="risk-block">
            <span>Risque brut</span>
            <span class="mono" style="color:{rc};">{s['risk_raw']}/100</span>
          </div>
        </div>"""

    html = f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<title>REIV — Rapport comparatif Top {top_n}</title>
{CSS}
<style>
.compare-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:12px;}}
table.synth{{width:100%;border-collapse:collapse;font-size:11px;margin-bottom:24px;}}
table.synth th{{background:#1c2130;color:#555e78;padding:6px 8px;text-align:left;font-weight:500;border-bottom:1px solid #252b3b;white-space:nowrap;}}
table.synth td{{padding:6px 8px;border-bottom:1px solid #1c2130;}}
table.synth tr:hover td{{background:#1c2130;}}
</style>
</head>
<body>

<div style="margin-bottom:24px;">
  <div style="font-size:10px;color:#555e78;font-family:'JetBrains Mono',monospace;margin-bottom:6px;">
    REIV · SCORING MARCHÉS HÔTELIERS · RAPPORT COMPARATIF
  </div>
  <h1>Top {top_n} marchés — {profile_name}</h1>
  <p style="color:#8b92a8;font-size:12px;margin-top:4px;">
    {top_n} marchés sélectionnés · Pondérations : 
    {' — '.join([f"{d['label'][:14]} {dim_weights.get(d['id'],0)}%" for d in DIMS])}
  </p>
</div>

<div class="card">
  <h3>Tableau de synthèse</h3>
  <div style="overflow-x:auto;">
    <table class="synth">
      <thead>{thead}</thead>
      <tbody>{tbody}</tbody>
    </table>
  </div>
</div>

<h2 style="margin-bottom:12px;">Fiches détaillées</h2>
<div class="compare-grid">{cards_html}</div>

<div class="footer">
  <span>REIV Hospitality — Scoring marchés hôteliers · Données indicatives</span>
  <span>{today}</span>
</div>

</body>
</html>"""
    return html
