# Learnings

## 2026-11-05 - Initial full scan (refresh mode)
- Trigger: "no KB exists" refresh from engineer agent.
- What worked: small codebase; reading every file in app/ directly was fastest. README documents tools, env vars and limits, cross-checked against code.
- What went wrong / was missing: tests, `.ai/plans`, `.vscode`, `uv.lock`, `requirements.txt` not read. `docs/kb/` needed creating via shell (create tool needs existing parents). Project lessons L-001 (verify write capability) satisfied: files written and listed.
- Lesson: for this repo, start from `app/server.py` and README; ignore `.venv` and `__pycache__`; read tests next if test behavior is asked.
- KB files changed: all (initial creation).
- Confidence: high for app code, low for tests/infra.
