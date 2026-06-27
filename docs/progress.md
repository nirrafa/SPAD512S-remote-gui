# Progress Log

> **Update this file at the end of every work session.** Each entry records what was done, what was decided, what blocked, and what comes next. This is the single source of truth for project status.

**References:** [Plan](plan.md) · [PRD](PRD.md) · [Constraints](constraints.md) · [Learnings](learnings.md)

---

## Status summary

| Phase | Description | Status | Tests passing |
|---|---|---|---|
| 0 | Project setup & tooling | ✅ Done | gate ✓ |
| 1 | Mock vendor server | Not started | 0 / 19 |
| 2 | Bridge core | Not started | 0 / 19 |
| 3 | Intensity mode (vertical slice) | Not started | 0 / 16 |
| 4 | Gated time-resolved mode | Not started | 0 / 12 |
| 5 | FLIM mode | Not started | 0 / 9 |
| 6 | Raw 1-bit single-photon | Not started | 0 / 5 |
| 7 | Calibration system | Not started | 0 / 13 |
| 8 | Safety, health & auto-protect | Not started | 0 / 17 |
| 9 | Sweeps, scheduling & resilience | Not started | 0 / 18 |
| 10 | Data handling & reducer | Not started | 0 / 18 |
| 11 | Front-end visualization | Not started | 0 / 12 |
| 12 | Experiment log & presets | Not started | 0 / 16 |
| 13 | Integration & hardware bring-up | Not started | 0 / 11 |
| **Total** | | | **0 / 185** |

---

## Session log

### Template

Copy this block for each new entry. Most recent session goes on top.

```
### YYYY-MM-DD — Session title

**Phase(s):** #
**Duration:** ~Xh
**Who:** name

#### Done
- bullet points of completed work

#### Decisions made
- any choices made and why (also add to plan.md decisions log)

#### Bugs / issues encountered
- description → resolution (also add to learnings.md if non-trivial)

#### Blocked on
- anything that prevents further progress

#### Next session
- what to pick up next
```

---

<!-- Add new entries below this line, most recent first -->

### 2026-06-27 — Phase 0: project setup & tooling

**Phase(s):** 0
**Duration:** ~1h
**Who:** Nir + Claude

#### Done
- Initialized git repo; created public GitHub repo [nirrafa/SPAD512S-remote-gui](https://github.com/nirrafa/SPAD512S-remote-gui) and pushed initial commit (docs, pre-dev tests, reference code).
- Installed Homebrew + `gh` CLI on the host; authenticated as `nirrafa`.
- Created Python bridge package skeleton: `bridge/{__init__,main,config}.py`, `py.typed`. FastAPI app with `GET /api/health` and CORS.
- `pyproject.toml` with runtime deps (FastAPI, uvicorn, pydantic, pydantic-settings, numpy, websockets) and dev extras (pytest, pytest-asyncio, httpx, ruff, mypy). Configured pytest (asyncio auto), ruff, mypy (strict).
- `mock_server/` and `tests/` skeletons; bridge smoke test (`tests/test_health.py`).
- Scaffolded `frontend/` (Vite React-TS): added `strict: true` + `noUncheckedIndexedAccess`, dev proxy for `/api` + `/ws`, vitest + Testing Library, Prettier. Replaced demo App with bridge-health shell + smoke test.
- Created `README.md` and root `.gitignore`.

#### Decisions made
- Python 3.11 over system 3.9; Vite default template (React 19 / oxlint / vitest); pydantic-settings with `SPAD_` env prefix. (See plan.md decisions log.)

#### Bugs / issues encountered
- Homebrew install needs interactive sudo → user ran it manually; same for `gh auth login`. Non-blocking.
- ruff flagged import order in `tests/conftest.py` → auto-fixed.

#### Blocked on
- Nothing.

#### Next session
- Phase 1: mock vendor server. Study `theoretical_info/piimaging_examples/cSPAD.py` + streaming examples, then implement the asyncio TCP server and pass `test_14_mock_vendor_server.py` (19 tests).
