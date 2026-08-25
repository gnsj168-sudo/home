import os
from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np
import psycopg
from dotenv import load_dotenv
from pgvector.psycopg import register_vector

from chunker import chunk_text
from ingest import embed_documents
from retrieval import search

load_dotenv()

MAX_DISTANCE = 0.45


def search_notes(query: str) -> str:
    """Search the user's personal notes and return relevant passages."""
    hits = search(query, k=3)
    hits = [h for h in hits if h["distance"] <= MAX_DISTANCE]

    if not hits:
        return "No relevant notes found."

    return "\n\n".join(
        f"[chunk {h['id']}, distance {h['distance']:.3f}]\n{h['content']}"
        for h in hits
    )


def add_note(content: str) -> str:
    """Store a new note in the user's knowledge base."""
    chunks = chunk_text(content)
    if not chunks:
        return "Nothing to store — the note was empty."

    vectors = embed_documents(chunks)

    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        register_vector(conn)
        with conn.cursor() as cur:
            for text, vector in zip(chunks, vectors):
                cur.execute(
                    "INSERT INTO chunks (content, embedding, source, source_type) "
                    "VALUES (%s, %s, %s, %s)",
                    (text, np.array(vector, dtype=np.float32), "agent", "note"),
                )
        conn.commit()

    return f"Stored {len(chunks)} chunk(s)."


def get_current_time() -> str:
    """Return the current date and time in the user's timezone."""
    now = datetime.now(ZoneInfo("Asia/Kuala_Lumpur"))
    return now.strftime("%A, %d %B %Y, %I:%M %p")


TOOL_SCHEMAS = [
    {
        "name": "search_notes",
        "description": (
            "Search the user's personal notes and documents for information about "
            "their research, projects, coursework, or background. Use this whenever "
            "the question refers to the user's own work or life."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query, phrased as a natural question or topic.",
                }
            },
            "required": ["query"],
        },
    },
    {
        "name": "add_note",
        "description": (
            "Save new information to the user's knowledge base so it can be "
            "retrieved later. Use this when the user tells you something to "
            "remember, or shares a fact about themselves or their work."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "The note text to store, written as a complete sentence.",
                }
            },
            "required": ["content"],
        },
    },
    {
        "name": "get_current_time",
        "description": "Get the current date and time. Use for anything date-relative.",
        "parameters": {"type": "object", "properties": {}},
    },
]

TOOL_IMPLEMENTATIONS = {
    "search_notes": search_notes,
    "add_note": add_note,
    "get_current_time": get_current_time,
}

from plugins import Plugin

CORE_PLUGIN = Plugin(
    name="core",
    description="Home's built-in notes and time tools.",
    schemas=TOOL_SCHEMAS,
    implementations=TOOL_IMPLEMENTATIONS,
    prompt_fragment=(
        "Use search_notes for anything about the user's own work or life. "
        "Use add_note when they tell you something to remember."
    ),
)