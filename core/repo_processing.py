import json
from dataclasses import dataclass, field
from pathlib import Path

from core.config import settings

LANG_BY_EXT = {
    ".py": "Python", ".js": "JavaScript", ".ts": "TypeScript", ".tsx": "TypeScript",
    ".java": "Java", ".go": "Go", ".rs": "Rust", ".rb": "Ruby", ".php": "PHP",
    ".c": "C", ".h": "C", ".cpp": "C++", ".cs": "C#", ".sh": "Shell",
    ".md": "Markdown", ".yml": "YAML", ".yaml": "YAML", ".json": "JSON",
    ".toml": "TOML", ".html": "HTML", ".css": "CSS", ".sql": "SQL",
    ".ipynb": "Jupyter Notebook",
}

CELL_MARKER = "# %% [cell {}]"

TEXT_EXTS = set(LANG_BY_EXT) | {".txt", ".cfg", ".ini", ".env.example", ".lock", ".csv"}


@dataclass
class SourceFile:
    path: Path
    rel_path: str
    language: str
    size: int


def notebook_cells(path: Path) -> list:
    """Extract code-cell sources from a .ipynb. Returns list of source strings."""
    try:
        nb = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    except (json.JSONDecodeError, OSError, ValueError):
        return []
    cells = []
    for c in nb.get("cells", []):
        if c.get("cell_type") == "code":
            src = c.get("source", "")
            cells.append("".join(src) if isinstance(src, list) else src)
    return cells


def build_mirror(cells: list) -> str:
    """Text fed as a virtual .py file to analysis/repair, with cell markers."""
    parts = []
    for i, src in enumerate(cells):
        parts.append(CELL_MARKER.format(i))
        parts.append(src.rstrip())
    return "\n".join(parts) + "\n"


def parse_mirror(text: str, expected_count: int):
    """Split a patched mirror file back into cell sources. None if markers lost."""
    import re
    idxs = list(re.finditer(r"^# %% \[cell (\d+)\]$", text, flags=re.M))
    if len(idxs) != expected_count:
        return None
    cells = []
    for j, m in enumerate(idxs):
        start = m.end()
        end = idxs[j + 1].start() if j + 1 < len(idxs) else len(text)
        cells.append(text[start:end].strip("\n"))
    return cells


def apply_notebook_patch(path: Path, patched_text: str, original_cells: list) -> bool:
    """Write repaired code cells back into the notebook JSON. True on success."""
    cells = parse_mirror(patched_text, len(original_cells))
    if cells is None:
        return False
    nb = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    k = 0
    for c in nb.get("cells", []):
        if c.get("cell_type") == "code" and k < len(cells):
            c["source"] = cells[k].splitlines(keepends=True) or []
            k += 1
    path.write_text(json.dumps(nb, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return True


@dataclass
class ProcessedRepo:
    files: list = field(default_factory=list)
    languages: dict = field(default_factory=dict)
    dependencies: dict = field(default_factory=lambda: {"requirements": [], "pyproject": []})
    skipped_count: int = 0


def collect_files(root: Path) -> ProcessedRepo:
    result = ProcessedRepo()
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        if any(part in settings.ignore_dirs for part in p.parts):
            result.skipped_count += 1
            continue
        ext = p.suffix.lower()
        if ext in settings.ignore_exts:
            result.skipped_count += 1
            continue
        if ext == ".ipynb":
            cells = notebook_cells(p)
            code_len = sum(len(c) for c in cells)
            if not cells or code_len > settings.max_file_size:
                result.skipped_count += 1
                continue
            rel = str(p.relative_to(root)).replace("\\", "/")
            result.files.append(
                SourceFile(path=p, rel_path=rel, language="Jupyter Notebook", size=code_len)
            )
            continue
        if ext not in TEXT_EXTS:
            result.skipped_count += 1
            continue
        size = p.stat().st_size
        if size > settings.max_file_size:
            result.skipped_count += 1
            continue
        rel = str(p.relative_to(root)).replace("\\", "/")
        result.files.append(
            SourceFile(path=p, rel_path=rel, language=LANG_BY_EXT.get(ext, "Other"), size=size)
        )
    result.languages = _count(result.files)
    result.dependencies = _extract_deps(root)
    return result


def _count(files) -> dict:
    counts: dict = {}
    for f in files:
        counts[f.language] = counts.get(f.language, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: -kv[1]))


def _extract_deps(root: Path) -> dict:
    deps = {"requirements": [], "pyproject": []}
    req = root / "requirements.txt"
    if req.is_file():
        for line in req.read_text(errors="ignore").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                deps["requirements"].append(line)
    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
        text = pyproject.read_text(errors="ignore")
        in_deps = False
        for line in text.splitlines():
            s = line.strip()
            if s.startswith("[") and s.endswith("]"):
                in_deps = s in ("[project.dependencies]", "[tool.poetry.dependencies]")
                continue
            if in_deps and s:
                deps["pyproject"].append(s.rstrip(","))
    return deps


def read_source(files, max_files: int) -> list:
    out = []
    for f in files[:max_files]:
        try:
            out.append({"path": f.rel_path, "content": f.path.read_text(errors="ignore")})
        except OSError:
            continue
    return out


def dumps(obj) -> str:
    return json.dumps(obj, default=str, indent=2)
