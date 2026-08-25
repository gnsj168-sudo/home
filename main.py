import os
import psycopg
from dotenv import load_dotenv
from fastapi import FastAPI
from google import genai
from pydantic import BaseModel

from retrieval import search

load_dotenv()
client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
app = FastAPI(title="Home")

MAX_DISTANCE = 0.45

SYSTEM_PROMPT = """You are Home, a personal assistant that answers questions using only the context provided below.

Rules:
- Answer only from the context. Do not use outside knowledge.
- If the context does not contain the answer, say you do not have that information.
- Be concise.

Context:
{context}"""


class AskRequest(BaseModel):
    question: str


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/ask")
def ask(req: AskRequest):
    hits = search(req.question, k=3)

    if not hits or hits[0]["distance"] > MAX_DISTANCE:
        return {
            "answer": "I don't have anything relevant to that in my notes.",
            "sources": [],
        }

    context = "\n\n---\n\n".join(
        f"[chunk {h['id']}] {h['content']}" for h in hits
    )

    response = client.models.generate_content(
        model="gemini-3.6-flash",
        contents=req.question,
        config={"system_instruction": SYSTEM_PROMPT.format(context=context)},
    )

    return {
        "answer": response.text,
        "sources": [
            {"id": h["id"], "distance": round(h["distance"], 3), "source": h["source"]}
            for h in hits
        ],
    }
