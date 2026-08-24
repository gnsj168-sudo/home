import os
import psycopg
from dotenv import load_dotenv
from google import genai
from pgvector.psycopg import register_vector

load_dotenv()

client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
    register_vector(conn)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS chunks (
            id SERIAL PRIMARY KEY,
            content TEXT NOT NULL,
            embedding vector(768)
        );
    """)

    text = "Asgv researches micro-expression recognition using deep learning."

    result = client.models.embed_content(
        model="gemini-embedding-001",
        contents=text,
        config={"output_dimensionality": 768},
    )
    vector = result.embeddings[0].values
    print(f"Embedding length: {len(vector)}")

    conn.execute(
        "INSERT INTO chunks (content, embedding) VALUES (%s, %s)",
        (text, vector),
    )
    conn.commit()

    rows = conn.execute("SELECT id, content FROM chunks").fetchall()
    print(rows)