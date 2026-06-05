import streamlit as st


def inject_theme():
    st.markdown(_CSS, unsafe_allow_html=True)


_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,500;9..144,600;9..144,700&family=Archivo:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap');

:root{
  --navy:#1B3A6F; --navy-deep:#0F2344; --navy-abyss:#081629;
  --cyan:#6FAED9; --cyan-bright:#8FCDF5; --cyan-glow:rgba(111,174,217,.30);
  --paper:#0C1626; --surface:#13203A; --surface-2:#1A2B49; --surface-3:#22335A;
  --ink:#EAF1FA; --ink-soft:#A9BBD4; --ink-mute:#6B7E9E;
  --line:#243453; --line-bright:#33486F;
  --good:#3DD8A4; --good-bg:rgba(61,216,164,.12);
  --warn:#F5B544; --warn-bg:rgba(245,181,68,.12);
  --bad:#F2615A;  --bad-bg:rgba(242,97,90,.12);
  /* Aliases so both naming conventions used across the app resolve correctly */
  --success:#3DD8A4; --danger:#F2615A; --warning:#F5B544;
  --text-secondary:#A9BBD4; --text-muted:#6B7E9E; --accent:#6FAED9;
  --radius:16px; --radius-lg:20px;
  --shadow:0 8px 28px rgba(8,22,41,.45);
  --font-display:'Fraunces',Georgia,serif;
  --font-body:'Archivo',-apple-system,sans-serif;
  --font-mono:'JetBrains Mono',monospace;
}

/* ── App background : profondeur + atmosphère ── */
[data-testid="stAppViewContainer"]{
  background:var(--paper);
  background-image:
    radial-gradient(1100px 550px at 8% -5%, rgba(111,174,217,.10), transparent 55%),
    radial-gradient(800px 450px at 100% 0%, rgba(27,58,111,.32), transparent 50%);
  background-attachment:fixed;
}
[data-testid="stHeader"]{background:transparent}
.main .block-container{padding-top:2.5rem;max-width:1100px}

html,body,[data-testid="stAppViewContainer"],[class*="css"]{
  font-family:var(--font-body);color:var(--ink);
  -webkit-font-smoothing:antialiased;
}

/* subtle grain overlay */
[data-testid="stAppViewContainer"]::before{
  content:"";position:fixed;inset:0;pointer-events:none;z-index:0;opacity:.022;
  background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='120' height='120'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.9' numOctaves='3'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E");
}

/* ── Hide Streamlit chrome ── */
#MainMenu,footer,[data-testid="stToolbar"]{visibility:hidden}

/* ── Typography ── */
h1,h2,h3{font-family:var(--font-display);letter-spacing:-.02em;color:var(--ink)}

/* ── PAGE HEADER ── */
.page-header{
  position:relative;padding:8px 0 28px;margin-bottom:28px;
  border-bottom:1px solid var(--line);
  animation:rise .6s cubic-bezier(.2,.8,.2,1);
}
.page-header::before{
  content:"";position:absolute;left:0;top:14px;width:40px;height:3px;
  background:linear-gradient(90deg,var(--cyan),transparent);border-radius:2px;
}
.page-header h1{
  font-family:var(--font-display);font-weight:600;
  font-size:clamp(30px,4vw,44px);line-height:1.05;margin:18px 0 8px;
}
.page-header p{color:var(--ink-soft);font-size:16px;max-width:620px;margin:0}

/* ── SECTION HEADER ── */
.section-header{
  font-family:var(--font-mono);font-size:12px;letter-spacing:.2em;
  text-transform:uppercase;color:var(--ink-mute);
  margin:36px 0 18px;display:flex;align-items:center;gap:14px;
}
.section-header::after{content:"";flex:1;height:1px;background:var(--line)}

