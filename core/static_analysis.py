import ast
import json
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import requests

from core import repo_processing


@dataclass
class Finding:
    tool: str
    severity: str
    file: str
    line: int
    message: str
    code: str = ""


@dataclass
class AnalysisResult:
    findings: list = field(default_factory=list)
    build_errors: list = field(default_factory=list)


SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}


def run_static_analysis(root: Path, files) -> AnalysisResult:
    result = AnalysisResult()
    result.build_errors = _ast_check(files)
    result.findings.extend(result.build_errors)
    result.findings.extend(_ruff(root))
    result.findings.extend(_bandit(root))
    result.findings.extend(_notebook_findings(files))
    # ruff >=0.7 lints notebooks natively; drop duplicate findings from mirror runs
    seen = set()
    deduped = []
    for f in result.findings:
        key = (f.tool, f.file, f.line, f.message)
        if key not in seen:
            seen.add(key)
            deduped.append(f)
    result.findings = deduped
    return result


def _notebook_findings(files) -> list:
    """Analyze code cells of notebooks via a temporary mirror directory."""
    nbs = [f for f in files if f.language == "Jupyter Notebook"]
    if not nbs:
        return []
    findings = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        mapping = {}  # mirror filename -> (rel_path, [marker line numbers 1-based])
        for nb in nbs:
            cells = repo_processing.notebook_cells(nb.path)
            if not cells:
                continue
            mirror = repo_processing.build_mirror(cells)
            try:
                ast.parse(mirror)
            except SyntaxError as e:
                findings.append(
                    Finding("ast", "high", nb.rel_path, e.lineno or 1, f"Syntax error: {e.msg}")
                )
            mname = nb.rel_path.replace("/", "__")[:-len(".ipynb")] + ".py"
            (tmp_dir / mname).write_text(mirror, encoding="utf-8")
            marker_lines = [
                i + 1 for i, l in enumerate(mirror.splitlines())
                if l.startswith("# %% [cell ")
            ]
            mapping[mname] = (nb.rel_path, marker_lines)
        if not mapping:
            return []
        bandit_out = _bandit_dir(tmp_dir) or {}
        for item in bandit_out.get("results", []):
            findings.append(_remap_nb(item, "bandit", tmp_dir, mapping))
    return findings


def _remap_nb(item, tool, tmp_dir: Path, mapping: dict) -> "Finding":
    if tool == "ruff":
        raw_name = item.get("filename", "")
        line = item.get("start", {}).get("line", 1)
        sev = "high" if item.get("message", "").startswith("F") else "low"
        msg = f"{item.get('code')}: {item.get('message')}"
    else:
        raw_name = item.get("filename", "")
        line = item.get("line_number", 1)
        sev = str(item.get("issue_severity", "Low")).lower()
        msg = f"{item.get('test_id')}: {item.get('issue_text')}"
    mname = Path(raw_name).name
    rel, marks = mapping.get(mname, (raw_name, []))
    cell = 0
    for j, ml in enumerate(marks):
        if ml <= line:
            cell = j
    if marks:
        line_in_cell = line - marks[cell] + 1
        msg = f"[cell {cell}] {msg}"
    return Finding(tool, sev, rel, max(line_in_cell if marks else line, 1), msg)


def _ast_check(files) -> list:
    findings = []
    for f in files:
        if f.language != "Python":
            continue
        try:
            ast.parse(f.path.read_text(errors="ignore"))
        except SyntaxError as e:
            findings.append(
                Finding("ast", "high", f.rel_path, e.lineno or 1, f"Syntax error: {e.msg}")
            )
    return findings


def _ruff(root: Path, skip_run: bool = False):
    out = _run_tool(["-m", "ruff"], ["check", "--output-format=json", "."], root)
    if skip_run:
        return out
    findings = []
    for item in out or []:
        sev = "high" if item.get("message", "").startswith("F") else "low"
        findings.append(
            Finding("ruff", sev, _rel(item.get("filename", ""), root),
                    item.get("start", {}).get("line", 1),
                    f"{item.get('code')}: {item.get('message')}")
        )
    return findings


def _bandit(root: Path) -> list:
    out = _bandit_dir(root) or {}
    findings = []
    for item in out.get("results", []):
        sev = str(item.get("issue_severity", "Low")).lower()
        findings.append(
            Finding("bandit", sev if sev != "medium" else "medium",
                    item.get("filename", ""), item.get("line_number", 1),
                    f"{item.get('test_id')}: {item.get('issue_text')}")
        )
    return findings


def _bandit_dir(root: Path):
    return _run_tool(["-m", "bandit"], ["-q", "-r", "-f", "json", "./"], root)


def _run_tool(module_args: list, args: list, root: Path):
    try:
        proc = subprocess.run(
            [sys.executable] + module_args + args,
            check=False, cwd=root, capture_output=True, text=True, timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    data = proc.stdout.strip() or proc.stderr.strip()
    try:
        return json.loads(data)
    except json.JSONDecodeError:
        return None


def check_vulnerabilities(dependencies: dict) -> list:
    findings = []
    for dep in dependencies.get("requirements", []):
        name = dep.split("==")[0].split(">=")[0].strip()
        for vuln in _osv_query(name, dep):
            findings.append(
                Finding("osv", vuln.get("severity", "medium"), dep, 0,
                        f"{vuln['id']} affects {name}: {vuln['summary'][:140]}")
            )
    return findings


def _osv_query(package: str, dep_spec: str) -> list:
    try:
        resp = requests.post(
            "https://api.osv.dev/v1/query",
            json={"package": {"name": package, "ecosystem": "PyPI"}},
            timeout=20,
        )
        resp.raise_for_status()
        vulns = resp.json().get("vulns", [])[:3]
    except requests.RequestException:
        return []
    results = []
    for v in vulns:
        severity = "medium"
        for s in v.get("severity", []):
            if s.get("score", "").startswith("CVSS") and "9" in s["score"][:20]:
                severity = "high"
        if v.get("database_specific", {}).get("severity") == "CRITICAL":
            severity = "critical"
        results.append({"id": v.get("id", "UNKNOWN"), "summary": v.get("summary", ""), "severity": severity})
    return results


def sorted_findings(findings) -> list:
    return sorted(findings, key=lambda f: SEVERITY_ORDER.get(f.severity, 4))


def _rel(name: str, root: Path) -> str:
    try:
        return str(Path(name).resolve().relative_to(Path(root).resolve()))
    except ValueError:
        return name

