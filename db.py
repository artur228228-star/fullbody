"""SQLite-хранилище: настройки пользователя, журнал подходов, кеш file_id медиа."""
from __future__ import annotations

import datetime as dt
import sqlite3
import threading
from pathlib import Path
from typing import Dict, List, Optional, Tuple

DB_PATH = Path(__file__).parent / "data" / "gymbot.sqlite3"
DB_PATH.parent.mkdir(exist_ok=True)

_lock = threading.Lock()
_conn = sqlite3.connect(DB_PATH, check_same_thread=False)
_conn.row_factory = sqlite3.Row

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id    INTEGER PRIMARY KEY,
    name       TEXT,
    rest_sec   INTEGER DEFAULT 90,
    media_mode TEXT DEFAULT 'gif',
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS sets_log (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id   INTEGER,
    date      TEXT,
    exercise  TEXT,
    set_no    INTEGER,
    weight    REAL,
    reps      INTEGER
);
CREATE TABLE IF NOT EXISTS workouts (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id   INTEGER,
    date      TEXT,
    mode      TEXT,
    exercises INTEGER,
    sets      INTEGER,
    volume    REAL
);
CREATE TABLE IF NOT EXISTS media_cache (
    key     TEXT PRIMARY KEY,   -- '<exercise_key>:<gif|card>'
    file_id TEXT
);
"""
with _lock:
    _conn.executescript(SCHEMA)
    _conn.commit()


def _run(sql: str, params: Tuple = ()) -> None:
    with _lock:
        _conn.execute(sql, params)
        _conn.commit()


def _rows(sql: str, params: Tuple = ()) -> List[sqlite3.Row]:
    with _lock:
        return _conn.execute(sql, params).fetchall()


# ---------- пользователи ----------
def ensure_user(user_id: int, name: str) -> None:
    _run("INSERT OR IGNORE INTO users(user_id, name, created_at) VALUES(?,?,?)",
         (user_id, name, dt.datetime.now().isoformat(timespec="seconds")))


def get_user(user_id: int) -> Dict:
    r = _rows("SELECT * FROM users WHERE user_id=?", (user_id,))
    return dict(r[0]) if r else {"rest_sec": 90, "media_mode": "gif"}


def set_rest(user_id: int, sec: int) -> None:
    _run("UPDATE users SET rest_sec=? WHERE user_id=?", (sec, user_id))


def set_media_mode(user_id: int, mode: str) -> None:
    _run("UPDATE users SET media_mode=? WHERE user_id=?", (mode, user_id))


# ---------- журнал ----------
def log_set(user_id: int, exercise: str, set_no: int, weight: float, reps: int) -> None:
    _run("INSERT INTO sets_log(user_id,date,exercise,set_no,weight,reps) VALUES(?,?,?,?,?,?)",
         (user_id, dt.date.today().isoformat(), exercise, set_no, weight, reps))


def finish_workout(user_id: int, mode: str, exercises: int, sets: int, volume: float) -> None:
    _run("INSERT INTO workouts(user_id,date,mode,exercises,sets,volume) VALUES(?,?,?,?,?,?)",
         (user_id, dt.date.today().isoformat(), mode, exercises, sets, volume))


def last_result(user_id: int, exercise: str) -> Optional[Tuple[float, int]]:
    """Лучший подход (вес × повторы) в прошлой тренировке по этому упражнению."""
    r = _rows("""SELECT weight, reps FROM sets_log WHERE user_id=? AND exercise=?
                 AND date < date('now') ORDER BY date DESC, weight DESC, reps DESC LIMIT 1""",
              (user_id, exercise))
    return (r[0]["weight"], r[0]["reps"]) if r else None


def personal_records(user_id: int) -> List[Tuple[str, float, int]]:
    r = _rows("""SELECT exercise, MAX(weight) AS w, reps FROM sets_log
                 WHERE user_id=? AND weight > 0 GROUP BY exercise ORDER BY w DESC""", (user_id,))
    return [(x["exercise"], x["w"], x["reps"]) for x in r]


def stats(user_id: int) -> Dict:
    w = _rows("SELECT COUNT(*) c, COALESCE(SUM(volume),0) v, COALESCE(SUM(sets),0) s "
              "FROM workouts WHERE user_id=?", (user_id,))[0]
    week = _rows("SELECT COUNT(*) c FROM workouts WHERE user_id=? AND date >= date('now','-6 days')",
                 (user_id,))[0]["c"]
    last = _rows("SELECT date, mode, exercises, sets, volume FROM workouts WHERE user_id=? "
                 "ORDER BY id DESC LIMIT 5", (user_id,))
    return {"total": w["c"], "volume": w["v"], "sets": w["s"], "week": week, "last": [dict(x) for x in last]}


# ---------- кеш медиа ----------
def get_file_id(key: str) -> Optional[str]:
    r = _rows("SELECT file_id FROM media_cache WHERE key=?", (key,))
    return r[0]["file_id"] if r else None


def put_file_id(key: str, file_id: str) -> None:
    _run("INSERT OR REPLACE INTO media_cache(key,file_id) VALUES(?,?)", (key, file_id))
