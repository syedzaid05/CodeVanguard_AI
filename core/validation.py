import ast
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ValidationReport:
    ran: bool
    passed: bool
    output: str
    syntax_ok: bool = True
    regression_ok: bool = True
    details: list = field(default_factory=list)


def syntax_check(root: Path, files) -> list:
    errors = []
    for f in files:
        if f.language == "Python":
            try:
                ast.parse(f.path.read_text(encoding="utf-8", errors="ignore"))
            except SyntaxError as e:
                errors.append(f"{f.rel_path}: line {e.lineno}: {e.msg}")
        elif f.language == "Jupyter Notebook":
            from core import repo_processing
            mirror = repo_processing.build_mirror(repo_processing.notebook_cells(f.path))
            try:
                ast.parse(mirror)
            except SyntaxError as e:
                errors.append(f"{f.rel_path} (cell offset line {e.lineno}): {e.msg}")
    return errors


def run_tests(root: Path, timeout: int = 300) -> ValidationReport:
    if not _has_tests(root):
        return smoke_check(root)
    tmp = Path(tempfile.mkdtemp(prefix="validate_"))
    work_dir = tmp / "sandbox"
    shutil.copytree(root, work_dir, ignore=shutil.ignore_patterns(".git", "__pycache__", ".venv", "venv"))
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "-x", "-q", "--tb=short", "-p", "no:cacheprovider"],
            check=False,
            cwd=work_dir,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        output = (proc.stdout + "\n" + proc.stderr)[-8000:]
        return ValidationReport(True, proc.returncode == 0, output)
    except subprocess.TimeoutExpired:
        return ValidationReport(True, False, f"pytest timed out after {timeout}s.")
    except OSError as e:
        return ValidationReport(True, False, f"Failed to run pytest: {e}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def smoke_check(root: Path) -> ValidationReport:
    """Fallback when the repo has no pytest tests: compile all Python code
    (and notebook code cells) in an isolated sandbox."""
    py_files = [
        p for p in root.rglob("*.py")
        if "__pycache__" not in p.parts and ".git" not in p.parts
    ]
    ok = True
    output_lines = []
    for p in py_files:
        try:
            compile(p.read_text(encoding="utf-8", errors="ignore"), str(p), "exec")
        except (SyntaxError, ValueError) as e:
            ok = False
            name = p.name
            output_lines.append(f"COMPILE ERROR {name}: line {getattr(e, 'lineno', '?')}: {getattr(e, 'msg', e)}")
    from core import repo_processing
    for p in root.rglob("*.ipynb"):
        if ".git" in p.parts or "__pycache__" in p.parts:
            continue
        cells = repo_processing.notebook_cells(p)
        for i, cell in enumerate(cells):
            if not cell.strip():
                continue
            try:
                compile(cell, f"{p.name} [cell {i}]", "exec")
            except (SyntaxError, ValueError) as e:
                ok = False
                output_lines.append(f"COMPILE ERROR {p.name} [cell {i}]: line {getattr(e, 'lineno', '?')}: {getattr(e, 'msg', e)}")
    if not py_files and not root.rglob("*.ipynb"):
        return ValidationReport(True, True, "No Python code or notebooks found — nothing to validate.")
    n_compiled = len(py_files) + sum(1 for p in root.rglob("*.ipynb") if repo_processing.notebook_cells(p))
    if ok:
        output_lines.append(f"Smoke validation passed: {n_compiled} code unit(s) compile cleanly.")
    else:
        output_lines.insert(0, "Smoke validation FAILED:")
    return ValidationReport(True, ok, "\n".join(output_lines))


def validate_patch(root: Path, files, timeout: int = 300) -> ValidationReport:
    details = syntax_check(root, files)
    report = run_tests(root, timeout=timeout)
    report.syntax_ok = not details
    report.details = details
    if details:
        report.passed = False
        report.output = "\n".join(details) + "\n\n" + report.output
    return report


def _has_tests(root: Path) -> bool:
    return any(root.rglob("test_*.py")) or any(root.rglob("*_test.py")) or (root / "tests").is_dir()
