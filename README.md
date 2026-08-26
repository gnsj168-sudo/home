# home

# Home

A personal multi-agent platform with retrieval-augmented generation, a hand-written
tool-calling loop, and a plug-in interface for extending it with new capabilities.

The first plug-in built on it, **internship**, tailors job applications by matching
requirements against the user's real, retrieved experience — and reports the gaps
instead of inventing them.

---

## Why this exists

Two things I wanted to understand properly rather than import: how retrieval
actually works over my own data, and how an agent decides to use a tool. Every
part of the loop here is code I can walk through and explain.

---

## Architecture

```
                 HTTP (FastAPI)
                       |
        +--------------+--------------+
        |                             |
     /ask                          /chat
  fixed RAG pipeline           agent loop
  retrieve -> answer          decides, may call
                              tools repeatedly
                                     |
                            +--------+--------+
                            |                 |
                     plug-in registry    Gemini API
                            |
             +--------------+--------------+
             |                             |
        core plug-in               internship plug-in
    search_notes, add_note,          match_profile
      get_current_time
             |
             +--> retrieval -> Postgres + pgvector
```

Both endpoints share one knowledge base. Keeping them side by side is deliberate:
`/ask` shows what fixed-pipeline RAG can do, `/chat` shows what the loop adds.

### Request flow for `/chat`

1. Load the last N turns of conversation history from Postgres
2. Send history + question + all registered tool schemas to Gemini
3. If the model requests tools, execute them **in Python** and append the results
4. Repeat until the model answers, capped at 8 iterations
5. Persist the turn

The model never executes anything. It requests; this code decides and runs.

---

## Design decisions

**Postgres + pgvector instead of a dedicated vector database.**
Chunks, embeddings, and conversation history live in one store, so retrieval can
filter with ordinary SQL alongside similarity search — no syncing two systems, no
lost joins. pgvector is slower at very large scale; at personal-platform scale that
ceiling is irrelevant.

**No LangChain or LlamaIndex.**
The agent loop is about 60 lines. Using a framework would have made it shorter and
made me unable to explain what happens when a tool throws, or when the model loops.
For a system I need to reason about, owning the control flow was worth the extra code.

**Automatic function calling disabled.**
The Gemini SDK will run the tool loop for you. It's switched off here
(`AutomaticFunctionCallingConfig(disable=True)`) so the call/execute/append cycle
is explicit and traceable.

**Provider-agnostic conversation storage.**
History is stored as plain user/assistant text, not SDK objects. Tool calls are
logged separately as JSONB for observability. Swapping model providers doesn't
make the history unreadable.

**A plug-in is only two things:** tools it contributes, and a system-prompt fragment
saying when to use them. Everything else — retrieval, the loop, persistence, error
handling — it inherits. Home's own tools are registered as the `core` plug-in through
the same interface, so the built-in case isn't a special case.

**Asymmetric embedding task types.**
Documents are embedded as `RETRIEVAL_DOCUMENT`, queries as `RETRIEVAL_QUERY`. A
question and its answer are worded very differently; this compensates.

**A distance threshold, tuned from observed data.**
Cosine distance above 0.45 is treated as no match, and the model is never called.
The number came from watching real queries: correct retrievals scored 0.24–0.34 with
a clear gap to second place, while questions with no answer in the store produced
results bunched at 0.45–0.52. Similarity search always returns *k* results — it
cannot say "I don't know", so the threshold says it instead.

---

## What it does

**Grounded question answering.** Answers come from ingested notes with chunk-level
citations. Asked "what is the capital of France?", it returns nothing — the model
knows, but the context doesn't contain it, and the guard rejects the query before
the API call.

**Multi-tool dispatch.** Three core tools with distinct descriptions; the model
selects among them. Asked the date it calls `get_current_time`; told to remember
something it calls `add_note`; asked about past work it calls `search_notes`.

**Self-extending knowledge.** `add_note` chunks, embeds, and stores new information
through the same pipeline as file ingestion, tagged with `source_type='note'`. The
agent writes to its own knowledge base and retrieves from it in later turns.

**Conversation memory.** Follow-ups resolve against history — "and what hardware did
I run it on?" becomes a search for the subject established two turns earlier.

**Honest application drafting.** The internship plug-in calls `match_profile` once
per job requirement and drafts bullets only from what comes back. Given a job
description listing Kubernetes experience the user does not have, it lists that
requirement as unmet rather than fabricating it.

---

## Stack

| Layer | Choice |
|---|---|
| API | FastAPI + uvicorn |
| Model | Gemini (configurable via `MODEL`) |
| Embeddings | `gemini-embedding-001`, 768 dimensions |
| Store | Postgres (Neon) + pgvector |
| Driver | psycopg 3 |

---

## Running it

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Create `.env`:

```
DATABASE_URL=postgresql://...
GEMINI_API_KEY=...
MODEL=gemini-3.6-flash
```

Set up the schema and ingest:

```bash
python setup_db.py
python ingest.py
```

Run:

```bash
uvicorn main:app --reload --port 8080
```

Then `http://localhost:8080/docs`.

---

## Example

<!-- PASTE YOUR TERMINAL OUTPUT FROM `python agent.py` HERE -->

```
```

---

## Files

| File | Role |
|---|---|
| `chunker.py` | Paragraph-aware splitting with a sliding overlap window |
| `ingest.py` | Write path — chunk, batch-embed, store with provenance |
| `retrieval.py` | Read path — cosine nearest-neighbour search |
| `memory.py` | Conversation persistence |
| `plugins.py` | Plug-in dataclass and registry with collision detection |
| `tools.py` | Core tools, registered as the `core` plug-in |
| `internship.py` | Internship plug-in |
| `agent.py` | The tool-calling loop |
| `main.py` | FastAPI endpoints |

---

## Known limitations

- **Chunking splits mid-word.** Paragraph-first, then a hard character split.
  Sentence-boundary splitting would be better; this was measured as good enough
  before optimising.
- **The agent over-searches.** It sometimes calls `search_notes` for information
  already present in conversation history, preferring to verify against sources.
  Correct but not cheap.
- **Grounding constrains, it doesn't prevent.** Output stays close to retrieved
  content but can still infer beyond it — one drafted bullet named a framework that
  was implied by the notes rather than stated in them.
- **No vector index.** At current scale Postgres scans every row in microseconds.
  Past ~100k chunks this needs an HNSW index.
- **History is truncated, not summarised.** The oldest turns beyond the limit are
  dropped rather than compressed.

---

## Roadmap

- Multimodal ingestion — voice memos and images through transcription/captioning
  adapters in front of the unchanged chunk/embed/store pipeline
- Web UI
- LLMOps layer — token and latency tracking per request, tool-use analytics from
  the existing JSONB logs
- Streaming responses
- Docker Compose for local Postgres (the connection string is already the only
  coupling point)