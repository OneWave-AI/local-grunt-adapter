"""Cross-client job state for the desktop panel. Stores labels, never source text."""
import os
import sqlite3
import time


class Jobs:
    def __init__(self, state):
        self.path = state / "jobs.sqlite3"
        with self.connect() as c:
            c.execute("""CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY, task TEXT, label TEXT, model TEXT, phase TEXT,
                started REAL, finished REAL, pid INTEGER, cached INTEGER DEFAULT 0,
                input_tokens INTEGER DEFAULT 0, output_tokens INTEGER DEFAULT 0, error TEXT)""")
            c.execute("BEGIN IMMEDIATE")
            columns = {r[1] for r in c.execute("PRAGMA table_info(jobs)")}
            for name, kind in {"context_tokens": "INTEGER", "source_chars": "INTEGER", "file_count": "INTEGER", "source_mode": "TEXT", "routing_reason": "TEXT", "outcome": "TEXT", "load_seconds": "REAL", "generation_seconds": "REAL"}.items():
                if name not in columns: c.execute(f"ALTER TABLE jobs ADD COLUMN {name} {kind}")

    def connect(self): return sqlite3.connect(self.path, timeout=10)

    def start(self, call_id, task, label):
        with self.connect() as c:
            c.execute("INSERT INTO jobs (id,task,label,model,phase,started,pid) VALUES (?,?,?,?,?,?,?)",
                      (call_id, task, (label or task.replace('_', ' ').capitalize())[:80], "Choosing model", "preparing", time.time(), os.getpid()))
            c.execute("DELETE FROM jobs WHERE id IN (SELECT id FROM jobs WHERE finished IS NOT NULL ORDER BY started DESC LIMIT -1 OFFSET 100)")

    def phase(self, call_id, phase, model=""):
        with self.connect() as c:
            c.execute("UPDATE jobs SET phase=?, model=CASE WHEN ?='' THEN model ELSE ? END WHERE id=?", (phase, model, model, call_id))

    def details(self, call_id, **values):
        allowed = {"context_tokens", "source_chars", "file_count", "source_mode", "routing_reason", "outcome", "load_seconds", "generation_seconds"}
        if not values or not set(values).issubset(allowed): raise ValueError("Unsupported job details")
        with self.connect() as c:
            c.execute("UPDATE jobs SET " + ",".join(key + "=?" for key in values) + " WHERE id=?", (*values.values(), call_id))

    def skip(self, call_id, task, reason, label=""):
        self.start(call_id, task, label)
        with self.connect() as c:
            c.execute("UPDATE jobs SET phase='kept_with_caller',model='Cloud assistant',finished=?,routing_reason=? WHERE id=?", (time.time(), reason, call_id))

    def finish(self, call_id, result=None, error=None):
        result = result or {}
        with self.connect() as c:
            c.execute("UPDATE jobs SET phase=?,finished=?,model=CASE WHEN ?='' THEN model ELSE ? END,cached=?,input_tokens=?,output_tokens=?,error=? WHERE id=?",
                      ("failed" if error else "complete", time.time(), result.get("model", ""), result.get("model", ""), int(result.get("cached", False)),
                       result.get("local_input_tokens", 0), result.get("local_output_tokens", 0), error, call_id))

    def snapshot(self):
        with self.connect() as c:
            c.row_factory = sqlite3.Row
            rows = [dict(row) for row in c.execute("SELECT * FROM jobs ORDER BY started DESC LIMIT 40")]
            for row in rows:
                if row["finished"] is None:
                    if time.time()-row["started"] > 300:
                        c.execute("UPDATE jobs SET phase='interrupted',finished=?,error='Worker status timed out' WHERE id=?", (time.time(), row["id"]))
                        row.update(phase="interrupted", finished=time.time(), error="Worker status timed out")
                        continue
                    try: os.kill(row["pid"], 0)
                    except ProcessLookupError:
                        c.execute("UPDATE jobs SET phase='interrupted',finished=?,error='Worker exited before finishing' WHERE id=?", (time.time(), row["id"]))
                        row.update(phase="interrupted", finished=time.time(), error="Worker exited before finishing")
        return rows
