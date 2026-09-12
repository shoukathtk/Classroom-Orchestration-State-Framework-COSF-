"""
preprocess.py — One-time data pipeline
Reads raw Moodle log CSV → computes co-regulation states → stores in SQLite
Run once: python3 preprocess.py --csv path/to/log_consol-s613050.csv
"""
import sqlite3, json, argparse, sys
import pandas as pd
import numpy as np
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "sessions.db"
KAPPA   = 0.500

def gini(counts):
    c = np.sort(np.array(counts, dtype=float))
    K = len(c)
    if K <= 1 or c.sum() == 0: return 0.0
    return (2 * np.sum(np.arange(1, K+1) * c)) / (K * c.sum()) - (K+1)/K

def sc_a(v): return max(1, min(5, round(1 + v * 4)))
def sc_d(v): return max(1, min(5, round(1 + v * 4)))
def sc_s(v): return max(1, min(5, round(v * 4 + 1)))

def get_action(a, d):
    if a == 5: return "monitor"
    if a == 4 and d <= 3: return "monitor"
    if a == 3 and d <= 2: return "monitor"
    if a == 3 and d <= 4: return "clarify_instruction"
    if a == 3: return "pacing_adjust"
    if a == 2 and d <= 2: return "target_subgroup"
    if a == 2 and d == 3: return "clarify_instruction"
    if a == 2 and d >= 4: return "whole_class_prompt"
    if a == 1: return "pause_and_reset"
    return "monitor"