/* ── STAT CARD (métriques) ── */
.stat-card{
  background:var(--surface);border:1px solid var(--line);
  border-radius:var(--radius);padding:24px 22px;position:relative;overflow:hidden;
  transition:transform .25s cubic-bezier(.2,.8,.2,1),border-color .25s;
  animation:rise .6s cubic-bezier(.2,.8,.2,1) backwards;
}
.stat-card::after{
  content:"";position:absolute;bottom:0;left:0;right:0;height:3px;
  background:linear-gradient(90deg,var(--cyan),transparent);opacity:.7;
}
.stat-card:hover{transform:translateY(-4px);border-color:var(--line-bright)}
.stat-label{
  font-family:var(--font-mono);font-size:11px;letter-spacing:.12em;
  text-transform:uppercase;color:var(--ink-mute);margin-bottom:12px;
}
.stat-value{
  font-family:var(--font-display);font-size:40px;font-weight:600;
  line-height:1;letter-spacing:-.02em;color:var(--ink);
}
.stat-desc{font-size:13px;color:var(--ink-soft);margin-top:8px}

/* ── INFO CARD ── */
.info-card{
  background:var(--surface);border:1px solid var(--line);
  border-radius:var(--radius);padding:24px 26px;
  transition:transform .25s cubic-bezier(.2,.8,.2,1),border-color .25s;
  animation:rise .6s cubic-bezier(.2,.8,.2,1) backwards;
}
.info-card:hover{transform:translateY(-3px);border-color:var(--line-bright)}
.info-card h3,.info-card h4{font-family:var(--font-display);color:var(--ink);margin-bottom:10px}
.info-card p{color:var(--ink-soft)}

/* ── BRAND TAGLINE (sidebar) ── */
.brand-tagline{
  font-family:var(--font-mono);font-size:11px;letter-spacing:.18em;
  text-transform:uppercase;color:var(--cyan);margin:6px 0 18px;
}

/* ── LOGO (sidebar) ── */
/* The sidebar has a dark navy background; the logo image is given a light
   rounded plate so a dark-on-transparent logo stays legible, and a hard
   max-width so a large source PNG never overflows the 300px sidebar. */
.sidebar-logo{
  display:flex;align-items:center;justify-content:center;
  padding:14px 16px;margin:4px 0 2px;
  background:#FFFFFF;border-radius:12px;
  box-shadow:0 2px 10px rgba(0,0,0,.18);
}
.sidebar-logo img,
.sidebar-logo svg{
  max-width:100%;max-height:64px;height:auto;width:auto;display:block;
}

/* ── LOGO (home hero) ── */
.hero-logo{
  display:flex;align-items:center;gap:20px;
  margin:4px 0 22px;padding:18px 22px;
  background:linear-gradient(135deg,var(--navy),var(--navy-deep));
  border-radius:16px;border:1px solid var(--line);
}
.hero-logo img,
.hero-logo svg{
  max-height:72px;height:auto;width:auto;flex-shrink:0;
  background:#FFFFFF;border-radius:10px;padding:8px 10px;display:none;
}
.hero-logo .brand-text h1{
  margin:0;font-size:1.5rem;line-height:1.2;color:#FFFFFF;font-weight:700;
}
.hero-logo .brand-text p{
  margin:4px 0 0;font-size:.95rem;color:var(--cyan);
}

/* ── SIDEBAR ── */
[data-testid="stSidebar"]{
  background:linear-gradient(180deg,var(--navy-deep),var(--navy-abyss));
  border-right:1px solid var(--line);
}
[data-testid="stSidebar"] *{color:var(--ink-soft)}
[data-testid="stSidebar"] h1,[data-testid="stSidebar"] h2,[data-testid="stSidebar"] h3{color:var(--ink)}

/* Navigation radio → onglets verticaux élégants */
[data-testid="stSidebar"] [role="radiogroup"] label{
  padding:10px 14px;border-radius:10px;margin-bottom:4px;
  transition:background .2s,color .2s;font-weight:500;
  border:1px solid transparent;
}
[data-testid="stSidebar"] [role="radiogroup"] label:hover{
  background:rgba(111,174,217,.08);color:var(--ink);
}

