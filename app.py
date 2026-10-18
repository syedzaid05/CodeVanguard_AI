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
from core.report import findings_to_rows, render_export_buttons
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
        --accent-soft: #eef2ff;
        --success: #059669;
        --warning: #d97706;
        --danger: #dc2626;
        --ink: #0f172a;
        --muted: #64748b;
        --card-border: #e2e8f0;
        --card-bg: #ffffff;
        --surface: #f8fafc;
    }
    .stApp { background: radial-gradient(1200px 500px at 80% -10%, #eef2ff 0%, transparent 60%), #f8fafc; }
    .block-container { padding-top: 1.4rem; max-width: 1500px; }
    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #0b1020 0%, #151a33 55%, #1e1b4b 100%);
        border-right: 1px solid rgba(99, 102, 241, .18);
    }
    section[data-testid="stSidebar"] * { color: #e5e7eb !important; }
    section[data-testid="stSidebar"] hr { border-color: rgba(255,255,255,.12); }
    section[data-testid="stSidebar"] input, section[data-testid="stSidebar"] [data-baseweb="input"] {
        background: rgba(255,255,255,.06) !important;
    }
    div[data-testid="stButton"] > button { border-radius: 10px; font-weight: 600; transition: all .15s ease; border: 1px solid var(--card-border); }
    div[data-testid="stButton"] > button:hover { transform: translateY(-1px); box-shadow: 0 6px 16px rgba(15, 23, 42, .08); border-color: #c7d2fe; }
    div[data-testid="stButton"] > button[kind="primary"] {
        background: linear-gradient(135deg, #4f46e5, #6366f1 55%, #818cf8);
        border: none;
        color: #fff;
        box-shadow: 0 6px 18px rgba(79, 70, 229, .35);
    }
    div[data-testid="stMetric"] {
        background: var(--card-bg);
        border: 1px solid var(--card-border);
        border-radius: 14px;
        padding: 16px 18px;
        box-shadow: 0 1px 2px rgba(15, 23, 42, .04);
    }
    div[data-testid="stMetric"] label { color: var(--muted) !important; font-size: .78rem !important; text-transform: uppercase; letter-spacing: .06em; }
    div[data-testid="stMetric"] [data-testid="stMetricValue"] { font-weight: 800; color: var(--ink); }
    div[data-testid="stTabs"] [role="tablist"] button {
        border-radius: 10px 10px 0 0; font-weight: 700; letter-spacing: .01em;
        padding: 10px 18px;
    }
    div[data-testid="stTabs"] [role="tablist"] button[aria-selected="true"] {
        background: linear-gradient(180deg, #eef2ff, #ffffff);
        border-top: 3px solid var(--accent);
        color: #312e81;
    }
    .hero {
        position: relative;
        overflow: hidden;
        background: linear-gradient(120deg, #0b1020 0%, #1b1f3a 45%, #312e81 100%);
        border-radius: 18px;
        padding: 30px 34px;
        margin-bottom: 16px;
        color: #fff;
        box-shadow: 0 18px 40px rgba(15, 23, 42, .18);
    }
    .hero::after {
        content: ""; position: absolute; inset: auto -40% -60% auto;
        width: 420px; height: 420px; border-radius: 50%;
        background: radial-gradient(circle, rgba(99,102,241,.35), transparent 65%);
        pointer-events: none;
    }
    .hero h1 { color: #fff; margin: 0; font-size: 1.85rem; letter-spacing: -.01em; }
    .hero p { color: #c7d2fe; margin: 8px 0 0 0; font-size: .98rem; max-width: 720px; }
    .hero .brand-badge {
        display: inline-block;
        background: rgba(99, 102, 241, .25);
        border: 1px solid rgba(129, 140, 248, .5);
        color: #c7d2fe;
        font-size: .72rem;
        font-weight: 700;
        letter-spacing: .08em;
        text-transform: uppercase;
        padding: 4px 12px;
        border-radius: 999px;
        margin-bottom: 12px;
    }
    .hero-stats { display: flex; gap: 10px; flex-wrap: wrap; margin-top: 16px; }
    .hero-stats .hstat {
        background: rgba(255,255,255,.06);
        border: 1px solid rgba(255,255,255,.12);
        border-radius: 12px;
        padding: 8px 14px;
        font-size: .82rem;
        color: #e0e7ff;
    }
    .hero-stats .hstat b { color: #fff; }
    .step-legend { display: flex; gap: 8px; flex-wrap: wrap; margin: 4px 0 18px 0; }
    .step-legend span {
        background: #fff; color: #3730a3; border: 1px solid #c7d2fe;
        border-radius: 999px; padding: 5px 14px; font-size: .8rem; font-weight: 600;
        box-shadow: 0 1px 2px rgba(79,70,229,.08);
    }
    .dep-chip {
        background: #f1f5f9; color: #334155; border: 1px solid #e2e8f0;
        border-radius: 8px; padding: 5px 11px; font-size: .8rem;
        font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    }
    .pipe-item {
        display: flex; align-items: center; gap: 10px;
        padding: 8px 10px; border-radius: 10px; margin: 2px 0;
        border: 1px solid transparent; font-size: .88rem;
    }
    .pipe-item .dot {
        width: 10px; height: 10px; border-radius: 50%;
        background: rgba(255,255,255,.18); flex: 0 0 auto;
        box-shadow: 0 0 0 3px rgba(255,255,255,.06);
    }
    .pipe-item.done { background: rgba(16, 185, 129, .12); border-color: rgba(16, 185, 129, .25); }
    .pipe-item.done .dot { background: #34d399; box-shadow: 0 0 0 3px rgba(52, 211, 153, .2); }
    .pipe-item.idle { opacity: .72; }
    .prov-chip {
        display: inline-flex; align-items: center; gap: 6px;
        border-radius: 999px; padding: 3px 10px; font-size: .74rem; font-weight: 700;
        border: 1px solid rgba(255,255,255,.14); margin: 2px 4px 2px 0;
        background: rgba(255,255,255,.06); color: #e5e7eb;
    }
    .prov-chip.ok { background: rgba(16,185,129,.16); border-color: rgba(52,211,153,.35); color: #a7f3d0; }
    .section-card {
        background: var(--card-bg); border: 1px solid var(--card-border);
        border-radius: 14px; padding: 18px 20px; margin-bottom: 14px;
        box-shadow: 0 1px 2px rgba(15, 23, 42, .04);
    }
    .empty-state {
        text-align: center; padding: 42px 20px; color: var(--muted);
        border: 1px dashed #cbd5e1; border-radius: 16px; background: rgba(255,255,255,.6);
    }
    .empty-state .es-icon { font-size: 2rem; margin-bottom: 6px; }
    .empty-state p { margin: 4px 0 0 0; font-size: .92rem; }
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
          <div class="hero-stats">
            <div class="hstat"><b>6-step</b> pipeline</div>
            <div class="hstat"><b>Multi-provider</b> AI fallback</div>
            <div class="hstat"><b>ruff · bandit · OSV</b> analysis</div>
            <div class="hstat"><b>pytest</b> sandbox validation</div>
          </div>
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
    st.markdown("<div style='font-size:.72rem;opacity:.65;letter-spacing:.1em;text-transform:uppercase;margin-bottom:6px;'>Pipeline</div>", unsafe_allow_html=True)
    steps = []
    if st.session_state.get("repo"):
        steps.append(("done", "Repository loaded"))
    if st.session_state.get("_analyzed") and st.session_state.get("analysis"):
        steps.append(("done", f"Analysis · {len(st.session_state.analysis['findings'])} findings"))
    if st.session_state.get("ai_explanations"):
        steps.append(("done", "AI explanations ready"))
    if st.session_state.get("repair"):
        steps.append(("done", f"Patches · {len(st.session_state.repair['applied'])} applied"))
    if st.session_state.get("validation"):
        v0 = st.session_state.validation
        steps.append(("done" if (v0.ran and v0.passed) else "idle", "Validation"))
    for state, label in steps:
        st.markdown(f"<div class='pipe-item {state}'><span class='dot'></span>{label}</div>", unsafe_allow_html=True)
    if not steps:
        st.markdown("<div class='pipe-item idle'><span class='dot'></span>Awaiting input…</div>", unsafe_allow_html=True)
    st.markdown("<hr>", unsafe_allow_html=True)
    st.markdown("<div style='font-size:.72rem;opacity:.65;letter-spacing:.1em;text-transform:uppercase;margin-bottom:6px;'>AI providers</div>", unsafe_allow_html=True)
    prov_bits = []
    if ai.api_key:
        prov_bits.append(f"<span class='prov-chip ok'>● OpenRouter</span>")
    if ai.fallbacks:
        for fname, *_ in ai.fallbacks:
            prov_bits.append(f"<span class='prov-chip ok'>● {fname}</span>")
    if prov_bits:
        st.markdown("<div>" + "".join(prov_bits) + "</div>", unsafe_allow_html=True)
        st.caption("Fallback order: " + " → ".join(
            [f for f, *_ in ai.fallbacks] + (["OpenRouter"] if ai.api_key else [])
        ))
    else:
        st.warning("No API key set — AI features disabled.")
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
        "Powered by OpenRouter · Groq · Gemini · ruff · bandit · pytest · OSV"
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
        st.markdown(
            f"<div class='section-card'>✅ Loaded <b>{repo.name}</b> from <code>{repo.path}</code></div>",
            unsafe_allow_html=True,
        )

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
                    "<div style='display:flex; flex-wrap:wrap; gap:6px;'>"
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
        st.markdown(
            '<div class="empty-state"><div class="es-icon">🔍</div>'
            '<b>No analysis yet</b><p>Load a repository in the <b>Input</b> tab and run analysis.</p></div>',
            unsafe_allow_html=True,
        )
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
            st.dataframe(_sev_styles(pd.DataFrame(vrows), "Severity"), width="stretch")
        st.markdown("#### 🔍 Static-analysis findings")
        st.dataframe(
            _sev_styles(pd.DataFrame(rows), "Severity"),
            width="stretch",
            height=430,
        )

with tab_ai:
    if not ai.enabled:
        st.markdown(
            '<div class="empty-state"><div class="es-icon">🧠</div>'
            '<b>AI disabled</b><p>Set OPENROUTER_API_KEY, GROQ_API_KEY or GOOGLE_GEMINI_API_KEY in .env.</p></div>',
            unsafe_allow_html=True,
        )
    if st.session_state.get("analysis") and ai.enabled:
        if st.button("🧠 Explain top findings", type="primary"):
            with st.spinner("Selecting context files..."):
                files = ai.select_context_files(
                    st.session_state.processed.files,
                    st.session_state.analysis["findings"],
                )
            status = st.status("Asking AI model...", expanded=True)
            pbar = st.progress(0.0)
            results = []

            def _cb(done, total, finding):
                if done == -1:
                    pbar.progress(1.0 if not results else min(len(results) / total, 1.0))
                else:
                    status.update(label=f"Explaining {done}/{total} — {finding.file}:{finding.line}")
                    pbar.progress((done - 1) / max(total, 1))

            st.session_state.ai_explanations = ai.explain_findings(
                st.session_state.analysis["findings"], files, _cb
            )
            pbar.progress(1.0)
            status.update(label="Explanations ready ✅", state="complete", expanded=False)
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
        st.markdown(
            '<div class="empty-state"><div class="es-icon">🔧</div>'
            '<b>Not ready</b><p>AI key + analyzed repo required before generating patches.</p></div>',
            unsafe_allow_html=True,
        )
    elif st.button("🔧 Generate & apply patches", type="primary"):
        try:
            def _norm(pth: str) -> str:
                return pth.replace("\\", "/").lstrip("./") if pth else pth

            by_file: dict = {}
            for f in findings:
                by_file.setdefault(_norm(f.file), []).append(f)
            result = {"applied": [], "failed": [], "findings": len(findings), "skipped": 0, "unmatched": []}
            progress = st.progress(0.0, text="Generating repair patches…")
            file_map = {f.rel_path: f for f in files.files}
            skipped, repaired = 0, 0
            for i, (rel, fnd) in enumerate(by_file.items()):
                src = file_map.get(rel)
                if not src or src.language not in ("Python", "Jupyter Notebook"):
                    result["skipped"] += 1
                    result["unmatched"].append(rel)
                    continue
                progress.progress(0.0, text=f"Repairing {rel}…")
                lines = src.path.read_text(encoding="utf-8", errors="ignore").splitlines(keepends=True)
                orig_text = "".join(lines)
                nb_cells = None
                if src.language == "Jupyter Notebook":
                    from core import repo_processing
                    nb_cells = repo_processing.notebook_cells(src.path)
                    if not nb_cells:
                        result["failed"].append({"file": rel, "error": "no code cells"})
                        continue
                    lines = repo_processing.build_mirror(nb_cells).splitlines(keepends=True)
                patched, err = None, None
                for attempt in range(3):
                    patched, err = generate_repair(ai, src, lines, fnd)
                    if patched and _syntax_ok_string(patched):
                        break
                if not patched:
                    result["failed"].append({"file": rel, "error": err or "no patch produced"})
                else:
                    diff = extract_unified_diff(orig_text, patched, rel)
                    applied_ok = False
                    if nb_cells:
                        from core import repo_processing
                        applied_ok = repo_processing.apply_notebook_patch(
                            src.path, patched, nb_cells
                        )
                        if not applied_ok:
                            result["failed"].append({"file": rel, "error": "patch lost notebook cell markers"})
                            continue
                    else:
                        apply_patch(src, patched)
                        applied_ok = True
                    if applied_ok and diff:
                        repaired += 1
                        result["applied"].append(
                            RepairAttempt(file=rel, diff=diff, original=orig_text, patched=patched)
                        )
                    elif not diff:
                        result["failed"].append({"file": rel, "error": "no changes produced"})
                progress.progress((i + 1) / max(len(by_file), 1), text=f"Done {rel}")
            st.session_state.repair = result
        except Exception:
            import traceback
            err_txt = traceback.format_exc()
            with open("repair_debug.log", "w", encoding="utf-8") as fh:
                fh.write(err_txt)
            st.error("Repair crashed — see repair_debug.log")
            st.code(err_txt, language="text")
        st.rerun()
    rep = st.session_state.get("repair")
    if rep:
        okcols = st.columns(2)
        okcols[0].metric("Patches applied", len(rep["applied"]))
        okcols[1].metric("Failed files", len(rep["failed"]))
        rep_files = st.session_state.get("processed")
        src_names = [f.rel_path for f in rep_files.files] if rep_files else []
        finding_files = sorted({f.file for f in findings})
        if rep.get("skipped"):
            st.warning(
                f"**{rep['skipped']}** file(s) with findings cannot be repaired "
                f"(not Python / no matching source): `{', '.join(rep.get('unmatched', [])) or '—'}`"
            )
        if not rep["applied"] and not rep["failed"]:
            st.info(
                f"Nothing to patch. Findings: **{rep.get('findings', 0)}** · "
                f"Files not matchable: **{rep.get('skipped', 0)}**\n\n"
                f"Files with findings: `{', '.join(finding_files) or '—'}`\n\n"
                f"Repo source files: `{', '.join(src_names[:20]) or '—'}`"
            )
            st.caption("Only **Python** files with matching paths can be repaired.")
        for f in rep["failed"]:
            with st.expander(f"❌ Failed: {f['file']}", expanded=True):
                st.error(f["error"])
        for a in rep["applied"]:
            with st.expander(f"🟩 Patch: {a.file}", expanded=False):
                st.code(a.diff, language="diff")

with tab_valid:
    if st.session_state.get("repo") and st.session_state.get("repair"):
        if st.button("🧪 Run pytest validation", type="primary"):
            with st.spinner("Running tests in isolated temp sandbox..."):
                st.session_state.validation = validate_patch(
                    st.session_state.repo.path, st.session_state.processed.files
                )
    v = st.session_state.get("validation")
    if v:
        ok = st.success if (v.ran and v.passed) else (st.warning if not v.ran else st.error)
        if "No pytest tests found in repository." in (v.output or ""):
            ok("No pytest tests in this repo — a compile smoke validation was performed instead.")
        else:
            ok(f"Tests ran: {v.ran} | Passed: {v.passed}")
        st.code(v.output or "(no output)", language="text")
    else:
        st.markdown(
            '<div class="empty-state"><div class="es-icon">🧪</div>'
            '<b>No validation yet</b><p>Run <b>Repair</b> first. Repos with pytest tests get a full sandboxed pytest run; others get a compile smoke check.</p></div>',
            unsafe_allow_html=True,
        )

with tab_report:
    if st.session_state.get("repo") and st.session_state.get("analysis"):
        render_export_buttons(st.session_state)
        with st.expander("Full report preview"):
            from core.report import report_markdown
            st.markdown(report_markdown(st.session_state))
    else:
        st.markdown(
            '<div class="empty-state"><div class="es-icon">📤</div>'
            '<b>Nothing to export</b><p>Load and analyze a repository first.</p></div>',
            unsafe_allow_html=True,
        )
