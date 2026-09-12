"""
app.py — Co-Regulation Orchestration Dashboard
FastAPI backend serving authentic Moodle log replay data

Run:  uvicorn app:app --host 0.0.0.0 --port 8000 --reload
Open: http://localhost:8000
"""

import sqlite3, json
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

DB_PATH     = Path(__file__).parent / "data" / "sessions.db"
STATIC_PATH = Path(__file__).parent / "static"

app = FastAPI(
    title="Co-Regulation Orchestration Dashboard",
    description="Authentic Moodle log replay — PhD research prototype",
    version="1.0.0",
)

def get_db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


# ── Root → serve dashboard ──────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
def root():
    idx = STATIC_PATH / "index.html"
    if not idx.exists():
        raise HTTPException(404, "Frontend not found — ensure static/index.html exists")
    return HTMLResponse(idx.read_text())


# ── GET /api/stats ──────────────────────────────────────────────
@app.get("/api/stats")
def get_stats():
    con = get_db()
    cur = con.cursor()
    stats = {}
    stats["total_sessions"] = cur.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
    stats["total_windows"]  = cur.execute("SELECT COUNT(*) FROM windows").fetchone()[0]
    stats["total_sections"] = cur.execute("SELECT COUNT(DISTINCT sec) FROM sessions").fetchone()[0]
    stats["week_range"]     = cur.execute("SELECT MIN(week), MAX(week) FROM sessions").fetchone()
    stats["total_events"]   = cur.execute("SELECT SUM(total_events) FROM sessions").fetchone()[0]
    stats["total_users"]    = cur.execute("SELECT SUM(total_users) FROM sessions").fetchone()[0]
    action_rows = cur.execute(
        "SELECT action, COUNT(*) as n FROM windows GROUP BY action ORDER BY n DESC"
    ).fetchall()
    stats["action_distribution"] = [dict(r) for r in action_rows]
    con.close()
    return stats


# ── GET /api/sections ───────────────────────────────────────────
@app.get("/api/sections")
def get_sections():
    con = get_db()
    rows = con.execute(
        "SELECT sec, COUNT(*) as n_sessions, SUM(total_events) as total_events "
        "FROM sessions GROUP BY sec ORDER BY sec"
    ).fetchall()
    con.close()
    return [dict(r) for r in rows]


# ── GET /api/sessions ───────────────────────────────────────────
@app.get("/api/sessions")
def get_sessions(
    section: Optional[str] = Query(None, description="Filter by section, e.g. Sec-03"),
    week:    Optional[int]  = Query(None, description="Filter by semester week"),
    min_windows: int        = Query(5,    description="Minimum windows in session"),
):
    con = get_db()
    q   = "SELECT * FROM sessions WHERE n_windows >= ?"
    params = [min_windows]
    if section:
        q += " AND sec = ?"
        params.append(section)
    if week is not None:
        q += " AND week = ?"
        params.append(week)
    q += " ORDER BY sec, date_str, start_time"
    rows = con.execute(q, params).fetchall()
    con.close()
    return [dict(r) for r in rows]


# ── GET /api/sessions/{session_key} ────────────────────────────
@app.get("/api/sessions/{session_key}")
def get_session(session_key: str):
    con = get_db()
    sess = con.execute(
        "SELECT * FROM sessions WHERE session_key = ?", (session_key,)
    ).fetchone()
    if not sess:
        raise HTTPException(404, f"Session '{session_key}' not found")

    windows = con.execute(
        "SELECT * FROM windows WHERE session_key = ? ORDER BY window_idx",
        (session_key,)
    ).fetchall()
    con.close()

    sess_dict = dict(sess)
    wins_list = []
    for w in windows:
        wd = dict(w)
        wd["top_events"] = json.loads(wd.pop("top_events_json", "[]"))
        wins_list.append(wd)

    sess_dict["windows"] = wins_list
    return sess_dict


# ── GET /api/window/{session_key}/{window_idx} ──────────────────
@app.get("/api/window/{session_key}/{window_idx}")
def get_window(session_key: str, window_idx: int):
    """Fetch a single window — for step-through / live simulation"""
    con = get_db()
    row = con.execute(
        "SELECT * FROM windows WHERE session_key = ? AND window_idx = ?",
        (session_key, window_idx)
    ).fetchone()
    con.close()
    if not row:
        raise HTTPException(404, "Window not found")
    wd = dict(row)
    wd["top_events"] = json.loads(wd.pop("top_events_json", "[]"))
    return wd


# ── GET /api/search ─────────────────────────────────────────────
@app.get("/api/search")
def search_sessions(
    action: Optional[str] = Query(None, description="Filter by dominant action type"),
    min_events: int        = Query(0),
):
    """Find sessions containing a specific action type"""
    con = get_db()
    if action and action != "monitor":
        col_map = {
            "clarify_instruction": "n_clarify",
            "target_subgroup":     "n_target",
            "pacing_adjust":       "n_pacing",
            "whole_class_prompt":  "n_whole_class",
            "pause_and_reset":     "n_pause",
        }
        col = col_map.get(action)
        if col:
            rows = con.execute(
                f"SELECT * FROM sessions WHERE {col} > 0 AND total_events >= ? "
                f"ORDER BY {col} DESC LIMIT 50",
                (min_events,)
            ).fetchall()
        else:
            rows = []
    else:
        rows = con.execute(
            "SELECT * FROM sessions WHERE total_events >= ? ORDER BY total_events DESC LIMIT 50",
            (min_events,)
        ).fetchall()
    con.close()
    return [dict(r) for r in rows]


# ── Serve static files (CSS, JS if split later) ─────────────────
if STATIC_PATH.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_PATH)), name="static")
