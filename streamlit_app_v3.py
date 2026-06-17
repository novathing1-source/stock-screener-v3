
import json
from datetime import datetime
import streamlit as st
from analyze_stock_v3 import analyze_stock, format_result_markdown

st.set_page_config(page_title="Stock Screen Pro", page_icon="📈", layout="centered", initial_sidebar_state="collapsed")

st.markdown(
    """
    <style>
    .block-container {max-width: 920px; padding-top: 1rem; padding-bottom: 2rem;}
    [data-testid="stTextInput"] input {font-size: 1.1rem !important; padding: 0.92rem 1rem !important;}
    .stButton > button, [data-testid="stFormSubmitButton"] button {width: 100%; min-height: 3.1rem; border-radius: 14px; font-size: 1.02rem;}
    .hero {padding: 1rem 1.1rem; border-radius: 18px; border: 1px solid #D6E2F0; background: linear-gradient(180deg, #F7FAFF 0%, #F4F7FB 100%); margin: 0.5rem 0 1rem 0;}
    .badge-pass, .badge-stop, .badge-soft {display: inline-block; padding: 0.22rem 0.55rem; border-radius: 999px; font-size: 0.82rem; margin-right: 0.35rem; margin-bottom: 0.25rem;}
    .badge-pass { background:#E7F8EE; border:1px solid #B7E3C6; color:#155724; }
    .badge-stop { background:#FDECEC; border:1px solid #F1B6B6; color:#7F1D1D; }
    .badge-soft { background:#EEF3F8; border:1px solid #D7E2EE; color:#344054; }
    .section-note { color:#5B6575; font-size:0.94rem; }
    .footnote { color:#667085; font-size:0.92rem; }
    .small-card {padding: 0.85rem 1rem; border: 1px solid #E4EAF2; border-radius: 16px; background:#FFFFFF;}
    </style>
    """,
    unsafe_allow_html=True,
)

if "recent_queries_v3" not in st.session_state:
    st.session_state.recent_queries_v3 = []

@st.cache_data(show_spinner=False, ttl=900)
def cached_analyze_stock(company_name: str):
    return analyze_stock(company_name)

def add_recent(name: str):
    cleaned = name.strip()
    if not cleaned:
        return
    existing = st.session_state.recent_queries_v3
    updated = [cleaned] + [q for q in existing if q.lower() != cleaned.lower()]
    st.session_state.recent_queries_v3 = updated[:6]

def verdict_badge(decision: str) -> str:
    decision_lower = (decision or "").lower()
    if "passes screen" in decision_lower:
        return '<span class="badge-pass">PASS</span>'
    if any(x in decision_lower for x in ["stop", "overvalued", "issues", "weak", "low profit", "not meaningful"]):
        return '<span class="badge-stop">STOP</span>'
    return '<span class="badge-soft">INCOMPLETE</span>'

st.title("📈 Stock Screen Pro")
st.write("A stricter, cleaner stock screener you can comfortably use from an iPad or browser.")
st.caption("Enter only a public company name. The app will try to find the ticker and apply the screen automatically.")

with st.sidebar:
    st.header("How this app works")
    st.write("It checks revenue growth, P/E, PEG, ROE, and quick ratio in order. If one step fails, the screen stops there.")
    st.write("This is a screening tool only, not financial advice.")
    st.header("Recent searches")
    if st.session_state.recent_queries_v3:
        for q in st.session_state.recent_queries_v3:
            if st.button(f"Use: {q}", key=f"recent_{q}"):
                st.session_state.company_name_v3 = q
                st.rerun()
    else:
        st.caption("No recent searches yet.")
    st.header("Good demo inputs")
    st.caption("Tap one of these to fill the search box quickly.")
    demo_cols = st.columns(2)
    demos = ["Apple", "Microsoft", "Nvidia", "Costco"]
    for idx, demo in enumerate(demos):
        if demo_cols[idx % 2].button(demo, key=f"demo_{demo}"):
            st.session_state.company_name_v3 = demo
            st.rerun()

with st.form("analyze_stock_form_v3", clear_on_submit=False):
    company_name = st.text_input("Company name", key="company_name_v3", placeholder="Examples: Apple, Microsoft, Costco, Coca-Cola", help="Type one public company name. The app will try to resolve it to a stock ticker automatically.")
    c1, c2 = st.columns([2, 1])
    analyze_clicked = c1.form_submit_button("Analyze company")
    clear_clicked = c2.form_submit_button("Clear")

if clear_clicked:
    st.session_state.company_name_v3 = ""
    st.rerun()

