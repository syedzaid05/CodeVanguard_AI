# 🛠️ CodeGuardAI — AI Code Repair & Analysis Agent

CodeGuardAI is a Streamlit application that takes any repository (GitHub URL, ZIP,
uploaded files, pasted code, or a local folder), runs a full static-analysis pipeline,
uses LLMs to explain and **automatically repair** the problems, validates the patches,
and exports a complete engineering report.

```
   ┌─────────────┐   ┌──────────────┐   ┌───────────────┐   ┌──────────────┐
   │  1 · INPUT   │ → │ 2 · FINDINGS │ → │ 3 · AI BRAINS │ → │ 4 · REPAIRS  │
   └─────────────┘   └──────────────┘   └───────────────┘   └──────────────┘
        GitHub/ZIP/        ruff · bandit       OpenRouter ·          full-file
        files/paste/       AST · OSV.dev       Groq · Gemini         unified diffs
        local folder                           fallback chain
   ┌─────────────┐   ┌──────────────┐
   │ 5 · VALIDATE │ → │ 6 · EXPORT   │
   └─────────────┘   └──────────────┘
      pytest sandbox ·     MD · JSON · CSV ·
      smoke compile check  combined .patch · live report
```

---

## What it does, stage by stage

### 1 · Repository Input
Five ways to load code: **public GitHub URL**, **ZIP upload**, **multi-file upload**,
**pasted code**, or a **local folder path**. Repository processing filters out binaries/vendored
dirs, detects languages, parses dependencies (`requirements.txt`, `pyproject.toml`), and
sanitizes paths against traversal attacks.

### 2 · Static Analysis
| Engine | Detects |
|---|---|
| **Python AST** | syntax errors before any tooling runs |
| **ruff** | lint/quality issues (unused imports, sorting, unsafe patterns …) |
| **bandit** | security smells (`exec`, `shell=True`, weak crypto …) |
| **OSV.dev** | known CVEs in your declared dependencies |

**Jupyter notebooks are first-class**: `.ipynb` code cells are extracted into a virtual
Python mirror (with `# %% [cell N]` markers) so all analyzers work on notebook code too.
Findings carry the notebook filename and, where useful, the originating cell.

### 3 · AI Intelligence
Findings are sent to an LLM with surrounding code context and explained in plain English
("what it is, why it matters, concrete fix"). One click runs the top findings.

**Multi-provider fallback chain** — the app is resilient to provider flakiness:

```
Groq (llama / gpt-oss) → Gemini (2.5/3.x flash) → OpenRouter (free coding models)
```

Provider order favors fastest response; timeouts fail over automatically, so a hung
or rate-limited provider can never freeze the UI.

### 4 · Automated Repair
For each Python file (or notebook), all its findings are bundled into one prompt and the
model returns a **rewritten file**, which is:

1. syntax-checked with `ast.parse` (up to 3 retry attempts),
2. diffed into a **unified diff** display,
3. written back to disk — notebooks get their code cells rewritten in place,
   preserving markdown cells, outputs, and metadata.

Token budgets scale with file size so whole files round-trip intact.

### 5 · Validation
- **Repos with tests** → pytest runs in an isolated temp-dir sandbox (`-x -q`,
  no cacheprovider, network untouched).
- **Repos without tests** → a **smoke validation** compiles every `.py` file *and* every
  notebook code cell; failures are reported per file/cell with line numbers.

### 6 · Export
One-click artifacts from the Export tab:

| Artifact | Contents |
|---|---|
| 📄 `repair_report.md` | full Markdown report (findings, AI explanations, diffs, validation) |
| 🧾 `repair_report.json` | machine-readable equivalent |
| 📊 `findings.csv` | flat findings table (Tool / Severity / File / Line / Message) |
| 🩹 `patches.patch` | combined unified diff of *all* applied patches — `git apply`-ready |

---

## Project structure

```
app.py                     Streamlit UI (6 tabs, pipeline state, styling)
core/
  config.py                Settings; reads .env then st.secrets
  repo_input.py            clone/zip/files/paste/folder loading + cleanup
  repo_processing.py       file collection · languages · deps · notebook mirrors
  static_analysis.py       AST + ruff + bandit + OSV checks, notebook-aware
  ai_engine.py             multi-provider LLM fallback engine
  repair_agent.py          repair prompts, diffing, patch application
  validation.py            pytest sandbox + compile smoke check
  report.py                report generation & export artifacts
.env                       OPENROUTER_API_KEY etc. (gitignored)
```

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

Create `.env` (any one key enables AI; all three are tried in fallback order if present):

```env
GROQ_API_KEY="gsk_..."          # fastest, used first
GOOGLE_GEMINI_API_KEY="AI..."   # optional
OPENROUTER_API_KEY="sk-or-v1-..."  # optional

# optional model overrides
GROQ_MODEL="openai/gpt-oss-120b"
GEMINI_MODEL="gemini-3.8-flash"
OPENROUTER_MODEL="nvidia/nemotron-3.5-lightning:free"
```

## Deploy to Streamlit Cloud

1. Push to **public GitHub** — `.env` is gitignored, never commit keys.
2. https://share.streamlit.io → **Create app** → select repo/branch → main file path `app.py`.
3. In the deploy dialog, expand **Advanced settings** and set **Python version to 3.11**
   (3.12 also works; avoid 3.13+).
4. **App settings → Secrets** (paste only the providers you have):

   ```toml
   GROQ_API_KEY = "gsk_..."
   OPENROUTER_API_KEY = "sk-or-v1-..."
   GOOGLE_GEMINI_API_KEY = "AI..."
   ```

5. Deploy — `core/config.py` reads `os.environ` first, then `st.secrets`; tooling runs
   via `python -m ruff` / `python -m bandit` inside the same env, and `git` is
   pre-installed on Cloud, so it works out of the box.

Online after deploy: https://share.streamlit.io/app/<your-username>/<repo-name/main/app.py> — restart clicks in
**Manage app** fix any cold-start hiccups.

## Notes

- **Validation sandbox**: a temp-dir subprocess (no Docker) — safe for Cloud. Only the
  repo's temp copy is tested.
- **Repair targets only Python code** (plain `.py` files and notebook code cells).
- **Patch behavior**: patches are applied in place to the loaded repo copy; use the
  sidebar 🧹 button to reset the session.
- **Security**: no network installs during analysis; uploaded paths sanitized against
  path traversal; API keys stay in `.env`/secrets.
