"""
Assignment 11 — Audit Log starter (TODO).

Records every interaction for forensics. Never blocks by itself —
other layers catch attacks; this layer makes them reviewable.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path


class AuditLogPlugin:
    """Framework-agnostic audit logger (wire into ADK callbacks or your pipeline)."""

    def __init__(self):
        self.name = "audit_log"
        self.logs: list[dict] = []
        self._open: dict[str, dict] = {}

    def record_input(self, *, user_id: str, text: str, request_id: str | None = None):
        """Store input metadata until the matching output is recorded."""
        key = request_id or user_id
        self._open[key] = {
            "request_id": request_id or key,
            "user_id": user_id,
            "input": text,
            "started_at": utc_now_iso(),
            "started_perf": time.perf_counter(),
        }

    def record_output(
        self,
        *,
        user_id: str,
        text: str,
        blocked: bool = False,
        layer: str | None = None,
        request_id: str | None = None,
    ):
        """Finish an interaction and append a reviewable audit row."""
        key = request_id or user_id
        opened = self._open.pop(key, None) or {
            "request_id": request_id or key,
            "user_id": user_id,
            "input": "",
            "started_at": utc_now_iso(),
            "started_perf": time.perf_counter(),
        }
        latency_ms = max(0.0, (time.perf_counter() - opened.pop("started_perf")) * 1000)
        self.logs.append({
            **opened,
            "completed_at": utc_now_iso(),
            "output": text,
            "blocked": bool(blocked),
            "layer": layer,
            "latency_ms": round(latency_ms, 3),
        })

    def export_json(self, filepath: str = "outputs/audit_log.json"):
        """Write logs to disk (JSON array)."""
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.logs, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return path


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
