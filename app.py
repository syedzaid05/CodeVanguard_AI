import ast

import pandas as pd
import streamlit as st

from core import repo_input, repo_processing
from core.ai_engine import AIEngine
from core.repair_agent import (
    RepairAttempt,
    apply_patch,
    extract_unified_diff,
    generate_repair,
)
from core.report import download_button_markdown, findings_to_rows
from core.static_analysis import (
    check_vulnerabilities,
    run_static_analysis,
    sorted_findings,
)
from core.validation import validate_patch

st.set_page_config(
    page_title="CodeGuardAI — AI Code Repair Agent",
    page_icon="🛠️",
    layout="wide",
    initial_sidebar_state="expanded",
)

BRAND_CSS = """
<style>
    :root {
        --accent: #4f46e5;
        --success: #059669;
        --warning: #d97706;
        --danger: #dc2626;
    }
    .block-container { padding-top: 1.6rem; max-width: 1500px; }
    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #101426 0%, #1b1f3a 100%);
    }
    section[data-testid="stSidebar"] * { color: #e5e7eb !important; }
    section[data-testid="stSidebar"] hr { border-color: rgba(255,255,255,.12); }
    div[data-testid="stButton"] > button { border-radius: 8px; font-weight: 600; }
    div[data-testid="stButton"] > button[kind="primary"] {
        background: linear-gradient(90deg, #4f46e5, #6366f1);
        border: none;
        box-shadow: 0 4px 14px rgba(79, 70, 229, .3);
    }
    div[data-testid="stMetric"] {
        background: #f8f9fc;
        border: 1px solid #e5e7eb;
        border-radius: 10px;
        padding: 14px 16px;
    }
    .hero {
        background: linear-gradient(120deg, #101426 0%, #1b1f3a 60%, #312e81 100%);
        border-radius: 14px;
        padding: 26px 30px;
        margin-bottom: 18px;
        color: #fff;
    }
    .hero h1 { color: #fff; margin: 0; font-size: 1.7rem; }
    .hero p { color: #c7d2fe; margin: 6px 0 0 0; font-size: .95rem; }
    .hero .brand-badge {
        display: inline-block;
        background: rgba(99, 102, 241, .25);
        border: 1px solid rgba(129, 140, 248, .5);
        color: #c7d2fe;
        font-size: .72rem;
        font-weight: 700;
        letter-spacing: .08em;
        text-transform: uppercase;
        padding: 3px 10px;
        border-radius: 999px;
        margin-bottom: 10px;
    }
    .step-legend {
        display: flex; gap: 6px; flex-wrap: wrap; margin: 10px 0 18px 0;
    }
    .step-legend span {
        background: #eef2ff; color: #3730a3; border: 1px solid #c7d2fe;
        border-radius: 999px; padding: 3px 12px; font-size: .8rem; font-weight: 600;
    }
    .dep-chip {
        background: #f4f5f7; color: #374151; border: 1px solid #d1d5db;
        border-radius: 6px; padding: 4px 10px; font-size: .8rem;
        font-family: ui-monospace, monospace;
    }
    footer { visibility: hidden; }
    #MainMenu { visibility: hidden; }
</style>
"""


