import os
import psycopg
from dotenv import load_dotenv
from google import genai
from pgvector.psycopg import register_vector
import numpy as np

load_dotenv()
client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])


def embed_query(text: str) -> list[float]:
    result = client.models.embed_content(
        model="gemini-embedding-001",
        contents=text,
        config={"output_dimensionality": 768, "task_type": "RETRIEVAL_QUERY"},
    )
    return result.embeddings[0].values


def search(question: str, k: int = 3) -> list[dict]:
    vector = embed_query(question)

    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        register_vector(conn)
        rows = conn.execute(
            """
            SELECT id, content, source, embedding <=> %s AS distance
            FROM chunks
            ORDER BY distance
            LIMIT %s;
            """,
            (np.array(vector, dtype=np.float32), k),
        ).fetchall()

    return [
        {"id": r[0], "content": r[1], "source": r[2], "distance": r[3]}
        for r in rows
    ]


if __name__ == "__main__":
    for q in ["what were my HTNet results?", "tell me about my android app"]:
        print(f"\n=== {q} ===")
        for hit in search(q):
            print(f"[{hit['distance']:.3f}] {hit['content'][:100]}...")