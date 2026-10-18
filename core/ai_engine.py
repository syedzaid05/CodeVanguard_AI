import os

import requests

from core.config import settings


class AIEngine:
    def __init__(self):
        self.api_key = settings.openrouter_api_key
        self.base_url = settings.openrouter_base_url
        self.model = settings.openrouter_model
        self.fallbacks = []
        if settings.groq_api_key:
            self.fallbacks.append(("Groq", settings.groq_base_url, settings.groq_model, settings.groq_api_key))
        if settings.gemini_api_key:
            self.fallbacks.append(("Gemini", settings.gemini_base_url, settings.gemini_model, settings.gemini_api_key))

    @property
    def enabled(self) -> bool:
        return bool(self.api_key) or bool(self.fallbacks)

    def chat(self, system: str, user: str, temperature: float = 0.1, max_tokens: int = 1400) -> str:
        if not self.enabled:
            raise RuntimeError("No API key set. Add OPENROUTER_API_KEY, GROQ_API_KEY or GOOGLE_GEMINI_API_KEY to .env.")
        openrouter = [("OpenRouter", self.base_url, self.model, self.api_key)] if self.api_key else []
        # Fast providers first: Groq/Gemini typically respond in seconds,
        # OpenRouter free models can take minutes.
        providers = list(self.fallbacks) + openrouter
        errors = []
        for name, base_url, model, api_key in providers:
            try:
                return self._post(base_url, model, api_key, system, user, temperature, max_tokens)
            except (requests.RequestException, KeyError, IndexError, ValueError) as e:
                errors.append(f"{name}: {e}")
        raise RuntimeError("All providers failed -> " + " | ".join(errors))

    def _post(self, base_url: str, model: str, api_key: str, system: str, user: str, temperature: float, max_tokens: int = 1400) -> str:
        if base_url == settings.gemini_base_url:
            url = f"{base_url}/models/{model}:generateContent"
            headers = {"x-goog-api-key": api_key}
            payload = {
                "systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": user}]}],
                "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens},
            }
        else:
            url = f"{base_url}/chat/completions"
            headers = {
                "Authorization": f"Bearer {api_key}",
                "HTTP-Referer": os.getenv("APP_URL", "http://localhost"),
                "X-Title": "AI Code Repair Agent",
            }
            payload = {
                "model": model,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            }
        resp = requests.post(url, headers=headers, json=payload, timeout=settings.request_timeout)
        resp.raise_for_status()
        data = resp.json()
        if base_url == settings.gemini_base_url:
            return data["candidates"][0]["content"]["parts"][0]["text"]
        return data["choices"][0]["message"]["content"]

    def explain_findings(self, findings, context_files, progress_callback=None) -> list:
        out = []
        targets = findings[:10]
        for i, f in enumerate(targets):
            if progress_callback:
                progress_callback(i + 1, len(targets), f)
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
            if progress_callback:
                progress_callback(-1, len(targets), f)  # -1 signals completion of this item
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