def _render_hero() -> None:
    st.markdown(
        """
        <div class="hero">
          <span class="brand-badge">Static analysis · AI repair · Automated validation</span>
          <h1>🛠️ CodeGuardAI — AI Code Repair &amp; Analysis Agent</h1>
          <p>Load a repository → scan → explain → patch → validate → export a production-ready report.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_step_legend() -> None:
    st.markdown(
        '<div class="step-legend"><span>1 · Input</span><span>2 · Findings</span>'
        '<span>3 · AI intelligence</span><span>4 · Repair</span>'
        '<span>5 · Validation</span><span>6 · Export</span></div>',
        unsafe_allow_html=True,
    )


_RENDERED_CSS = {"done": False}


def _ensure_css() -> None:
    if not _RENDERED_CSS["done"]:
        st.markdown(BRAND_CSS, unsafe_allow_html=True)
        _RENDERED_CSS["done"] = True


_SEVERITY_COLORS = {
    "critical": ("#dc2626", "#fee2e2"),
    "high": ("#b91c1c", "#fee2e2"),
    "medium": ("#b45309", "#fef3c7"),
    "low": ("#0369a1", "#e0f2fe"),
    "info": ("#4b5563", "#f3f4f6"),
}


def _sev_styles(df: pd.DataFrame, col: str):
    def _paint(val):
        f, b = _SEVERITY_COLORS.get(str(val).lower(), ("#4b5563", "#f3f4f6"))
        return f"background-color:{b};color:{f};font-weight:700;"

    return (
        df.style.map(_paint, subset=pd.IndexSlice[:, [col]])
        .set_properties(**{"font-size": "0.88rem"})
        .hide(axis="index")
    )


ai = AIEngine()
_ensure_css()
_render_hero()
_render_step_legend()

with st.sidebar:
    st.markdown(
        """
        <div style='text-align:center; padding: 6px 0 2px 0;'>
          <div style='font-size: 2.2rem;'>🛠️</div>
          <div style='font-size: 1.15rem; font-weight: 800; letter-spacing: .02em;'>CodeGuardAI</div>
          <div style='font-size: .74rem; opacity: .75; letter-spacing: .12em; text-transform: uppercase;'>
            AI Code Repair Agent
          </div>
        </div>
        <hr>
        """,
        unsafe_allow_html=True,
    )
    _list = []
    if st.session_state.get("repo"):
        _list.append(("✅", "Repository loaded"))
    if st.session_state.get("_analyzed") and st.session_state.get("analysis"):
        _list.append(("✅", f"Analysis · {len(st.session_state.analysis['findings'])} findings"))
    if st.session_state.get("ai_explanations"):
        _list.append(("✅", "AI explanations ready"))
    if st.session_state.get("repair"):
        _list.append(("✅", f"Patches · {len(st.session_state.repair['applied'])} applied"))
    if st.session_state.get("validation"):
        v0 = st.session_state.validation
        _list.append(("✅" if (v0.ran and v0.passed) else "⏸", "Validation"))
    for icon, label in _list:
        st.markdown(f"{icon}&nbsp;&nbsp;{label}", unsafe_allow_html=True)
    if not _list:
        st.markdown("⏳&nbsp;&nbsp;Awaiting input…", unsafe_allow_html=True)
    st.markdown("<hr>", unsafe_allow_html=True)
    if not ai.enabled:
        st.warning("OPENROUTER_API_KEY not set — AI features disabled.")
    _m1, _m2, _m3 = st.columns(3)
    if _m1.button("🧹", key="reset_btn", help="Reset session"):
        if st.session_state.get("repo"):
            repo_input.cleanup_repo(st.session_state.repo)
        for k in list(st.session_state.keys()):
            if not k.startswith("_streamlit"):
                del st.session_state[k]
        st.rerun()
    st.markdown(
        "<div style='font-size:.75rem; opacity:.7; margin-top: 8px;'>"
        "Powered by OpenRouter · ruff · bandit · pytest · OSV"
        "</div>",
        unsafe_allow_html=True,
    )

tab_input, tab_findings, tab_ai, tab_repair, tab_valid, tab_report = st.tabs(
    ["📦 Input", "🔍 Findings", "🧠 AI Intelligence", "🔧 Repair", "🧪 Validation", "📤 Export"]
)

with tab_input:
    st.subheader("Provide a repository")
    source = st.radio(
        "Source",
        ["Public GitHub URL", "Upload ZIP", "Upload files", "Paste code", "Local folder"],
        horizontal=True,
    )
    repo = st.session_state.get("repo")

    def _loaded(info):
        st.session_state.repo = info
        st.session_state._analyzed = False

    if source == "Public GitHub URL":
        url = st.text_input("Repository URL", placeholder="https://github.com/user/repo")
        if st.button("Load repository", type="primary") and url:
            with st.spinner("Cloning..."):
                try:
                    _loaded(repo_input.clone_repo_from_url(url))
                    st.rerun()
                except Exception as e:
                    st.error(f"Clone failed: {e}")
    elif source == "Upload ZIP":
        zf = st.file_uploader("Repository ZIP", type=["zip"])
        if zf and st.button("Load ZIP", type="primary"):
            try:
                _loaded(repo_input.load_repo_from_zip(zf.getvalue()))
                st.rerun()
            except Exception as e:
                st.error(f"Unzip failed: {e}")
    elif source == "Upload files":
        docs = "Select one or many source files (paths inside the ZIP-style names are preserved)."
        upl = st.file_uploader(docs, accept_multiple_files=True)
        if upl and st.button("Load files", type="primary"):
            try:
                _loaded(repo_input.load_repo_from_uploads(upl))
                st.rerun()
            except Exception as e:
                st.error(f"Load failed: {e}")
    elif source == "Paste code":
        code = st.text_area("Paste your code", height=260, placeholder="# paste Python or any text source here")
        fname = st.text_input("File name", value="pasted_code.py")
        if st.button("Load pasted code", type="primary") and code.strip():
            try:
                _loaded(repo_input.load_repo_from_paste(code, fname))
                st.rerun()
            except Exception as e:
                st.error(f"Load failed: {e}")
    else:
        folder = st.text_input("Local folder path", placeholder=r"C:\path\to\project")
        if st.button("Load folder", type="primary") and folder:
            try:
                _loaded(repo_input.load_repo_from_folder(folder))
                st.rerun()
            except Exception as e:
                st.error(f"Load failed: {e}")

    if repo:
        st.success(f"Loaded **{repo.name}** from `{repo.path}`")

    if repo and (st.button("🚀 Run full analysis", type="primary") or not st.session_state.get("_analyzed")):
        with st.spinner("Processing repository files..."):
            processed = repo_processing.collect_files(repo.path)
            st.session_state.processed = processed
        st.session_state.analysis = {
            "findings": [],
            "vulns": check_vulnerabilities(processed.dependencies),
        }
        try:
            static = run_static_analysis(repo.path, processed.files)
        except Exception as e:
            st.error(f"Static tools error: {e}")
            static = None
        if static:
            st.session_state.analysis["findings"] = sorted_findings(static.findings)
        st.session_state._analyzed = True
        st.rerun()

    if st.session_state.get("processed"):
        p = st.session_state.processed
        mcols = st.columns(4)
        mcols[0].metric("Files analyzed", len(p.files))
        mcols[1].metric("Files skipped", p.skipped_count)
        mcols[2].metric("Findings", len(st.session_state.analysis["findings"]))
        mcols[3].metric(
            "Vulnerable deps",
            len(st.session_state.analysis.get("vulns", [])),
        )
        left, right = st.columns([2, 2])
        with left:
            st.markdown("#### Language breakdown")
            st.bar_chart(pd.Series(p.languages, name="files"))
        with right:
            st.markdown("#### Detected dependencies")
            deps = p.dependencies["requirements"] + p.dependencies["pyproject"]
            if deps:
                st.markdown(
                    "<div style='display:flex;	flex-wrap:wrap;	gap:6px;'>"
                    + "".join(
                        f"<span class='dep-chip'>{d}</span>" for d in deps[:18]
                    )
                    + "</div>",
                    unsafe_allow_html=True,
                )
            else:
                st.caption("No manifest dependencies detected.")

with tab_findings:
    rows = findings_to_rows(st.session_state.analysis.get("findings", [])) \
        if st.session_state.get("analysis") else []
    if not rows:
        st.info("No analysis yet — load a repository in the **Input** tab and run analysis.")
    else:
        total = len(rows)
        by_sev = {}
        for r0 in rows:
            by_sev[r0["Severity"]] = by_sev.get(r0["Severity"], 0) + 1
        kcols = st.columns(min(len(by_sev) + 1, 6))
        kcols[0].metric("Total findings", total)
        for j, sev in enumerate(["critical", "high", "medium", "low", "info"]):
            if j + 1 < len(kcols) and sev in by_sev:
                kcols[j + 1].metric(sev.capitalize(), by_sev[sev])
        vrows = findings_to_rows(st.session_state.analysis.get("vulns", []))
        if vrows:
            st.markdown("#### 🛑 Vulnerable dependencies")
            st.dataframe(_sev_styles(pd.DataFrame(vrows), "Severity"), use_container_width=True)
        st.markdown("#### 🔍 Static-analysis findings")
        st.dataframe(
            _sev_styles(pd.DataFrame(rows), "Severity"),
            use_container_width=True,
            height=430,
        )

with tab_ai:
    if not ai.enabled:
        st.info("Set OPENROUTER_API_KEY in .env to enable AI explanations.")
    if st.session_state.get("analysis") and ai.enabled:
        if st.button("🧠 Explain top findings"):
            with st.spinner("Asking AI model..."):
                files = ai.select_context_files(
                    st.session_state.processed.files,
                    st.session_state.analysis["findings"],
                )
                st.session_state.ai_explanations = ai.explain_findings(
                    st.session_state.analysis["findings"], files
                )
        for item in st.session_state.get("ai_explanations", []):
            f = item["finding"]
            fg, bg = _SEVERITY_COLORS.get(f.severity.lower(), ("#4b5563", "#f3f4f6"))
            badge = (
                f"<span style='background:{bg};color:{fg};font-weight:700;padding:2px 10px;"
                f"border-radius:999px;font-size:.75rem;margin-right:8px;'>{f.severity.upper()}</span>"
            )
            st.markdown(
                f"<div style='margin-bottom:-6px;'>{badge}<code>{f.file}:{f.line}</code></div>",
                unsafe_allow_html=True,
            )
            with st.expander(f.message[:90]):
                st.markdown(item["explanation"])
                st.markdown(
                    f"<div style='font-size:.8rem;opacity:.6;'>Tool: <code>{f.tool}</code> · Model: "
                    f"<code>{ai.model.split('/')[-1]}</code></div>",
                    unsafe_allow_html=True,
                )

def _syntax_ok_string(text: str) -> bool:
    try:
        ast.parse(text)
        return True
    except SyntaxError:
        return False


with tab_repair:
    files = st.session_state.get("processed")
    findings = st.session_state.analysis.get("findings", []) if st.session_state.get("analysis") else []
    if not ai.enabled or not files:
        st.info("AI key + analyzed repo required.")
    elif st.button("🔧 Generate & apply patches"):
        by_file: dict = {}
        for f in findings:
            by_file.setdefault(f.file, []).append(f)
        result = {"attempts": [], "applied": [], "failed": []}
        progress = st.progress(0.0)
        file_map = {f.rel_path: f for f in files.files}
        for i, (rel, fnd) in enumerate(by_file.items()):
            src = file_map.get(rel)
            if not src or src.language != "Python":
                continue
            lines = src.path.read_text(encoding="utf-8", errors="ignore").splitlines(keepends=True)
            patched, err = None, None
            for attempt in range(3):
                patched, err = generate_repair(ai, src, lines, fnd)
                if patched and _syntax_ok_string(patched):
                    break
            if not patched:
                result["failed"].append({"file": rel, "error": err or "no patch produced"})
            else:
                diff = extract_unified_diff("".join(lines), patched, rel)
                if diff:
                    apply_patch(src, patched)
                    result["applied"].append(
                        RepairAttempt(file=rel, diff=diff, original="".join(lines), patched=patched)
                    )
            progress.progress((i + 1) / max(len(by_file), 1))
        st.session_state.repair = result
        st.rerun()
    rep = st.session_state.get("repair")
    if rep:
        okcols = st.columns(2)
        okcols[0].metric("Patches applied", len(rep["applied"]))
        okcols[1].metric("Failed files", len(rep["failed"]))
        for a in rep["applied"]:
            with st.expander(f"🟩 Patch: {a.file}", expanded=True):
                st.code(a.diff, language="diff")
        for f in rep["failed"]:
            st.warning(f"Failed: {f['file']} — {f['error']}")

with tab_valid:
    if st.session_state.get("repo") and st.session_state.get("repair"):
        if st.button("🧪 Run pytest validation"):
            with st.spinner("Running tests in isolated temp sandbox..."):
                st.session_state.validation = validate_patch(
                    st.session_state.repo.path, st.session_state.processed.files
                )
    v = st.session_state.get("validation")
    if v:
        ok = st.success if (v.ran and v.passed) else (st.warning if not v.ran else st.error)
        ok(f"Tests ran: {v.ran} | Passed: {v.passed}")
        st.code(v.output or "(no output)", language="text")
    else:
        st.info("Run **Repair** first, then validate patches with pytest in an isolated sandbox here.")

with tab_report:
    if st.session_state.get("repo") and st.session_state.get("analysis"):
        st.markdown(download_button_markdown(st.session_state))
        with st.expander("Full report preview"):
            from core.report import report_markdown
            st.markdown(report_markdown(st.session_state))
    else:
        st.info("Load and analyze a repository first.")
