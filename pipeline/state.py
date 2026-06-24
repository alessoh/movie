"""Session and job state store.

In-memory by default, with an optional SQLite mirror so job state can survive
a process restart at this prototype scale.  The store is the single source of
truth the orchestrator updates and the API reads for progress reporting.
"""
from __future__ import annotations

import secrets
import sqlite3
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from config import BASE_DIR, settings

_DB_PATH = BASE_DIR / "storage" / "state.db"


# Ordered phases used for both progress percentage and human messages.
PHASES = [
    ("queued", "Waiting to start"),
    ("reading", "Reading your novel"),
    ("shaping", "Shaping a two-minute story"),
    ("planning", "Planning the shots"),
    ("designing", "Designing your characters"),
    ("filming", "Filming the shots"),
    ("narrating", "Recording the narration"),
    ("scoring", "Scoring the music"),
    ("final_cut", "Final cut"),
    ("ready", "Ready"),
    ("error", "Something went wrong"),
]
_PHASE_ORDER = {name: i for i, (name, _) in enumerate(PHASES)}


@dataclass
class Session:
    token: str
    upload_path: str = ""
    work_dir: str = ""
    status: str = "queued"  # phase name
    progress: int = 0  # 0..100
    messages: List[str] = field(default_factory=list)
    movie_path: Optional[str] = None
    error: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    movies_made: int = 0  # quota counter
    options: dict = field(default_factory=dict)  # per-job control overrides

    def public_dict(self) -> dict:
        """Client-safe view of the session (never includes file system internals
        beyond what the frontend needs)."""
        phase_label = dict(PHASES).get(self.status, self.status)
        return {
            "token": self.token,
            "status": self.status,
            "phase_label": phase_label,
            "progress": self.progress,
            "messages": self.messages[-25:],
            "ready": self.status == "ready" and bool(self.movie_path),
            "error": self.error,
        }


class StateStore:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._sessions: Dict[str, Session] = {}
        self._init_db()

    # --- SQLite (optional persistence) ------------------------------------
    def _init_db(self) -> None:
        try:
            con = sqlite3.connect(_DB_PATH)
            con.execute(
                """CREATE TABLE IF NOT EXISTS sessions (
                    token TEXT PRIMARY KEY,
                    upload_path TEXT,
                    work_dir TEXT,
                    status TEXT,
                    progress INTEGER,
                    messages TEXT,
                    movie_path TEXT,
                    error TEXT,
                    created_at REAL,
                    movies_made INTEGER
                )"""
            )
            con.commit()
            con.close()
        except Exception:
            # Persistence is best-effort; the in-memory store still works.
            pass

    def _persist(self, s: Session) -> None:
        try:
            con = sqlite3.connect(_DB_PATH)
            con.execute(
                """INSERT OR REPLACE INTO sessions
                   (token, upload_path, work_dir, status, progress, messages,
                    movie_path, error, created_at, movies_made)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (
                    s.token,
                    s.upload_path,
                    s.work_dir,
                    s.status,
                    s.progress,
                    "\n".join(s.messages),
                    s.movie_path,
                    s.error,
                    s.created_at,
                    s.movies_made,
                ),
            )
            con.commit()
            con.close()
        except Exception:
            pass

    # --- public API -------------------------------------------------------
    def create(self) -> Session:
        token = secrets.token_urlsafe(16)
        work_dir = settings_storage_dir() / token
        work_dir.mkdir(parents=True, exist_ok=True)
        s = Session(token=token, work_dir=str(work_dir))
        with self._lock:
            self._sessions[token] = s
            self._persist(s)
        return s

    def get(self, token: str) -> Optional[Session]:
        with self._lock:
            return self._sessions.get(token)

    def all(self) -> List[Session]:
        with self._lock:
            return list(self._sessions.values())

    def delete(self, token: str) -> None:
        with self._lock:
            self._sessions.pop(token, None)
        try:
            con = sqlite3.connect(_DB_PATH)
            con.execute("DELETE FROM sessions WHERE token=?", (token,))
            con.commit()
            con.close()
        except Exception:
            pass

    def set_phase(self, token: str, phase: str, message: str, progress: Optional[int] = None) -> None:
        with self._lock:
            s = self._sessions.get(token)
            if not s:
                return
            s.status = phase
            if progress is None:
                idx = _PHASE_ORDER.get(phase, 0)
                # Map phase index across the working range 5..95.
                span = max(1, len(PHASES) - 2)
                progress = int(5 + (idx / span) * 90)
            s.progress = max(0, min(100, progress))
            if message:
                s.messages.append(message)
                self._write_log(s, message)
            self._persist(s)

    def add_message(self, token: str, message: str, progress: Optional[int] = None) -> None:
        with self._lock:
            s = self._sessions.get(token)
            if not s:
                return
            s.messages.append(message)
            self._write_log(s, message)
            if progress is not None:
                s.progress = max(0, min(100, progress))
            self._persist(s)

    def finish(self, token: str, movie_path: str) -> None:
        with self._lock:
            s = self._sessions.get(token)
            if not s:
                return
            s.status = "ready"
            s.progress = 100
            s.movie_path = movie_path
            s.movies_made += 1
            s.messages.append("Your movie is ready.")
            self._write_log(s, "Your movie is ready.")
            self._persist(s)

    def fail(self, token: str, error: str) -> None:
        with self._lock:
            s = self._sessions.get(token)
            if not s:
                return
            s.status = "error"
            s.error = error
            msg = f"Terminal error: {error}"
            s.messages.append(msg)
            self._write_log(s, msg)
            self._persist(s)

    @staticmethod
    def _write_log(s: Session, message: str) -> None:
        """Append a timestamped line to the session's log.txt.  Best-effort:
        logging must never break the pipeline."""
        if not s.work_dir:
            return
        try:
            stamp = time.strftime("%Y-%m-%d %H:%M:%S")
            with open(Path(s.work_dir) / "log.txt", "a", encoding="utf-8") as fh:
                fh.write(f"[{stamp}] {message}\n")
        except Exception:
            pass


def settings_storage_dir() -> Path:
    from config import STORAGE_DIR

    return STORAGE_DIR


# Module-level singleton used across the app.
store = StateStore()
