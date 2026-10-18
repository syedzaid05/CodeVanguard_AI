import json
from datetime import UTC, datetime

import streamlit as st


def findings_to_rows(findings):
    return [
        {"Tool": f.tool, "Severity": f.severity, "File": f.file, "Line": f.line, "Message": f.message}
        for f in findings
    ]


def report_markdown(state) -> str:
    repo = state["repo"]
    analysis = state["analysis"]
    deps = analysis["vulns"]
    ai = state.get("ai_explanations", [])
    repair = state.get("repair")
    validation = state.get("validation")

    lines = [
        "# AI Code Repair Report",
        "",
        f"- **Repository:** {repo.name} ({repo.source})",
        f"- **Generated:** {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}",
        f"- **Languages:** {', '.join(f'{k} ({v})' for k, v in state['processed'].languages.items())}",
        "",
        "## Vulnerable Dependencies",
    ]
    if deps:
        lines.extend(f"- `{d.message}`" for d in deps)
    else:
        lines.append("- None detected")

    lines.append("\n## Findings")
    if analysis["findings"]:
        for f in analysis["findings"]:
            lines.append(f"- **[{f.severity.upper()}] `{f.file}`:{f.line}** ({f.tool}) — {f.message}")
    else:
        lines.append("- No findings")

    if ai:
        lines.append("\n## AI Explanations")
        for item in ai:
            f = item["finding"]
            lines.append(f"### `{f.file}`:{f.line} — {f.message}")
            lines.append(item["explanation"])
            lines.append("")

    if repair:
        lines.append("\n## Applied Patches")
        for a in repair["applied"]:
            lines.append(f"### {a.file}")
            lines.append(f"```diff\n{a.diff}```")
            lines.append("")

    if validation:
        lines.append("\n## Validation")
        lines.append(f"- Ran: {validation.ran} | Passed: {validation.passed}")
        lines.append(f"```\n{validation.output[:3000]}\n```")

    return "\n".join(lines)


def export_json(state) -> str:
    out = {
        "repo": {"name": state["repo"].name, "source": state["repo"].source},
        "languages": state["processed"].languages,
        "dependencies": state["processed"].dependencies,
        "findings": findings_to_rows(state["analysis"]["findings"]),
        "vulnerable_dependencies": [f.message for f in state["analysis"]["vulns"]],
        "ai_explanations": [
            {"file": i["finding"].file, "line": i["finding"].line, "explanation": i["explanation"]}
            for i in state.get("ai_explanations", [])
        ],
        "patches": [
            {"file": a.file, "diff": a.diff} for a in state.get("repair", {}).get("applied", [])
        ],
        "validation": {
            "ran": state["validation"].ran,
            "passed": state["validation"].passed,
            "output": state["validation"].output,
        } if state.get("validation") else None,
    }
    return json.dumps(out, indent=2, default=str)


def export_csv(state) -> str:
    import csv
    import io

    rows = findings_to_rows(state["analysis"]["findings"])
    buf = io.StringIO()
    if rows:
        writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return buf.getvalue()


def export_patches(state) -> str:
    parts = []
    for a in state.get("repair", {}).get("applied", []):
        parts.append(a.diff if a.diff.endswith("\n") else a.diff + "\n")
    return "\n".join(parts)


def render_export_buttons(state):
    st.markdown("#### 📤 Export artifacts")
    c1, c2, c3, c4 = st.columns(4)
    c1.download_button(
        "📄 Markdown report", report_markdown(state),
        file_name="repair_report.md", mime="text/markdown",
    )
    c2.download_button(
        "🧾 JSON report", export_json(state),
        file_name="repair_report.json", mime="application/json",
    )
    c3.download_button(
        "📊 Findings CSV", export_csv(state),
        file_name="findings.csv", mime="text/csv",
    )
    c4.download_button(
        "🩹 Combined patches", export_patches(state),
        file_name="patches.patch", mime="text/x-diff", disabled=not state.get("repair"),
    )
    rep = state.get("repair") or {}
    val = state.get("validation")
    mc1, mc2, mc3, mc4 = st.columns(4)
    mc1.metric("Findings", len(state["analysis"]["findings"]))
    mc2.metric("Vuln deps", len(state["analysis"].get("vulns", [])))
    mc3.metric("Patches applied", len(rep.get("applied", [])) if rep else 0)
    mc4.metric("Validation", ("passed" if val.passed else "failed") if val else "n/a")


def download_button_markdown(state):
    st.download_button(
        "Download report (Markdown)",
        report_markdown(state),
        file_name="repair_report.md",
        mime="text/markdown",
    )
    st.download_button(
        "Download report (JSON)",
        export_json(state),
        file_name="repair_report.json",
        mime="application/json",
    )
