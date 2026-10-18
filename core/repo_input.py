import shutil
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path


@dataclass
class RepoInfo:
    path: Path
    name: str
    source: str
    cleanup: bool = True


def load_repo_from_zip(zip_bytes: bytes) -> RepoInfo:
    tmp = Path(tempfile.mkdtemp(prefix="repo_"))
    zip_path = tmp / "upload.zip"
    zip_path.write_bytes(zip_bytes)
    extract_root = tmp / "src"
    extract_root.mkdir()
    with zipfile.ZipFile(zip_path) as zf:
        bad = [n for n in zf.namelist() if n.startswith("/") or ".." in Path(n).parts]
        if bad:
            raise ValueError(f"Unsafe zip entries: {bad[:3]}")
        zf.extractall(extract_root)
    return RepoInfo(path=_unwrap(extract_root), name="uploaded-repo", source="zip")


def clone_repo_from_url(url: str) -> RepoInfo:
    if not url.startswith(("https://github.com/", "https://gitlab.com/")):
        raise ValueError("Only public GitHub/GitLab HTTPS URLs are supported.")
    tmp = Path(tempfile.mkdtemp(prefix="repo_"))
    dest = tmp / "src"
    result = subprocess.run(
        ["git", "clone", "--depth", "1", url, str(dest)],
        check=False,
        capture_output=True,
        text=True,
        timeout=180,
    )
    if result.returncode != 0:
        shutil.rmtree(tmp, ignore_errors=True)
        raise RuntimeError(f"git clone failed: {result.stderr.strip()[:300]}")
    return RepoInfo(path=dest, name=_name_from_url(url), source=url)


def cleanup_repo(info: RepoInfo) -> None:
    if info.cleanup:
        shutil.rmtree(info.path.parent, ignore_errors=True)


def load_repo_from_paste(code: str, filename: str = "pasted_code.py") -> RepoInfo:
    if not code.strip():
        raise ValueError("Pasted code is empty.")
    tmp = Path(tempfile.mkdtemp(prefix="paste_"))
    root = tmp / "src"
    root.mkdir()
    target = root / _safe_name(filename or "pasted_code.py")
    target.write_text(code, encoding="utf-8")
    return RepoInfo(path=root, name=target.name, source="pasted code")


def load_repo_from_uploads(files, name_from=None) -> RepoInfo:
    if not files:
        raise ValueError("No files uploaded.")
    tmp = Path(tempfile.mkdtemp(prefix="files_"))
    root = tmp / "src"
    root.mkdir()
    for f in files:
        rel = _safe_rel(getattr(f, "name", "") or "file")
        dest = root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(f.getvalue())
    return RepoInfo(path=root, name=name_from or f"{len(files)} uploaded file(s)", source="upload")


def load_repo_from_folder(folder: str) -> RepoInfo:
    p = Path(folder).expanduser()
    if not p.is_dir():
        raise ValueError(f"Not a directory: {folder}")
    return RepoInfo(path=p, name=p.name, source=f"local folder {folder}", cleanup=False)


def _safe_name(name: str) -> str:
    return Path(name).name.replace("\\", "/").replace("/", "_")


def _safe_rel(rel: str) -> str:
    parts = [p for p in Path(rel.replace("\\", "/")).parts if p not in ("..", "", ".")]
    return "/".join(parts) or "file"


def _unwrap(root: Path) -> Path:
    children = [c for c in root.iterdir() if c.name != "upload.zip"]
    if len(children) == 1 and children[0].is_dir():
        return children[0]
    return root


def _name_from_url(url: str) -> str:
    name = url.rstrip("/").split("/")[-1]
    name = name.removesuffix(".git")
    return name or "repo"