/* ── BUTTONS ── */
.stButton>button,.stDownloadButton>button{
  font-family:var(--font-body);font-weight:600;border-radius:11px;
  border:1px solid var(--line-bright);background:var(--surface-2);color:var(--ink);
  padding:10px 20px;transition:all .22s cubic-bezier(.2,.8,.2,1);
}
.stButton>button:hover,.stDownloadButton>button:hover{
  transform:translateY(-2px);border-color:var(--cyan);
  box-shadow:0 6px 20px var(--cyan-glow);
}
/* Primary button */
.stButton>button[kind="primary"]{
  background:linear-gradient(135deg,var(--cyan),var(--navy));
  border:none;color:#06121F;
}
.stButton>button[kind="primary"]:hover{box-shadow:0 8px 26px var(--cyan-glow)}

/* ── INPUTS ── */
.stTextInput input,.stNumberInput input,.stSelectbox div[data-baseweb="select"]>div,
.stMultiSelect div[data-baseweb="select"]>div{
  background:var(--surface)!important;border:1px solid var(--line)!important;
  border-radius:10px!important;color:var(--ink)!important;
}
.stTextInput input:focus,.stNumberInput input:focus{
  border-color:var(--cyan)!important;box-shadow:0 0 0 3px var(--cyan-glow)!important;
}

/* ── METRICS natives (st.metric) ── */
[data-testid="stMetric"]{
  background:var(--surface);border:1px solid var(--line);
  border-radius:var(--radius);padding:18px 20px;
}
[data-testid="stMetricValue"]{font-family:var(--font-display);color:var(--ink)}
[data-testid="stMetricLabel"]{font-family:var(--font-mono);font-size:11px;
  letter-spacing:.1em;text-transform:uppercase;color:var(--ink-mute)}

/* ── TABLES / DATAFRAMES ── */
[data-testid="stDataFrame"],[data-testid="stTable"]{
  border:1px solid var(--line);border-radius:var(--radius);overflow:hidden;
}
.stDataFrame [role="columnheader"]{
  background:var(--surface-2)!important;font-family:var(--font-mono)!important;
  font-size:11px!important;letter-spacing:.08em!important;text-transform:uppercase!important;
  color:var(--ink-soft)!important;
}

/* ── TABS ── */
.stTabs [data-baseweb="tab-list"]{gap:6px;border-bottom:1px solid var(--line)}
.stTabs [data-baseweb="tab"]{
  font-family:var(--font-mono);font-size:13px;letter-spacing:.05em;
  color:var(--ink-mute);background:transparent;border-radius:9px 9px 0 0;padding:8px 16px;
}
.stTabs [aria-selected="true"]{color:var(--cyan)!important;border-bottom:2px solid var(--cyan)!important}

/* ── EXPANDER ── */
.streamlit-expanderHeader,[data-testid="stExpander"] summary{
  background:var(--surface)!important;border:1px solid var(--line)!important;
  border-radius:11px!important;font-family:var(--font-body)!important;color:var(--ink)!important;
}

/* ── ALERTS (success/warning/error) recolorés ── */
.stAlert{border-radius:12px;border:1px solid var(--line)}

/* ── PROGRESS BAR ── */
.stProgress>div>div>div{background:linear-gradient(90deg,var(--cyan),var(--navy))!important}

/* ── Badges utilitaires (à utiliser dans tes st.markdown) ── */
.badge{font-family:var(--font-mono);font-size:11px;letter-spacing:.08em;
  text-transform:uppercase;padding:5px 12px;border-radius:7px;display:inline-block}
.badge-good{background:var(--good-bg);color:var(--good);border:1px solid rgba(61,216,164,.3)}
.badge-warn{background:var(--warn-bg);color:var(--warn);border:1px solid rgba(245,181,68,.3)}
.badge-bad{background:var(--bad-bg);color:var(--bad);border:1px solid rgba(242,97,90,.3)}

/* ── Entrance animation ── */
@keyframes rise{from{opacity:0;transform:translateY(16px)}to{opacity:1;transform:translateY(0)}}

