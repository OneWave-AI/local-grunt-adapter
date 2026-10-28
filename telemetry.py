"""Private metadata ledger; IDs pair outcomes correctly across simultaneous clients."""
import json
import sqlite3
import time
import math
from pathlib import Path


class Ledger:
    def __init__(self, path):
        self.path = path
        with self.connect() as c:
            c.execute("""CREATE TABLE IF NOT EXISTS calls (
                id TEXT PRIMARY KEY, created REAL, task TEXT, model TEXT, status TEXT,
                cached INTEGER, elapsed REAL, input_tokens INTEGER, output_tokens INTEGER,
                source_mode TEXT, source_chars INTEGER, returned_chars INTEGER, outcome TEXT)""")

            c.execute("CREATE TABLE IF NOT EXISTS cloud_pairs (id TEXT PRIMARY KEY, baseline INTEGER, delegated INTEGER)")

    def connect(self):
        return sqlite3.connect(self.path, timeout=10)

    def record(self, call_id, task, result, status, source_mode):
        with self.connect() as c:
            c.execute("INSERT INTO calls VALUES (?,?,?,?,?,?,?,?,?,?,?,?,NULL)", (
                call_id, time.time(), task, result.get("model", ""), status, int(result.get("cached", False)),
                result.get("elapsed_seconds", 0), result.get("local_input_tokens", 0), result.get("local_output_tokens", 0),
                source_mode, result.get("source_characters", result.get("input_characters", 0)), len(json.dumps(result, ensure_ascii=False))))
            # Retain compact metadata for lifetime accounting; no source or result bodies.

    def outcome(self, call_id, verdict):
        if verdict not in {"accepted", "rejected", "redone"}:
            raise ValueError("outcome must be accepted, rejected or redone")
        with self.connect() as c:
            row = c.execute("SELECT status FROM calls WHERE id=?", (call_id,)).fetchone()
            if not row: raise ValueError("Unknown call_id")
            if row[0] != "ok": raise ValueError("Cannot mark failed generation as a reviewed result")
            c.execute("UPDATE calls SET outcome=? WHERE id=?", (verdict, call_id))
        return {"call_id": call_id, "outcome": verdict}

    def summary(self):
        with self.connect() as c:
            rows = c.execute("SELECT task,status,cached,elapsed,input_tokens,output_tokens,source_mode,source_chars,returned_chars,outcome FROM calls WHERE created>?", (time.time() - 30 * 86400,)).fetchall()
        result = {"calls": len(rows), "completed": 0, "failed": 0, "cache_hits": 0, "reviewed": 0, "accepted": 0,
                  "local_input_tokens": 0, "local_output_tokens": 0, "elapsed_seconds": 0, "by_task": {},
                  "measured_cloud_tokens_saved": None,
                  "note": "Local inference counts are not cloud billing or subscription savings. Acceptance is caller-reported."}
        for task, status, cached, elapsed, ti, to, mode, chars, returned, outcome in rows:
            bucket = result["by_task"].setdefault(task, {"calls": 0, "completed": 0, "reviewed": 0, "accepted": 0})
            bucket["calls"] += 1
            result["completed"] += status == "ok"
            bucket["completed"] += status == "ok"
            result["failed"] += status != "ok"
            result["cache_hits"] += cached
            result["local_input_tokens"] += ti
            result["local_output_tokens"] += to
            result["elapsed_seconds"] += elapsed
            if outcome:
                result["reviewed"] += 1
                bucket["reviewed"] += 1
                result["accepted"] += outcome == "accepted"
                bucket["accepted"] += outcome == "accepted"
        result["elapsed_seconds"] = round(result["elapsed_seconds"], 3)
        result["acceptance_rate"] = round(result["accepted"] / result["reviewed"], 3) if result["reviewed"] else None
        result["roi"] = self.roi()
        result["measured_cloud_tokens_saved"] = result["roi"]["measured_net_cloud_tokens_saved"]
        return result

    def record_cloud_pair(self, call_id, baseline_tokens, delegated_tokens):
        """Caller-reported paired total cloud tokens, including cached input and output."""
        for n in (baseline_tokens, delegated_tokens):
            if type(n) is not int or n < 0:
                raise ValueError("Cloud token totals must be nonnegative integers")
        with self.connect() as c:
            if not c.execute("SELECT 1 FROM calls WHERE id=?", (call_id,)).fetchone():
                raise ValueError("Unknown call_id")
            c.execute("INSERT OR REPLACE INTO cloud_pairs VALUES (?,?,?)", (call_id, baseline_tokens, delegated_tokens))
        return {"call_id": call_id, "measured_net_cloud_tokens": baseline_tokens-delegated_tokens,
                "note": "Caller-reported paired measurements; total tokens are not billed dollars or subscription quota."}

    def roi(self):
        config_path = Path(self.path).parent / "roi-config.json"
        config = json.loads(config_path.read_text()) if config_path.exists() else {}
        ratio = config.get("characters_per_token", 4)
        overhead = config.get("delegation_overhead_tokens", 1000)
        rate = config.get("blended_cloud_usd_per_million_tokens")
        local_cost = config.get("local_cost_usd", 0)
        for name, value in [("characters_per_token", ratio), ("delegation_overhead_tokens", overhead), ("local_cost_usd", local_cost), ("blended_cloud_usd_per_million_tokens", rate)]:
            if value is not None and (type(value) not in (int,float) or not math.isfinite(value) or value < 0):
                raise ValueError("Invalid ROI setting: " + name)
        if ratio is None or overhead is None or local_cost is None: raise ValueError("ROI assumptions cannot be null")
        if ratio == 0: raise ValueError("characters_per_token must be positive")
        with self.connect() as c:
            rows = c.execute("SELECT status,source_mode,source_chars,returned_chars,outcome,input_tokens,output_tokens,cached,elapsed FROM calls").fetchall()
            pairs = c.execute("SELECT baseline,delegated FROM cloud_pairs").fetchall()
            earliest = c.execute("SELECT MIN(created) FROM calls").fetchone()[0]
        accepted = [r for r in rows if r[0] == "ok" and r[4] == "accepted"]
        # Text already supplied to the cloud earns no avoided-input credit. Unreviewed
        # and unsuccessful calls incur overhead, but earn no savings credit.
        avoided = sum(math.ceil(r[2]/ratio) for r in accepted if r[1] == "files")
        returned = sum(math.ceil(r[3]/ratio) for r in rows)
        net = avoided - returned - len(rows)*overhead
        gross = net*rate/1e6 if rate is not None else None
        savings = gross-local_cost if gross is not None else None
        return {"scope": "lifetime retained metadata", "tracking_since": earliest,
                "calls": len(rows), "accepted": len(accepted), "cache_hits": sum(r[7] for r in rows),
                "local_input_tokens": sum(r[5] for r in rows), "local_output_tokens": sum(r[6] for r in rows),
                "local_elapsed_seconds": round(sum(r[8] for r in rows),3),
                "estimated_avoided_cloud_input_tokens": avoided,
                "estimated_return_tokens": returned, "estimated_delegation_overhead_tokens": len(rows)*overhead,
                "estimated_net_cloud_tokens_saved": net,
                "estimated_net_usd": savings,
                "estimated_roi_percent": round(savings/local_cost*100,2) if savings is not None and local_cost>0 else None,
                "local_cost_usd": local_cost, "paired_measurements": len(pairs),
                "measured_net_cloud_tokens_saved": sum(a-b for a,b in pairs) if pairs else None,
                "assumptions": {"characters_per_token": ratio, "delegation_overhead_tokens": overhead,
                    "blended_cloud_usd_per_million_tokens": rate},
                "note": "Estimate: accepted file-input characters / ratio, minus returned metadata and per-call overhead. Text/mixed inputs receive no avoided-input credit. Failures, rejected and unreviewed calls earn no credit. Repeated cloud context, review, cache pricing and actual tokenizer usage can differ substantially. Money requires a user-supplied blended rate; local cost is user-supplied. No subscription quota claim. Historical totals cover retained records only."}
