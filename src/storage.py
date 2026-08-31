"""
SQLite Storage - Clears prior data on startup to ensure fresh records only.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Dict, Iterator, List

from .config import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS recovery_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL,
    strategy_id TEXT,
    payload_id TEXT,
    order_reference TEXT,
    customer_name TEXT,
    customer_phone TEXT,
    amount REAL NOT NULL,
    decline_reason TEXT NOT NULL,
    payment_method TEXT,
    bank TEXT,
    retry_count INTEGER DEFAULT 0,
    channel TEXT,
    confidence_score REAL,
    urgency_level TEXT,
    decided_by TEXT,
    recommended_action TEXT,
    reasoning_json TEXT,
    installment_plan_json TEXT,
    payment_link TEXT,
    razorpay_payment_link_id TEXT,
    sms_message TEXT,
    sms_sid TEXT,
    notified INTEGER DEFAULT 0,
    recovered INTEGER DEFAULT 0,
    created_at TEXT NOT NULL
);
"""


@contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(settings.database_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db(clear_data: bool = True) -> None:
    with get_connection() as conn:
        conn.execute(SCHEMA)
        if clear_data:
            conn.execute("DELETE FROM recovery_records;")


def insert_record(record: Dict[str, Any]) -> int:
    with get_connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO recovery_records (
                event_id, strategy_id, payload_id, order_reference, customer_name,
                customer_phone, amount, decline_reason, payment_method, bank,
                retry_count, channel, confidence_score, urgency_level, decided_by,
                recommended_action, reasoning_json, installment_plan_json,
                payment_link, razorpay_payment_link_id, sms_message,
                sms_sid, notified, recovered, created_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                record["event_id"], record.get("strategy_id"), record.get("payload_id"),
                record.get("order_reference"), record.get("customer_name"), record.get("customer_phone"),
                record["amount"], record["decline_reason"], record.get("payment_method"), record.get("bank"),
                record.get("retry_count", 0), record.get("channel"), record.get("confidence_score"),
                record.get("urgency_level"), record.get("decided_by"), record.get("recommended_action"),
                json.dumps(record.get("reasoning", [])), json.dumps(record.get("installment_plan")),
                record.get("payment_link"), record.get("razorpay_payment_link_id"),
                record.get("sms_message"), record.get("sms_sid"),
                int(record.get("notified", False)), int(record.get("recovered", False)),
                datetime.utcnow().isoformat(),
            ),
        )
        return cur.lastrowid


def mark_recovered(event_id: str, recovered: bool = True) -> None:
    """Updates the recovered status of a specific event in SQLite."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE recovery_records SET recovered = ? WHERE event_id = ?",
            (1 if recovered else 0, event_id),
        )
        conn.commit()


def fetch_all(limit: int = 200) -> List[Dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM recovery_records ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]


def fetch_metrics() -> Dict[str, float]:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT
                COUNT(*) as total_events,
                COALESCE(SUM(amount), 0) as failed_revenue_analyzed,
                COALESCE(SUM(recovered), 0) as auto_recoveries,
                COALESCE(SUM(CASE WHEN recovered = 1 THEN amount ELSE 0 END), 0) as recovered_amount
            FROM recovery_records
            """
        ).fetchone()
        total = row["total_events"] or 0
        recoveries = row["auto_recoveries"] or 0
        agent_rate = (recoveries / total) if total else 0.0
        baseline = settings.baseline_dunning_recovery_rate
        lift = ((agent_rate - baseline) / baseline) * 100 if baseline else 0.0
        return {
            "total_events": total,
            "failed_revenue_analyzed": row["failed_revenue_analyzed"] or 0.0,
            "auto_recoveries": recoveries,
            "recovered_amount": row["recovered_amount"] or 0.0,
            "conversion_lift_pct": lift,
        }