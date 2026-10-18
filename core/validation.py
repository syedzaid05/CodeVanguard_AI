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
        if f.language != "Python":
            continue
        try:
            ast.parse(f.path.read_text(encoding="utf-8", errors="ignore"))
        except SyntaxError as e:
            errors.append(f"{f.rel_path}: line {e.lineno}: {e.msg}")
    return errors


def run_tests(root: Path, timeout: int = 300) -> ValidationReport:
    if not _has_tests(root):
        return ValidationReport(False, False, "No pytest tests found in repository.")
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
