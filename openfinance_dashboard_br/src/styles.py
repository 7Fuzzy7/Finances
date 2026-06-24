APP_CSS = """
<style>
:root {
  --bg: #070B14;
  --panel: rgba(255,255,255,.066);
  --panel-2: rgba(255,255,255,.105);
  --border: rgba(255,255,255,.13);
  --text: #EEF3FF;
  --muted: #A6B0C3;
  --accent: #7C3AED;
  --accent-2: #06B6D4;
  --good: #22C55E;
  --warn: #F59E0B;
  --bad: #EF4444;
}

.stApp {
  background:
    radial-gradient(circle at top left, rgba(124,58,237,.34), transparent 30%),
    radial-gradient(circle at top right, rgba(6,182,212,.20), transparent 35%),
    linear-gradient(135deg, #070B14 0%, #101728 55%, #070B14 100%);
  color: var(--text);
}

.block-container {
  padding-top: 2rem;
  padding-bottom: 3rem;
  max-width: 1320px;
}

.hero {
  border: 1px solid var(--border);
  background: linear-gradient(135deg, rgba(124,58,237,.23), rgba(6,182,212,.11));
  border-radius: 28px;
  padding: 28px;
  margin-bottom: 18px;
  box-shadow: 0 20px 70px rgba(0,0,0,.35);
}
.hero-badge {
  display: inline-block;
  border: 1px solid rgba(255,255,255,.16);
  background: rgba(255,255,255,.08);
  color: #dbeafe;
  border-radius: 999px;
  padding: 6px 11px;
  font-size: .78rem;
  font-weight: 800;
  margin-bottom: 12px;
}
.hero h1 {
  font-size: 2.45rem;
  line-height: 1.05;
  margin-bottom: 8px;
  letter-spacing: -0.045em;
}
.hero p { color: var(--muted); font-size: 1.06rem; margin: 0; }

.quality-strip {
  border: 1px solid rgba(6,182,212,.35);
  background: rgba(6,182,212,.10);
  border-radius: 18px;
  padding: 14px 16px;
  margin: 2px 0 16px;
  color: #e0f2fe;
}

.metric-card {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 22px;
  padding: 18px;
  min-height: 132px;
  box-shadow: 0 12px 34px rgba(0,0,0,.24);
}
.metric-card.positive { border-color: rgba(34,197,94,.36); background: rgba(34,197,94,.10); }
.metric-card.negative { border-color: rgba(239,68,68,.38); background: rgba(239,68,68,.10); }
.metric-label { color: var(--muted); font-size: .88rem; margin-bottom: 8px; }
.metric-value { color: var(--text); font-size: 1.55rem; font-weight: 850; letter-spacing: -0.035em; }
.metric-help { color: var(--muted); font-size: .82rem; margin-top: 8px; }

.insight-card {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 20px;
  padding: 18px;
  margin-bottom: 12px;
}
.insight-title { font-size: 1.04rem; font-weight: 850; color: var(--text); margin-bottom: 7px; }
.impact {
  display: inline-block;
  border-radius: 999px;
  padding: 4px 10px;
  font-size: .75rem;
  font-weight: 800;
  background: rgba(124,58,237,.18);
  border: 1px solid rgba(124,58,237,.35);
  margin-bottom: 8px;
}
.insight-text { color: var(--muted); font-size: .94rem; }

.section-title { font-size: 1.25rem; font-weight: 850; margin: 12px 0 10px; }
.stTabs [data-baseweb="tab-list"] { gap: 8px; flex-wrap: wrap; }
.stTabs [data-baseweb="tab"] {
  background: rgba(255,255,255,.07);
  border-radius: 999px;
  padding: 10px 16px;
  color: #dbeafe;
}
.stTabs [aria-selected="true"] { background: rgba(124,58,237,.38) !important; }

[data-testid="stSidebar"] {
  background: rgba(7, 11, 20, .94);
  border-right: 1px solid var(--border);
}

.stDataFrame, .stPlotlyChart {
  border-radius: 18px;
  overflow: hidden;
}

.small-muted { color: var(--muted); font-size: .90rem; }
</style>
"""
