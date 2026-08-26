# Home

A personal assistant platform with retrieval over my own notes, a hand-written
tool-calling loop, and a plug-in interface for adding new capabilities.

Three plug-ins run on it today: **core** (notes and time), **calendar** (read and
write Google Calendar), and **internship** (tailors job applications to real,
retrieved experience — and reports the gaps instead of inventing them).

---

## Why this exists

Two things I wanted to understand properly rather than import: how retrieval
actually works over my own data, and how an agent decides to use a tool. Every part
of the loop here is code I can walk through and explain.

---

## Architecture

```
              browser (chat UI)
                     |
              FastAPI (main.py)
                     |
        +------------+------------+
        |                         |
      /ask                      /chat
  fixed RAG pipeline        agent loop (agent.py)
  retrieve -> answer        decides, may call tools
                            repeatedly, capped at 8
                                   |
                        +----------+----------+
                        |                     |
                 plug-in registry        Gemini API
                        |
        +---------------+---------------+
        |               |               |
      core          calendar        internship
  search_notes    list_events      match_profile
  add_note        create_event
  get_current_time
        |               |               |
        |    Google Calendar API        |
        +---------------+---------------+
                        |
             retrieval -> Postgres + pgvector
```

### Request flow for `/chat`

1. Load recent conversation history from Postgres
2. Send history + question + every registered tool schema to Gemini
3. If the model requests tools, execute them **in Python** and append the results
4. Repeat until the model answers, capped at 8 iterations
5. Persist the turn

The model never executes anything. It requests; this code decides and runs.

---

## Design decisions

**RAG for stable data, live API calls for volatile data.**
Notes and documents are chunked and embedded — they're large, stable, and benefit
from semantic search. Calendar data is fetched live on every query and never
embedded: it changes constantly, so an embedded copy would go stale immediately and
retrieve last week's schedule with full confidence. Getting this split wrong is a
quiet failure, because stale retrieval looks exactly like fresh retrieval.

**Postgres + pgvector instead of a dedicated vector database.**
Chunks, embeddings, and conversation history live in one store, so retrieval can
filter with ordinary SQL alongside similarity search — no syncing two systems, no
lost joins. pgvector is slower at very large scale; at personal-platform scale that
ceiling is irrelevant.

**No LangChain or LlamaIndex.**
The agent loop is about 60 lines. A framework would have made it shorter and made me
unable to explain what happens when a tool throws, or when the model loops. Owning
the control flow was worth the extra code.

**Automatic function calling disabled.**
The Gemini SDK will run the tool loop for you. It's switched off
(`AutomaticFunctionCallingConfig(disable=True)`) so the call/execute/append cycle is
explicit and traceable.

**A plug-in is only two things:** tools it contributes, and a system-prompt fragment
saying when to use them. Everything else — retrieval, the loop, persistence, error
handling — it inherits. Home's own tools are registered as the `core` plug-in through
the same interface, so the built-in case isn't a special case. Adding the calendar
plug-in was one import and one `register()` call.

**Tools are for capabilities the model lacks.**
The internship plug-in has one tool, not three. Parsing a job description and writing
bullets are things the model already does; only `match_profile` touches the database,
so only it needs to exist. The rest is prompt.

**Least-privilege OAuth scopes.**
Calendar access started as `calendar.readonly` and moved to `calendar.events` only
when writing was added. The app cannot delete calendars or read anything outside
events.

**Provider-agnostic conversation storage.**
History is stored as plain user/assistant text, not SDK objects. Tool calls are
logged separately as JSONB for observability. Swapping model providers doesn't make
the history unreadable.

**Asymmetric embedding task types.**
Documents are embedded as `RETRIEVAL_DOCUMENT`, queries as `RETRIEVAL_QUERY`. A
question and its answer are worded very differently; this compensates.

**A distance threshold, tuned from observed data.**
Cosine distance above 0.45 is treated as no match, and the model is never called. The
number came from watching real queries: correct retrievals scored 0.24–0.34 with a
clear gap to second place, while questions with no answer in the store produced
results bunched at 0.45–0.52. Similarity search always returns *k* results — it
cannot say "I don't know", so the threshold says it instead.

**Plain-text output instead of rendered markdown.**
Model output flows into the browser alongside retrieved chunks and calendar events —
text I didn't write. Rendering it as HTML is an injection surface that needs a
sanitiser, not just a parser. The system prompt asks for plain text instead: no new
dependency, no new attack surface.

---

## What it does

**Grounded question answering.** Answers come from ingested notes with chunk-level
citations. Asked "what is the capital of France?", it returns nothing — the model
knows, but the context doesn't contain it, and the guard rejects the query before the
API call.

**Multi-tool dispatch across plug-ins.** The model selects among tools from every
registered plug-in based on their descriptions alone.

