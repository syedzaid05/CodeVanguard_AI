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
}

TEXT_EXTS = set(LANG_BY_EXT) | {".txt", ".cfg", ".ini", ".env.example", ".lock", ".csv"}


@dataclass
class SourceFile:
    path: Path
    rel_path: str
    language: str
    size: int


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