if not analyze_clicked:
    st.markdown('<div class="small-card"><strong>What makes this version more polished?</strong><br>Cleaner decision card, better organization, a more critical failure explanation, recent searches, downloads, and a faster cached analysis path for repeated checks.</div>', unsafe_allow_html=True)
    st.stop()

if not company_name or not company_name.strip():
    st.warning("Please enter a company name before analyzing.")
    st.stop()

query = company_name.strip()
add_recent(query)
with st.spinner("Running the stock screen..."):
    output = cached_analyze_stock(query)

result = output["result"]
summary_md = format_result_markdown(output)
now_label = datetime.now().strftime("%Y-%m-%d %H:%M")

hero_html = f"""
<div class="hero">
  <div>{verdict_badge(result['final_decision'])}<span class="badge-soft">Ticker: {result['ticker'] or 'Unavailable'}</span><span class="badge-soft">Source: {result['provider_name']}</span></div>
  <h3 style="margin:0.35rem 0 0.25rem 0;">{result['company_name']}</h3>
  <div style="font-size:1.08rem; font-weight:600; margin-bottom:0.45rem;">{result['final_decision']}</div>
  <div>{result['explanation']}</div>
  <div class="section-note" style="margin-top:0.55rem;">Last app run: {now_label}</div>
</div>
"""
st.markdown(hero_html, unsafe_allow_html=True)
st.caption("Passing the screen does not automatically mean the stock is a good investment.")

m1, m2, m3, m4 = st.columns(4)
m1.metric("P/E", "N/A" if result["pe_ratio"] is None else result["pe_ratio"])
m2.metric("PEG", "N/A" if result["peg_ratio"] is None else result["peg_ratio"])
m3.metric("Avg ROE", "N/A" if result["average_roe"] is None else f"{result['average_roe']}%")
m4.metric("Quick ratio", "N/A" if result["quick_ratio"] is None else result["quick_ratio"])

overview_tab, checks_tab, detail_tab, warnings_tab, about_tab = st.tabs(["Overview", "Checks", "Details", "Warnings", "About"], on_change="rerun", key="main_tabs_v3")

with overview_tab:
    st.subheader("Beginner summary")
    st.write("This tab gives the simplest interpretation of the result.")
    bullets = [f"**Company:** {result['company_name']}", f"**Ticker:** {result['ticker'] or 'Unavailable'}", f"**Decision:** {result['final_decision']}"]
    if result.get("screen_step_failed"):
        bullets.append(f"**Stopped at:** {result['screen_step_failed']}")
    for b in bullets:
        st.markdown(f"- {b}")
    st.markdown(f"<div class='footnote'>{result['data_source_note']}</div>", unsafe_allow_html=True)

with checks_tab:
    st.subheader("Screening checklist")
    for item in result.get("checks_detail", []):
        passed = item.get("passed")
        label = item.get("label")
        if passed is True:
            st.success(f"Step {item['step']}: {label} — Passed")
        elif passed is False:
            st.error(f"Step {item['step']}: {label} — Failed")
        else:
            st.info(f"Step {item['step']}: {label} — Not reached")

with detail_tab:
    st.subheader("Financial detail")
    d1, d2 = st.columns(2)
    with d1:
        st.markdown("**Revenue growth by year**")
        st.json(result["revenue_growth_by_year"])
    with d2:
        st.markdown("**ROE by year**")
        st.json(result["roe_by_year"])
    with st.expander("Full technical result", expanded=False, icon=":material/code:"):
        st.text(output["summary"])
        st.json(result)

with warnings_tab:
    st.subheader("Warnings and missing data")
    if result["missing_data_warnings"]:
        for warning in result["missing_data_warnings"]:
            st.warning(warning)
    else:
        st.success("No missing-data warnings were returned for this run.")

with about_tab:
    st.subheader("About this screen")
    st.write(result["disclaimer"])
    st.write(result["data_source_note"])
    st.markdown("**Strict logic used:**")
    st.markdown("1. Revenue growth first")
    st.markdown("2. Then P/E")
    st.markdown("3. Then PEG")
    st.markdown("4. Then average ROE")
    st.markdown("5. Then quick ratio")

st.subheader("Download output")
dl1, dl2 = st.columns(2)
dl1.download_button("Download JSON", data=json.dumps(result, indent=2), file_name=f"stock_screen_{(result['ticker'] or 'result').lower()}.json", mime="application/json")
dl2.download_button("Download Markdown summary", data=summary_md, file_name=f"stock_screen_{(result['ticker'] or 'result').lower()}.md", mime="text/markdown")

st.markdown("---")
st.markdown("<div class='footnote'>Designed for touch-friendly use, clarity, and cleaner stakeholder demos.</div>", unsafe_allow_html=True)