def build_db(csv_path: str):
    print(f"Loading {csv_path} ...")
    df = pd.read_csv(csv_path, encoding="latin1", low_memory=False)
    df = df.drop(columns=["x"], errors="ignore")
    df["Sec"] = df["Sec"].replace({"Sec-06-Spring 26, Sec-08": "Sec-08"})
    df["Date_parsed"] = pd.to_datetime(df["Date"], format="%d-%b-%y", errors="coerce")
    df["Timestamp"]   = pd.to_datetime(
        df["Date_parsed"].astype(str) + " " + df["Time"], errors="coerce")
    df = df[
        (df["Date_parsed"] >= "2026-02-01") &
        (df["Date_parsed"] <= "2026-06-30") &
        (df["Role"] == "Student")
    ].copy()
    df = df.sort_values(["Sec", "Timestamp"]).reset_index(drop=True)
    print(f"  Student events in window: {len(df):,}")

    COURSE_START = pd.Timestamp("2026-02-15")
    df["sec_gap"]  = df.groupby("Sec")["Timestamp"].diff().dt.total_seconds() / 60
    df["new_sess"] = df["sec_gap"].isna() | (df["sec_gap"] > 30)
    df["sess_id"]  = df.groupby("Sec")["new_sess"].cumsum()
    df["sess_key"] = df["Sec"] + "_S" + df["sess_id"].astype(str)

    ss = df.groupby("sess_key")["Timestamp"].transform("min")
    df["elapsed"]  = (df["Timestamp"] - ss).dt.total_seconds()
    df["win_idx"]  = (df["elapsed"] // 60).astype(int)
    df["week"]     = ((df["Date_parsed"] - COURSE_START).dt.days // 7) + 1
    df["date_str"] = df["Date_parsed"].dt.strftime("%d %b %Y")

    DB_PATH.parent.mkdir(exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()

    cur.executescript("""
    DROP TABLE IF EXISTS sessions;
    DROP TABLE IF EXISTS windows;

    CREATE TABLE sessions (
        session_key   TEXT PRIMARY KEY,
        sec           TEXT,
        session_num   INTEGER,
        date_str      TEXT,
        week          INTEGER,
        start_time    TEXT,
        end_time      TEXT,
        total_events  INTEGER,
        total_users   INTEGER,
        n_windows     INTEGER,
        dominant_event TEXT,
        n_monitor     INTEGER,
        n_clarify     INTEGER,
        n_target      INTEGER,
        n_pacing      INTEGER,
        n_whole_class INTEGER,
        n_pause       INTEGER
    );

    CREATE TABLE windows (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        session_key     TEXT,
        window_idx      INTEGER,
        time_str        TEXT,
        n_events        INTEGER,
        n_users         INTEGER,
        A               INTEGER,
        D               INTEGER,
        S               INTEGER,
        a_cont          REAL,
        d_cont          REAL,
        sigma           REAL,
        dominant_event  TEXT,
        dominant_comp   TEXT,
        K_event_types   INTEGER,
        action          TEXT,
        top_events_json TEXT,
        FOREIGN KEY (session_key) REFERENCES sessions(session_key)
    );

    CREATE INDEX idx_windows_sess ON windows(session_key);
    CREATE INDEX idx_sessions_sec  ON sessions(sec);
    CREATE INDEX idx_sessions_week ON sessions(week);
    """)

    total_sessions = 0
    total_windows  = 0
    sess_rows  = []
    win_rows   = []

    for skey, sg in df.groupby("sess_key", sort=False):
        win_groups = list(sg.groupby("win_idx"))
        n_wins = len([wg for _, wg in win_groups if len(wg) >= 2])
        if n_wins < 5:
            continue

        sec        = sg["Sec"].iloc[0]
        sess_num   = int(sg["sess_id"].iloc[0])
        date_str   = sg["date_str"].iloc[0]
        week       = int(sg["week"].iloc[0])
        start_time = sg["Timestamp"].min().strftime("%H:%M")
        end_time   = sg["Timestamp"].max().strftime("%H:%M")
        total_ev   = len(sg)
        total_us   = sg["Stu ID"].nunique()
        dom_event  = sg["Event name"].value_counts().index[0]

        action_counts = {
            "monitor": 0, "clarify_instruction": 0,
            "target_subgroup": 0, "pacing_adjust": 0,
            "whole_class_prompt": 0, "pause_and_reset": 0
        }

        prev_a = None
        for widx, wg in win_groups:
            if len(wg) < 2:
                continue
            n     = len(wg)
            ec    = wg["Event name"].value_counts()
            cc    = wg["Component"].value_counts()
            R_ev  = ec.iloc[0] / n
            R_cp  = cc.iloc[0] / n
            a_c   = 0.5 * R_ev + 0.5 * R_cp
            d_c   = gini(ec.values)
            sigma = 1.0 if prev_a is None else max(0, 1 - abs(a_c - prev_a) / KAPPA)
            prev_a = a_c
            A = sc_a(a_c); D = sc_d(d_c); S = sc_s(sigma)
            act = get_action(A, D)
            action_counts[act] = action_counts.get(act, 0) + 1

            ts_str = (sg["Timestamp"].min() +
                      pd.Timedelta(minutes=int(widx))).strftime("%H:%M")
            top_ev = [{"n": k[:40], "c": int(v)}
                      for k, v in ec.head(4).items()]

            win_rows.append((
                skey, int(widx), ts_str, int(n),
                int(wg["Stu ID"].nunique()),
                A, D, S,
                round(float(a_c), 3), round(float(d_c), 3),
                round(float(sigma), 3),
                str(ec.index[0])[:50], str(cc.index[0])[:30],
                int(len(ec)), act,
                json.dumps(top_ev)
            ))
            total_windows += 1

        n_wins_actual = len([w for w in win_rows if w[0] == skey])
        sess_rows.append((
            skey, sec, sess_num, date_str, week,
            start_time, end_time, int(total_ev), int(total_us),
            n_wins_actual, str(dom_event)[:50],
            action_counts["monitor"],
            action_counts["clarify_instruction"],
            action_counts["target_subgroup"],
            action_counts["pacing_adjust"],
            action_counts["whole_class_prompt"],
            action_counts["pause_and_reset"],
        ))
        total_sessions += 1

        if total_sessions % 50 == 0:
            print(f"  Processed {total_sessions} sessions, {total_windows} windows...")

    cur.executemany(
        "INSERT INTO sessions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        sess_rows)
    cur.executemany(
        "INSERT INTO windows VALUES (NULL,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        win_rows)
    con.commit()
    con.close()
    print(f"\nDone. {total_sessions} sessions, {total_windows} windows → {DB_PATH}")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True, help="Path to Moodle log CSV")
    args = ap.parse_args()
    build_db(args.csv)
