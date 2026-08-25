import json
import os
import psycopg
from dotenv import load_dotenv

load_dotenv()


def save_message(conversation_id: str, role: str, content: str, tool_calls=None):
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        conn.execute(
            "INSERT INTO messages (conversation_id, role, content, tool_calls) "
            "VALUES (%s, %s, %s, %s)",
            (
                conversation_id,
                role,
                content,
                json.dumps(tool_calls) if tool_calls else None,
            ),
        )
        conn.commit()


def load_history(conversation_id: str, limit: int = 10) -> list[dict]:
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        rows = conn.execute(
            """
            SELECT role, content FROM (
                SELECT role, content, created_at
                FROM messages
                WHERE conversation_id = %s
                ORDER BY created_at DESC
                LIMIT %s
            ) recent
            ORDER BY created_at ASC;
            """,
            (conversation_id, limit),
        ).fetchall()

    return [{"role": r[0], "content": r[1]} for r in rows]