/* Stagger des stat-cards en ligne */
[data-testid="column"]:nth-child(1) .stat-card{animation-delay:.05s}
[data-testid="column"]:nth-child(2) .stat-card{animation-delay:.12s}
[data-testid="column"]:nth-child(3) .stat-card{animation-delay:.19s}
[data-testid="column"]:nth-child(4) .stat-card{animation-delay:.26s}
/* ── WIZARD STEPPER (barre d'étapes horizontale) ── */
.wizard-stepper{
  display:flex;align-items:center;justify-content:space-between;gap:0;margin:8px 0 32px;
  padding:18px 24px;background:var(--surface);border:1px solid var(--line);
  border-radius:var(--radius);
}
.wizard-step{display:flex;flex-direction:column;align-items:center;gap:8px;flex:0 0 auto;text-align:center}
.wizard-step-num{
  width:38px;height:38px;border-radius:50%;display:flex;align-items:center;justify-content:center;
  font-family:var(--font-mono);font-size:14px;font-weight:600;
  background:var(--surface-2);border:1px solid var(--line-bright);color:var(--ink-mute);
  transition:all .3s cubic-bezier(.2,.8,.2,1);
}
.wizard-step-label{
  font-family:var(--font-mono);font-size:11px;letter-spacing:.06em;text-transform:uppercase;
  color:var(--ink-mute);transition:color .3s;max-width:92px;line-height:1.3;
}
.wizard-step.is-active .wizard-step-num{
  background:linear-gradient(135deg,var(--cyan),var(--navy));border:1px solid var(--cyan);color:#06121F;
  box-shadow:0 0 0 4px var(--cyan-glow),0 6px 18px var(--cyan-glow);transform:scale(1.08);
}
.wizard-step.is-active .wizard-step-label{color:var(--cyan);font-weight:600}
.wizard-step.is-complete .wizard-step-num{
  background:var(--good-bg);border-color:rgba(61,216,164,.45);color:var(--good);
}
.wizard-step.is-complete .wizard-step-label{color:var(--ink-soft)}
.wizard-connector{
  flex:1 1 auto;height:2px;min-width:20px;margin:0 6px;margin-bottom:26px;
  background:var(--line-bright);border-radius:2px;transition:background .3s;
}
.wizard-connector.is-complete{
  background:linear-gradient(90deg,var(--good),var(--cyan));box-shadow:0 0 8px rgba(61,216,164,.25);
}
.wizard-nav{margin:8px 0}

/* ── CHECKPOINT SUMMARY (success / result box) ── */
.checkpoint-summary{
  background:var(--good-bg);
  border:1px solid rgba(61,216,164,.40);
  border-left:4px solid var(--good);
  border-radius:var(--radius);
  padding:16px 20px;margin:10px 0 14px;
}
.checkpoint-summary-title{
  font-family:var(--font-body);font-weight:700;font-size:16px;color:var(--good);
  display:flex;align-items:center;gap:8px;
}
.checkpoint-list{
  display:flex;flex-wrap:wrap;gap:8px;margin-top:12px;
}

/* ── HELP TIP (contextual info box) ── */
.help-tip{
  background:var(--surface-2);
  border:1px solid var(--line);
  border-left:3px solid var(--cyan);
  border-radius:12px;
  padding:12px 16px;margin:8px 0;
  color:var(--ink-soft);font-size:14px;line-height:1.55;
}
.help-tip-icon{
  display:inline-flex;align-items:center;justify-content:center;
  width:18px;height:18px;margin-right:8px;border-radius:50%;
  background:var(--cyan);color:var(--navy-abyss);font-weight:700;font-size:12px;
}

/* ── VALIDATION BADGE ── */
.validation-badge{
  display:inline-flex;align-items:center;gap:6px;
  font-family:var(--font-mono);font-size:12px;font-weight:500;
  padding:5px 11px;border-radius:999px;border:1px solid var(--line-bright);
  background:var(--surface);color:var(--ink-soft);
}
.validation-badge.is-valid{
  background:var(--good-bg);border-color:rgba(61,216,164,.40);color:var(--good);
}
.validation-badge.is-warning{
  background:var(--warn-bg);border-color:rgba(245,181,68,.40);color:var(--warn);
}
.validation-badge.is-error{
  background:var(--bad-bg);border-color:rgba(242,97,90,.40);color:var(--bad);
}
.validation-badge.is-info{
  background:var(--surface-2);border-color:var(--line-bright);color:var(--cyan);
}

</style>"""
