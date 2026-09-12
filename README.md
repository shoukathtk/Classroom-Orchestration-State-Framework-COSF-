# Co-Regulation Orchestration Dashboard
### Intelligent Classroom Orchestration — PhD Research System
**Author:** PhD Candidate | **Supervisor:** [Name]
**Data:** Authentic Moodle LMS logs — 327,425 student events, Feb–Jun 2026

---

## What This System Is

A deployable web application that replays authentic classroom session data through
a real-time co-regulation monitoring dashboard. The system processes raw Moodle
LMS logs through the validated co-regulation pipeline (alignment aₜ, dispersion dₜ,
stability σₜ) and serves all sessions and windows via a REST API to a browser-based
orchestration dashboard for teacher use.

**Methodology note:** This system uses a log-replay evaluation design. Because
real-time LMS API access was not available during the study period — a common
institutional constraint in educational technology research — authentic historical
logs are replayed chronologically, providing evaluators with a functionally
equivalent experience to live deployment while maintaining full data authenticity.

---

## System Architecture

```
log_consol-s613050.csv
        │
        ▼  preprocess.py (run once)
  data/sessions.db ─── 772 sessions, 20,677 windows, 21 sections
        │
        ▼  app.py (FastAPI)
  REST API ────────────────────────────────────────────────────────
    GET /api/stats                → cohort overview
    GET /api/sections             → list of sections
    GET /api/sessions             → filterable session list
    GET /api/sessions/{key}       → full session + all windows
    GET /api/window/{key}/{idx}   → single window state
    GET /api/search?action=...    → sessions by action type
        │
        ▼  static/index.html (browser)
  Dashboard ───────────────────────────────────────────────────────
    • Section / week / action type filters
    • 772 sessions in sidebar
    • Live state gauges (A, D, S)
    • Action recommendation panel
    • Session timeline (Chart.js)
    • Step-through and replay controls
```

---

## Quick Start

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Preprocess the data (run once — takes ~2 min)
```bash
python3 preprocess.py --csv /path/to/log_consol-s613050.csv
```
This creates `data/sessions.db` (SQLite, ~15 MB).

### 3. Start the server
```bash
uvicorn app:app --host 0.0.0.0 --port 8000
```

### 4. Open the dashboard
```
http://localhost:8000
```

To share with evaluators on a local network:
```
http://<your-ip>:8000
```

To deploy publicly (e.g. on a university server):
```bash
uvicorn app:app --host 0.0.0.0 --port 8000 --workers 2
```
Or use a reverse proxy (nginx/Apache) in front of uvicorn.

---

## API Reference

| Endpoint | Parameters | Description |
|---|---|---|
| `GET /api/stats` | — | Cohort overview (session count, window count, action distribution) |
| `GET /api/sections` | — | All sections with session counts |
| `GET /api/sessions` | `section`, `week`, `min_windows` | Filterable session list |
| `GET /api/sessions/{key}` | — | Full session with all windows and window states |
| `GET /api/window/{key}/{idx}` | — | Single window state (for step-through) |
| `GET /api/search` | `action`, `min_events` | Sessions containing a specific action type |

---

## Co-Regulation Pipeline

All computations follow the validated framework from:
> [Author]. (2026). *A Trivariate Co-Regulation Framework for Classroom Orchestration*.
> IEEE Transactions on Learning Technologies (under review).

**Alignment:** aₜ = 0.5·R^event_t + 0.5·R^comp_t ∈ [0,1]

**Dispersion:** dₜ = Gini(c₁,…,cₖ) ∈ [0,1]

**Stability:** σₜ = max(0, 1 − |aₜ − aₜ₋₁| / κ), κ = 0.500

**Ordinal scaling:** 1–5 via linear mapping (0→1, 1→5)

**Action decision rules:** A/D thresholds as per validated 6-rater annotation study
(Chapter 4, ICC(A,1) = 0.848–0.866, Krippendorff α = 0.843–0.886)

---

## Files

```
dashboard/
├── app.py              ← FastAPI backend
├── preprocess.py       ← CSV → SQLite pipeline
├── requirements.txt    ← Python dependencies
├── README.md           ← This file
├── data/
│   └── sessions.db     ← SQLite database (generated)
└── static/
    └── index.html      ← Single-page dashboard frontend
```

---

## Evaluation Protocol

For the expert usability evaluation (Chapter 6), evaluators should:
1. Open the dashboard at the provided URL
2. Use section and week filters to navigate to a session of interest
3. Use the Replay button to step through the session chronologically
4. Rate each of the TAM dimensions (perceived usefulness, ease of use, action quality)
   using the evaluation questionnaire provided separately

Recommended sessions for demonstration:
- **Sec-03 Week 3** (01 Mar 2026) — Quiz session with clarify cascade
- **Sec-07 Week 3** (01 Mar 2026) — Session ending with target_subgroup detection
- **Sec-07 Week 17** (08 Jun 2026) — Long exam-period session (138 windows)

---

*PhD Research System — Intelligent Classroom Orchestration: A Machine Learning Framework
for Co-Regulation Modelling, Predictive Analytics, and Academic Performance Enhancement*
