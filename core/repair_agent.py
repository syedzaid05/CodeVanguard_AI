import difflib
from dataclasses import dataclass, field

from core.ai_engine import AIEngine

REPAIR_SYSTEM = (
    "You are an automated code repair agent. You will receive one source file and a "
    "list of issues. Rewrite the file fixing ONLY the listed issues, preserving all "
    "other behavior and formatting as much as possible. Respond with a fenced code "
    "block containing the complete fixed file and nothing else."
)


@dataclass
class RepairAttempt:
    file: str
    diff: str
    original: str
    patched: str
    note: str = ""


@dataclass
class RepairResult:
    attempts: list = field(default_factory=list)
    applied: list = field(default_factory=list)
    failed: list = field(default_factory=list)


def generate_repair(ai: AIEngine, file_path, lines: list, findings) -> tuple[str | None, str | None]:
    issue_text = "\n".join(f"[{f.tool}/{f.severity}] line {f.line}: {f.message}" for f in findings)
    user = f"File: {file_path.rel_path}\n\nIssues:\n{issue_text}\n\nFile content:\n```python\n{''.join(lines)}```"
    try:
        reply = ai.chat(REPAIR_SYSTEM, user, temperature=0.0)
    except Exception as e:
        return None, f"AI request failed: {e}"
    return _extract_code(reply), None


def extract_unified_diff(original: str, patched: str, rel_path: str) -> str:
    diff = difflib.unified_diff(
        original.splitlines(keepends=True),
        patched.splitlines(keepends=True),
        fromfile=f"a/{rel_path}",
        tofile=f"b/{rel_path}",
    )
    return "".join(diff)


def apply_patch(file_path, patched: str) -> None:
    file_path.path.write_text(patched, encoding="utf-8")


def _extract_code(reply: str):
    reply = reply.strip()
    if "```" in reply:
        blocks = reply.split("```")
        for block in blocks[1::2]:
            body = block.split("\n", 1)[1] if "\n" in block else block
            if body.strip():
                return body.strip() + "\n"
        return None
    return None
