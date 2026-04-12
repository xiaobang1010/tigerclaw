from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from loguru import logger

from services.trace.types import ExecutionTrace, ToolCallRecord


class TraceStore:
    DEFAULT_DB_PATH = ".tigerclaw/traces.db"

    def __init__(self, db_path: str | None = None) -> None:
        resolved = db_path or self.DEFAULT_DB_PATH
        self._db_path = Path(resolved).resolve()
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS execution_traces (
                    trace_id TEXT PRIMARY KEY,
                    request_id TEXT DEFAULT '',
                    session_id TEXT DEFAULT '',
                    timestamp TEXT DEFAULT '',
                    duration_ms REAL DEFAULT 0.0,
                    model TEXT DEFAULT '',
                    provider TEXT DEFAULT '',
                    input_tokens INTEGER DEFAULT 0,
                    output_tokens INTEGER DEFAULT 0,
                    tool_calls TEXT DEFAULT '[]',
                    status TEXT DEFAULT 'success',
                    error TEXT DEFAULT '',
                    request_preview TEXT DEFAULT '',
                    response_preview TEXT DEFAULT ''
                )
            """)

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self._db_path))

    def save(self, trace: ExecutionTrace) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO execution_traces
                (trace_id, request_id, session_id, timestamp, duration_ms,
                 model, provider, input_tokens, output_tokens, tool_calls,
                 status, error, request_preview, response_preview)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    trace.trace_id,
                    trace.request_id,
                    trace.session_id,
                    trace.timestamp,
                    trace.duration_ms,
                    trace.model,
                    trace.provider,
                    trace.input_tokens,
                    trace.output_tokens,
                    json.dumps([tc.to_dict() for tc in trace.tool_calls], ensure_ascii=False),
                    trace.status,
                    trace.error,
                    trace.request_preview,
                    trace.response_preview,
                ),
            )

    def get(self, trace_id: str) -> ExecutionTrace | None:
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM execution_traces WHERE trace_id = ?", (trace_id,)
            )
            row = cursor.fetchone()
            if row is None:
                return None
            return self._row_to_trace(row)

    def list_traces(
        self,
        session_id: str | None = None,
        model: str | None = None,
        status: str | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ExecutionTrace]:
        conditions: list[str] = []
        params: list[Any] = []

        if session_id:
            conditions.append("session_id = ?")
            params.append(session_id)
        if model:
            conditions.append("model = ?")
            params.append(model)
        if status:
            conditions.append("status = ?")
            params.append(status)
        if start_time:
            conditions.append("timestamp >= ?")
            params.append(start_time)
        if end_time:
            conditions.append("timestamp <= ?")
            params.append(end_time)

        where_clause = ""
        if conditions:
            where_clause = "WHERE " + " AND ".join(conditions)

        query = f"""
            SELECT * FROM execution_traces
            {where_clause}
            ORDER BY timestamp DESC
            LIMIT ? OFFSET ?
        """
        params.extend([limit, offset])

        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(query, params)
            return [self._row_to_trace(row) for row in cursor.fetchall()]

    def get_stats(self) -> dict[str, Any]:
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            total = conn.execute("SELECT COUNT(*) as cnt FROM execution_traces").fetchone()["cnt"]
            errors = conn.execute("SELECT COUNT(*) as cnt FROM execution_traces WHERE status = 'error'").fetchone()["cnt"]
            tokens = conn.execute("SELECT COALESCE(SUM(input_tokens), 0) as inp, COALESCE(SUM(output_tokens), 0) as out FROM execution_traces").fetchone()
            avg_duration = conn.execute("SELECT COALESCE(AVG(duration_ms), 0) as avg FROM execution_traces").fetchone()["avg"]

            tool_stats_rows = conn.execute("SELECT tool_calls FROM execution_traces").fetchall()
            tool_call_counts: dict[str, int] = {}
            for row in tool_stats_rows:
                calls = json.loads(row["tool_calls"])
                for call in calls:
                    name = call.get("name", "unknown")
                    tool_call_counts[name] = tool_call_counts.get(name, 0) + 1

        return {
            "total_traces": total,
            "total_errors": errors,
            "error_rate": round(errors / total, 4) if total > 0 else 0.0,
            "total_input_tokens": tokens["inp"],
            "total_output_tokens": tokens["out"],
            "avg_duration_ms": round(avg_duration, 2),
            "tool_call_distribution": tool_call_counts,
        }

    def _row_to_trace(self, row: sqlite3.Row) -> ExecutionTrace:
        tool_calls_data = json.loads(row["tool_calls"])
        tool_calls = [ToolCallRecord.from_dict(tc) for tc in tool_calls_data]
        return ExecutionTrace(
            trace_id=row["trace_id"],
            request_id=row["request_id"],
            session_id=row["session_id"],
            timestamp=row["timestamp"],
            duration_ms=row["duration_ms"],
            model=row["model"],
            provider=row["provider"],
            input_tokens=row["input_tokens"],
            output_tokens=row["output_tokens"],
            tool_calls=tool_calls,
            status=row["status"],
            error=row["error"],
            request_preview=row["request_preview"],
            response_preview=row["response_preview"],
        )


_store: TraceStore | None = None


def get_trace_store() -> TraceStore:
    global _store
    if _store is None:
        _store = TraceStore()
    return _store


def generate_trace_id() -> str:
    return f"trace-{uuid.uuid4().hex[:16]}"
