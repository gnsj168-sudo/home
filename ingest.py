import os
import psycopg
from dotenv import load_dotenv
from google import genai
from pgvector.psycopg import register_vector
from chunker import chunk_text

load_dotenv()
client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])


def embed_documents(texts: list[str]) -> list[list[float]]:
    result = client.models.embed_content(
        model="gemini-embedding-001",
        contents=texts,
        config={"output_dimensionality": 768, "task_type": "RETRIEVAL_DOCUMENT"},
    )
    return [e.values for e in result.embeddings]


def ingest_file(path: str, source_type: str = "text"):
    text = open(path, encoding="utf-8").read()
    chunks = chunk_text(text)
    print(f"{len(chunks)} chunks to embed")

    vectors = embed_documents(chunks)

    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        register_vector(conn)
        conn.execute("TRUNCATE chunks RESTART IDENTITY;")
        with conn.cursor() as cur:
            for content, vector in zip(chunks, vectors):
                cur.execute(
                    "INSERT INTO chunks (content, embedding, source, source_type) "
                    "VALUES (%s, %s, %s, %s)",
                    (content, vector, path, source_type),
                )
        conn.commit()
        count = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        print(f"stored {count} rows")


if __name__ == "__main__":
    ingest_file("input/notes.txt")