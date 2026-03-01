import json
import os
import sqlite3
import time


class ModerationDB:
    def __init__(self, db_path):
        self._db_path = db_path
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS moderation_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                username TEXT NOT NULL,
                message TEXT NOT NULL,
                fast_result TEXT NOT NULL,
                big_result TEXT NOT NULL,
                final_action TEXT NOT NULL,
                severity REAL NOT NULL,
                reason TEXT NOT NULL
            )
        """)
        self._conn.commit()

    def log_action(self, username, message, fast_result, big_result,
                   final_action, severity, reason):
        self._conn.execute(
            """INSERT INTO moderation_log
               (timestamp, username, message, fast_result, big_result,
                final_action, severity, reason)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                time.time(),
                username,
                message,
                json.dumps(fast_result),
                json.dumps(big_result),
                final_action,
                severity,
                reason,
            ),
        )
        self._conn.commit()

    def get_user_history(self, username, limit=20):
        cur = self._conn.execute(
            """SELECT * FROM moderation_log
               WHERE username = ? ORDER BY timestamp DESC LIMIT ?""",
            (username, limit),
        )
        return [dict(row) for row in cur.fetchall()]

    def get_recent(self, limit=50):
        cur = self._conn.execute(
            """SELECT * FROM moderation_log
               ORDER BY timestamp DESC LIMIT ?""",
            (limit,),
        )
        return [dict(row) for row in cur.fetchall()]

    def close(self):
        self._conn.close()
