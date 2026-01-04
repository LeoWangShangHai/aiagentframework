from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _default_db_path() -> str:
    env = os.getenv("TOKEN_USAGE_DB_PATH")
    if env and env.strip():
        return env.strip()

    # backend/app/db/token_usage.py -> project root is parents[3]
    project_root = Path(__file__).resolve().parents[3]
    return str(project_root / "token_usage.sqlite3")


def _connect(db_path: str | None = None) -> sqlite3.Connection:
    path = db_path or _default_db_path()
    conn = sqlite3.connect(path, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS conversation_turn_usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id TEXT NOT NULL,
            turn_index INTEGER NOT NULL,
            input_tokens INTEGER NOT NULL,
            output_tokens INTEGER NOT NULL,
            total_tokens INTEGER NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_ctu_conversation_turn ON conversation_turn_usage(conversation_id, turn_index)"
    )
    conn.commit()


@dataclass(frozen=True)
class TurnUsageRow:
    conversation_id: str
    turn_index: int
    input_tokens: int
    output_tokens: int
    total_tokens: int
    created_at: str


@dataclass(frozen=True)
class ConversationSummary:
    conversation_id: str
    turns: int
    total_tokens: int
    last_created_at: str


def record_turn_usage(
    conversation_id: str,
    turn_index: int,
    usage: dict[str, int],
    *,
    db_path: str | None = None,
) -> None:
    input_tokens = int(usage.get("input_tokens", 0))
    output_tokens = int(usage.get("output_tokens", 0))
    total_tokens = int(usage.get("total_tokens", input_tokens + output_tokens))

    created_at = datetime.now(timezone.utc).isoformat()

    conn = _connect(db_path)
    try:
        _ensure_schema(conn)
        conn.execute(
            """
            INSERT INTO conversation_turn_usage (
                conversation_id, turn_index, input_tokens, output_tokens, total_tokens, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (conversation_id, int(turn_index), input_tokens, output_tokens, total_tokens, created_at),
        )
        conn.commit()
    finally:
        conn.close()


def list_conversations_page(
    *,
    db_path: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[ConversationSummary]:
    conn = _connect(db_path)
    try:
        _ensure_schema(conn)
        rows = conn.execute(
            """
            SELECT
                conversation_id,
                COUNT(1) AS turns,
                COALESCE(SUM(total_tokens), 0) AS total_tokens,
                MAX(created_at) AS last_created_at
            FROM conversation_turn_usage
            GROUP BY conversation_id
            ORDER BY last_created_at DESC
            LIMIT ? OFFSET ?
            """,
            (int(limit), int(offset)),
        ).fetchall()
        return [
            ConversationSummary(
                conversation_id=str(r["conversation_id"]),
                turns=int(r["turns"]),
                total_tokens=int(r["total_tokens"]),
                last_created_at=str(r["last_created_at"]),
            )
            for r in rows
        ]
    finally:
        conn.close()


def count_conversations(
    *,
    db_path: str | None = None,
) -> int:
    conn = _connect(db_path)
    try:
        _ensure_schema(conn)
        row = conn.execute(
            """
            SELECT COUNT(1) AS total
            FROM (
                SELECT DISTINCT conversation_id
                FROM conversation_turn_usage
            )
            """,
        ).fetchone()
        if row is None:
            return 0
        return int(row["total"])
    finally:
        conn.close()


def list_turn_usage(
    conversation_id: str,
    *,
    db_path: str | None = None,
    limit: int = 1000,
) -> list[TurnUsageRow]:
    conn = _connect(db_path)
    try:
        _ensure_schema(conn)
        rows = conn.execute(
            """
            SELECT conversation_id, turn_index, input_tokens, output_tokens, total_tokens, created_at
            FROM conversation_turn_usage
            WHERE conversation_id = ?
            ORDER BY turn_index ASC, id ASC
            LIMIT ?
            """,
            (conversation_id, int(limit)),
        ).fetchall()
        return [
            TurnUsageRow(
                conversation_id=str(r["conversation_id"]),
                turn_index=int(r["turn_index"]),
                input_tokens=int(r["input_tokens"]),
                output_tokens=int(r["output_tokens"]),
                total_tokens=int(r["total_tokens"]),
                created_at=str(r["created_at"]),
            )
            for r in rows
        ]
    finally:
        conn.close()


def list_turn_usage_page(
    conversation_id: str,
    *,
    db_path: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[TurnUsageRow]:
    conn = _connect(db_path)
    try:
        _ensure_schema(conn)
        rows = conn.execute(
            """
            SELECT conversation_id, turn_index, input_tokens, output_tokens, total_tokens, created_at
            FROM conversation_turn_usage
            WHERE conversation_id = ?
            ORDER BY turn_index ASC, id ASC
            LIMIT ? OFFSET ?
            """,
            (conversation_id, int(limit), int(offset)),
        ).fetchall()
        return [
            TurnUsageRow(
                conversation_id=str(r["conversation_id"]),
                turn_index=int(r["turn_index"]),
                input_tokens=int(r["input_tokens"]),
                output_tokens=int(r["output_tokens"]),
                total_tokens=int(r["total_tokens"]),
                created_at=str(r["created_at"]),
            )
            for r in rows
        ]
    finally:
        conn.close()


def count_turn_usage(
    conversation_id: str,
    *,
    db_path: str | None = None,
) -> int:
    conn = _connect(db_path)
    try:
        _ensure_schema(conn)
        row = conn.execute(
            """
            SELECT COUNT(1) AS total
            FROM conversation_turn_usage
            WHERE conversation_id = ?
            """,
            (conversation_id,),
        ).fetchone()
        if row is None:
            return 0
        return int(row["total"])
    finally:
        conn.close()


def summarize_usage(
    conversation_id: str,
    *,
    db_path: str | None = None,
) -> dict[str, Any]:
    conn = _connect(db_path)
    try:
        _ensure_schema(conn)
        row = conn.execute(
            """
            SELECT
                COUNT(1) AS turns,
                COALESCE(SUM(input_tokens), 0) AS input_tokens,
                COALESCE(SUM(output_tokens), 0) AS output_tokens,
                COALESCE(SUM(total_tokens), 0) AS total_tokens
            FROM conversation_turn_usage
            WHERE conversation_id = ?
            """,
            (conversation_id,),
        ).fetchone()
        if row is None:
            return {"turns": 0, "input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
        return {
            "turns": int(row["turns"]),
            "input_tokens": int(row["input_tokens"]),
            "output_tokens": int(row["output_tokens"]),
            "total_tokens": int(row["total_tokens"]),
        }
    finally:
        conn.close()
