# 🛠️ AI Code Repair & Analysis Agent

Streamlit app that takes a repository, runs static analysis, explains findings with AI,
auto-generates repair patches, validates them with pytest, and exports a full report.

## Pipeline

```
Internet Repo / ZIP / Files / Pasted Code / Local Folder
   ↓  Repository Processing (file filtering · language detection · dependency extraction)
   ↓  Static Analysis (Python AST · ruff · bandit · OSV.dev vulnerability check)
   ↓  AI Code Intelligence (OpenRouter · free coding models · finding explanations)
   ↓  Automated Repair Agent (patch generation · unified diffs · limited retries)
   ↓  Validation (isolated temp-dir sandbox · pytest · regression check)
   ↓  Results Dashboard (findings · diffs · test results · Markdown/JSON export)
```

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

Set `OPENROUTER_API_KEY` in `.env` (copy keys from https://openrouter.ai/keys).
Optional overrides in `.env`: `OPENROUTER_MODEL=default:deepseek/deepseek-chat-v3-0324:free`.

Inputs accepted: public GitHub URL, ZIP upload, multi-file upload, pasted code, local folder.

## Deploy to Streamlit Cloud

1. Push this repo to **public GitHub** (`.env` is gitignored — never commit keys).
2. Go to https://share.streamlit.io → **Create app** → select the repo.
   - **Main file path:** `app.py`
3. In **App settings → Secrets**, add:

   ```toml
   OPENROUTER_API_KEY = "sk-or-v1-..."
   # optional
   OPENROUTER_MODEL = "deepseek/deepseek-chat-v3-0324:free"
   ```

   `core/config.py` reads these via `os.getenv`, and Streamlit Cloud injects secrets
   into environment variables automatically — no code changes needed.
4. Deploy. Dependency install uses `requirements.txt` (tooling runs via
   `python -m ruff` / `python -m bandit`, so it works inside the same env).

## Notes

- The validation engine uses a temp-dir subprocess (no Docker), so it works on
  Streamlit Cloud. GitHub cloning requires `git`, which is available in the
  Cloud runtime (ZIP/upload/paste inputs always work regardless).
- Secrets: `core/config.py` reads `os.environ` first, then `st.secrets`.
- Security: only the repo's temp copy is tested; no network installs during analysis;
  inputs (ZIP entries, uploaded paths) are sanitized against path traversal.
