# Superjoin — Fact Knowledge Layer

A fact knowledge layer over PDF documents. It extracts atomic facts, grounds each
one in the exact span of source text it came from, and flags when facts across
documents agree, conflict, or are explained by context (time period, scope,
units, reporting basis).

## Setup and Run Instructions

### Prerequisites

- **Docker Desktop** — https://www.docker.com/get-started (runs Postgres).
- **Python 3.11 or newer.**
- **Node.js 20 LTS** (18+ works).
- **Ollama** — https://ollama.com/download. After installing, pull the local
  model used for the fallback and the second-opinion extraction:
  ```
  ollama pull llama3.2:3b
  ```
- **Tesseract OCR** — optional. Only used for scanned pages; the sample PDFs are
  text-based, so you can skip it.

### 1. Start the database

From the repo root:
```
docker compose up -d db
```
This runs PostgreSQL 16 with the pgvector extension on host port **5433**.

### 2. Backend

```
cd backend
python -m venv .venv
# Windows:        .venv\Scripts\activate
# macOS / Linux:  source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

Get a **free** Groq API key (no credit card) at
https://console.groq.com and put it in `.env`:
```
GROQ_API_KEY=your-key-here
```

Then run the migrations and start the server:
```
python -m scripts.db upgrade
python -m uvicorn app.main:app --reload --port 8000
```
The first start downloads the local embedding model (`BAAI/bge-small-en-v1.5`,
about 130 MB).


### 3. Frontend

```
cd frontend
npm install
npm run dev
```
Opens http://localhost:5173. It talks to `http://localhost:8000` by default. To
point it elsewhere, set `VITE_API_BASE` in `frontend/.env.local`.

### 4. Confirm it works

Open http://localhost:5173, create a project, and upload the PDFs to be tested against. Watch it move through processing, then open the **Facts** tab and
click any fact — the evidence panel shows the exact highlighted span in the
source page.

## Video Demo

https://www.loom.com/share/87131f8e772e4ee49df98db656dab8f1

## Approach

A PDF is read page by page (text in reading order, tables as structure, OCR only
for pages with no text layer) and split into chunks with a little trailing
context. Each chunk goes to the model once under a strict schema: every fact
comes back as one of three kinds (quantitative, status, qualitative) with an
evidence quote, anchored to exact character offsets in the source. A fact is
kept only if that quote is a literal substring of the page and a second,
independent model call agrees the quote supports the claim. A value the
extractor never marked exact is stored as approximate, and any convention it had
to assume — a fiscal-year start, a missing comparator, an inferred entity —
lowers that fact's confidence.

Every new fact is then checked against the rest of the project. That check
escalates.

**No model call.** A deterministic pre-check normalises units, scales, and
periods and only ever confirms outright agreement — the same number after a
conversion, the same status. Anything it cannot settle it hands up.

**One model call.** An adjudicator classifies the pair as corroborates,
contradicts, reconciled_by_context, or unrelated, working through entity,
attribute, period, scale, qualifiers, and comparator in a fixed order.

**An agent.** When the adjudicator says a targeted lookup could still change the
verdict, a reconciliation agent gets three read-only tool calls —
`search_facts`, `search_evidence_text`, `get_surrounding_context` — with every
call and result written to an investigation trail. When the budget runs out it
is forced to classify with what it has.

A separate agent backs the reasoning console. It answers an open question against
the verified facts using up to five `search_facts` / `get_relationships` calls,
then writes an answer with citations and any disagreements it found — a different
agent solving a different problem.

Running these LLM paths against a free, rate-limited tier drove the operational
choices: requests are capped in flight and spaced apart, and a call falls back
from Groq to a local Ollama model on a rate limit, timeout, or auth/transport
error only.

Trade-offs worth knowing: the strongest check — a blind second extraction on the
other provider, reconciled through the same pre-check — runs on a subset of
facts for cost; confidence scores use fixed hand-set constants, not calibration;
cross-document concept matching is resolved one pair at a time and cached.

AI tool used : Claude Code

## Limitations and Next Steps

**What doesn't work yet**

- The fact schema is fixed to three kinds — quantitative, status, qualitative.
  It does not grow new fact types as new kinds of claim appear, which the
  assignment lists as a stretch goal.
- Cross-document entity and concept matching is done one pair at a time and
  cached. It is untested at a document count where that stops being cheap.
- The reconciliation agent has a hard three-call budget. When it runs out
  without finding a resolving fact it still returns a classification, so some
  verdicts are a best guess under a tool budget rather than a confirmed
  resolution — and that distinction is not surfaced in the UI.
- Confidence scoring uses fixed, hand-set constants: a flat penalty per assumed
  convention, a flat agree/disagree adjustment. Nothing is calibrated against
  known outcomes, so facts with very different real reliability can land on
  similar scores.
- The blind second extraction, the strongest check available, only runs on a
  subset of facts.
- Large-document processing has a fast-path and a per-document timeout, but
  sustained performance and multi-PDF scaling — both explicit stretch goals —
  are not benchmarked.
- A fact missed on a page is not detected or measured anywhere, and a page whose
  OCR or table extraction silently produced little shows only in the logs.

**Planned next**

- A fact schema that can grow new fact kinds as new claim types appear.
- Benchmarking large-PDF and multi-document scaling, including the pairwise
  concept matcher at higher document counts.
- Calibrating confidence scores against real extraction and comparison outcomes.
- Running the blind second extraction on every fact, not just a subset.
- Surfacing pages with reduced extraction confidence in the UI, and adding a
  page-level completeness check — numbers, dates, and currency mentions found
  versus extracted.

## Additional Notes