**Tool chaining.** Asked "what's on my calendar this week?", the model calls
`get_current_time` (core plug-in) to learn today's date, then `list_events` (calendar
plug-in) with real computed dates. Nothing in the code links those two tools — the
chaining comes out of the loop.

**Self-extending knowledge.** `add_note` chunks, embeds, and stores new information
through the same pipeline as file ingestion, tagged `source_type='note'`. The agent
writes to its own knowledge base and retrieves from it in later turns.

**Conversation memory.** Follow-ups resolve against history — "and what hardware did I
run it on?" becomes a search for the subject established two turns earlier.

**Calendar writes with provenance.** Events created by Home carry an "Added by Home"
marker in their description, so they're distinguishable from manually created ones in
any calendar client, and `list_events` labels them on the way back out.

**Duplicate detection.** `create_event` checks the target day before writing. On a
match it refuses and explains, and the model asks the user; confirming re-calls the
tool with `force=true`. The confirmation happens through conversation rather than
through pending-state machinery.

**Honest application drafting.** The internship plug-in calls `match_profile` once per
job requirement and drafts bullets only from what comes back. Given a job description
listing Kubernetes experience I don't have, it lists that requirement as unmet rather
than fabricating it.

---

## A bug worth recording

Before `create_event` existed, asking Home to "add fit2102 test on 7 September"
produced: *"I have saved a note about your fit2102 test on 7 September."*

It had no calendar write tool, so it reached for the nearest thing it did have —
`add_note` — and reported success. The failure was silent and plausible-sounding,
which is the dangerous combination. **A missing capability degrades into the wrong
capability, confidently.** The fix was the tool plus an explicit instruction in the
plug-in's prompt fragment: when the user asks to schedule something, use
`create_event`, never `add_note`.

---

## Stack

| Layer | Choice |
|---|---|
| API | FastAPI + uvicorn |
| UI | Single static HTML page, no framework |
| Model | Gemini (configurable via `MODEL`) |
| Embeddings | `gemini-embedding-001`, 768 dimensions |
| Store | Postgres (Neon) + pgvector |
| Driver | psycopg 3 |
| Calendar | Google Calendar API, OAuth desktop flow |

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

Set up the schema, add notes, ingest:

```bash
python setup_db.py
mkdir input && cp notes.example.txt input/notes.txt
python ingest.py
```

For the calendar plug-in, add an OAuth desktop client's `credentials.json` to the
project root. First run opens a browser for consent and writes `token.json`.

```bash
uvicorn main:app --reload --port 8080
```

Then `http://localhost:8080`.

`input/`, `.env`, `credentials.json`, and `token.json` are gitignored.

---

## Example

<!-- PASTE TERMINAL OUTPUT FROM `python agent.py` HERE -->

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
| `plugins.py` | Plug-in dataclass and registry with name-collision detection |
| `tools.py` | Core tools, registered as the `core` plug-in |
| `calendar_plugin.py` | Google Calendar plug-in |
| `internship.py` | Internship plug-in |
| `agent.py` | The tool-calling loop |
| `main.py` | FastAPI endpoints |
| `index.html` | Chat UI |

---

## Known limitations

- **Chunking splits mid-word.** Paragraph-first, then a hard character split.
  Sentence-boundary splitting would be better; this was measured as good enough
  before optimising.
- **Duplicate detection is a substring match.** "FIT2102 test" won't match "fit2102
  exam", and it only checks the target day.
- **No true human-in-the-loop confirmation.** Tools refuse and explain rather than
  pausing for approval; real approval needs pending-action state across turns.
- **The agent over-searches.** It sometimes calls `search_notes` for information
  already in conversation history, preferring to verify against sources. Correct but
  not cheap.
- **Grounding constrains, it doesn't prevent.** Output stays close to retrieved
  content but can still infer past it — one drafted bullet named a framework implied
  by the notes rather than stated in them.
- **No vector index.** At current scale Postgres scans every row in microseconds.
  Past ~100k chunks this needs an HNSW index.
- **History is truncated, not summarised.** Turns beyond the limit are dropped rather
  than compressed.
- **Single user.** No auth; conversation IDs are unauthenticated strings.

---

## Roadmap

- Obsidian vault ingestion — markdown files through the existing chunk/embed pipeline
- Multimodal ingestion — voice memos and images via transcription and captioning
  adapters in front of the unchanged pipeline
- Mobile client
- Pending-action state for real confirmation flows
- Smarter iteration budget — cap total tool calls rather than loop turns, so parallel
  calls count correctly, and degrade to a best-effort answer from partial results
  instead of failing at the ceiling
- LLMOps layer — token and latency tracking per request, tool-use analytics from the
  existing JSONB logs
- Streaming responses
- Docker Compose for local Postgres (the connection string is already the only
  coupling point)