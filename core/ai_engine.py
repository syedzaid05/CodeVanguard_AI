import os

import requests

from core.config import settings


class AIEngine:
    def __init__(self):
        self.api_key = settings.openrouter_api_key
        self.base_url = settings.openrouter_base_url
        self.model = settings.openrouter_model

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def chat(self, system: str, user: str, temperature: float = 0.1) -> str:
        if not self.enabled:
            raise RuntimeError("OPENROUTER_API_KEY is not set. Add it to .env.")
        resp = requests.post(
            f"{self.base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "HTTP-Referer": os.getenv("APP_URL", "http://localhost"),
                "X-Title": "AI Code Repair Agent",
            },
            json={
                "model": self.model,
                "temperature": temperature,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            },
            timeout=settings.request_timeout,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]

    def explain_findings(self, findings, context_files) -> list:
        out = []
        for f in findings[:12]:
            snippet = _find_snippet(context_files, f.file, f.line)
            user = (
                f"Explain this static-analysis finding and how to fix it, in max 6 sentences.\n"
                f"Tool: {f.tool}\nSeverity: {f.severity}\nFile: {f.file}:{f.line}\n"
                f"Issue: {f.message}\n\nCode near line {f.line}:\n{snippet}"
            )
            try:
                out.append({"finding": f, "explanation": self.chat(SYSTEM_PROMPT, user)})
            except (requests.RequestException, RuntimeError, KeyError, IndexError) as e:
                out.append({"finding": f, "explanation": f"(AI explanation unavailable: {e})"})
        return out

    def select_context_files(self, files, findings, limit: int = 6) -> list:
        flagged = {f.file for f in findings}
        py = [x for x in files if x.language == "Python"]
        scored = sorted(py, key=lambda x: (x.rel_path not in flagged, -x.size))
        picked = [(x.path, x.rel_path) for x in scored[:limit]]
        return [
            {"path": rel, "content": p.read_text(errors="ignore")}
            for p, rel in picked
        ]


SYSTEM_PROMPT = (
    "You are a senior static-analysis engineer. Explain code problems clearly and "
    "concisely, and suggest precise concrete fixes."
)

MAX_SNIPPET = 60


def _find_snippet(context_files, rel_path: str, line: int) -> str:
    for cf in context_files:
        if cf["path"] == rel_path:
            lines = cf["content"].splitlines()
            start = max(0, (line or 1) - 10)
            chunk = lines[start:start + MAX_SNIPPET]
            numbered = "\n".join(f"{start + i + 1}: {l}" for i, l in enumerate(chunk))
            return numbered[:6000]
    return "(file content not available)"
