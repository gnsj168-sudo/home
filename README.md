# Home

A personal assistant platform with retrieval over my own notes, a hand-written
tool-calling loop, and a plug-in interface for adding new capabilities.

Four plug-ins run on it today:

| Plug-in | Tools |
|---|---|
| **core** | `search_notes`, `add_note`, `get_current_time` |
| **calendar** | `list_events`, `create_event` |
| **notion** | `search_notion`, `read_notion_page`, `create_notion_page` |
| **internship** | `match_profile` |

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
        +-------+-------+-------+-------+
        |       |       |               |
      core   calendar  notion      internship
        |       |       |               |
        |   Calendar   Notion           |
        |     API       API             |
        +-------+---------------+-------+
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
Notes and documents are chunked and embedded — large, stable, and helped by semantic
search. Calendar and Notion content is fetched live on every query and never
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
the same interface, so the built-in case isn't a special case. Adding the Notion
plug-in was one import and one `register()` call.

**Tools are for capabilities the model lacks.**
The internship plug-in has one tool, not three. Parsing a job description and writing
bullets are things the model already does; only `match_profile` touches the database,
so only it needs to exist. The rest is prompt.

**Discovery tools, because ids aren't guessable.**
Notion pages are UUIDs the model cannot invent, so `search_notion` exists purely to
hand it a real id before `read_notion_page` or `create_notion_page` can run. The
model chains them on its own; nothing in the code links the two calls.

**Least-privilege scopes.**
Calendar started at `calendar.readonly` and moved to `calendar.events` only when
writing was added. The Notion connection is an internal access token that sees
nothing until specific pages are shared with it — a narrower model than Calendar's
all-or-nothing scope.

**Provenance on everything written.**
Calendar events created by Home carry an "Added by Home" marker in their description,
and `list_events` labels them on the way back out. Notion pages get a "Created by
Home" line. Agent-written chunks are stored with `source='home-agent'`. In every
case I can tell later what I wrote and what the agent did.

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
Model output flows into the browser alongside retrieved chunks, calendar events, and
Notion content — text I didn't write. Rendering it as HTML is an injection surface
that needs a sanitiser, not just a parser. The system prompt asks for plain text
instead: no new dependency, no new attack surface.

---

## What it does

**Grounded question answering.** Answers come from ingested notes with chunk-level
citations. Asked "what is the capital of France?", it returns nothing — the model
knows, but the context doesn't contain it, and the guard rejects the query before the
API call.

**Multi-tool dispatch across plug-ins.** The model selects among nine tools from four
plug-ins based on their descriptions alone.

**Tool chaining.** "What's on my calendar this week?" calls `get_current_time` (core)
to learn today's date, then `list_events` (calendar) with real computed dates.
"What's in my Notion?" calls `search_notion` for an id, then `read_notion_page`.
Nothing in the code links those pairs — the chaining comes out of the loop.

**Self-extending knowledge.** `add_note` chunks, embeds, and stores new information
through the same pipeline as file ingestion. The agent writes to its own knowledge
base and retrieves from it in later turns.

**Conversation memory.** Follow-ups resolve against history — "and what hardware did I
run it on?" becomes a search for the subject established two turns earlier.

**Calendar and Notion writes**, both marked with their origin, both reachable in plain
language: "add fit2102 test on 7 September", "create a Notion page called X".

**Duplicate detection.** `create_event` checks the target day before writing. On a
match it refuses and explains, and the model asks the user; confirming re-calls the
tool with `force=true`. The confirmation happens through conversation rather than
through pending-state machinery.

**Honest application drafting.** The internship plug-in calls `match_profile` once per
job requirement and drafts bullets only from what comes back. Given a job description
listing Kubernetes experience I don't have, it lists that requirement as unmet rather
than fabricating it.

---

## Three bugs worth recording

**A missing capability degrades into the wrong capability.**
Before `create_event` existed, "add fit2102 test on 7 September" produced: *"I have
saved a note about your fit2102 test on 7 September."* With no calendar write tool,
the model reached for the nearest thing it had — `add_note` — and reported success.
Silent, plausible-sounding, wrong. Fixed with the tool plus an explicit instruction in
the plug-in's prompt fragment.

**Overlapping tool descriptions cause silent mis-dispatch.**
After adding Notion, "what's my to-do list?" kept returning results from the embedded
notes, because `search_notes` was described as searching "the user's notes" — and
Notion is also notes. The model never errored; it picked one source and answered
confidently. Fixed by narrowing the core tool's description to exclude Notion
explicitly, and adding routing guidance to the base prompt. Same shape as the first
bug: as plug-ins accumulate, tool descriptions become a namespace that needs managing.

**The model can return no text at all.**
`response.text` came back `None` on a response with no text part, and the null landed
in a NOT NULL column — the database constraint is what surfaced it, several turns
later. The loop had assumed that "no function call" implies "has text". Now guarded at
the boundary where model output meets storage.

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
| Notion | Notion API, internal connection token |

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
NOTION_TOKEN=ntn_...
NOTION_PARENT_PAGE_ID=...
```

Set up the schema, add notes, ingest:

```bash
python setup_db.py
mkdir input && cp notes.example.txt input/notes.txt
python ingest.py
```

For the calendar plug-in, put an OAuth desktop client's `credentials.json` in the
project root; the first run opens a browser for consent and writes `token.json`. For
Notion, create an internal connection and share at least one page with it — the
integration sees nothing until you do.

```bash
uvicorn main:app --reload --port 8080
```

Then `http://localhost:8080`.

`input/`, `.env`, `credentials.json`, and `token.json` are gitignored.

---

## Example

<!-- PASTE TERMINAL OUTPUT FROM `python agent.py` HERE -->
<!-- best demo: "what's on my calendar this week?" - shows cross-plugin chaining -->

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
| `notion_plugin.py` | Notion plug-in |
| `internship.py` | Internship plug-in |
| `agent.py` | The tool-calling loop |
| `main.py` | FastAPI endpoints |
| `index.html` | Chat UI |

---

## Known limitations

- **Chunking splits mid-word.** Paragraph-first, then a hard character split.
  Sentence-boundary splitting would be better; measured as good enough before
  optimising.
- **Duplicate detection is a substring match.** "FIT2102 test" won't match "fit2102
  exam", and it only checks the target day.
- **No true human-in-the-loop confirmation.** Tools refuse and explain rather than
  pausing for approval; real approval needs pending-action state across turns.
- **Tool routing is prompt-level.** Source disambiguation lives in descriptions and
  the base prompt, not in code. It works, but it degrades as tools accumulate.
- **The agent over-searches — and sometimes under-searches.** It will re-query a
  source for something already in conversation history, and occasionally answer from
  history when it should re-query. Both failure directions are live.
- **Grounding constrains, it doesn't prevent.** Output stays close to retrieved
  content but can still infer past it — one drafted bullet named a framework implied
  by the notes rather than stated in them.
- **No vector index.** At current scale Postgres scans every row in microseconds.
  Past ~100k chunks this needs an HNSW index.
- **History is truncated, not summarised.** Turns beyond the limit are dropped.
- **Single user.** No auth; conversation IDs are unauthenticated strings.

---

## Roadmap

- Multimodal input — images and voice memos through captioning and transcription
  adapters in front of the unchanged chunk/embed pipeline
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