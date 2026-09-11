# Model Card — MELODY 2.0 (VibeFinder + Agentic RAG)

## 1. System Name

**MELODY 2.0** — an Agentic RAG music recommender that wraps the original
VibeFinder content-based scoring engine with a Gemini-powered reasoning chain,
multi-source retrieval, and a self-critique loop.

The deterministic scoring engine from VibeFinder 1.0 is preserved unchanged
inside [src/recommender.py](src/recommender.py) and is called as a tool by the
agent at step 2 of the chain.

## 2. Goal / Task

Take a **natural-language** music request from the user (e.g. "I need chill
indie music for studying") and return ranked recommendations from the catalog
with a transparent reasoning trace, retrieved evidence, and a confidence score.

The agent is intentionally **narrow**: it only handles music discovery for the
20-song catalog. It refuses out-of-domain requests by design.

## 3. Components

### 3a. Deterministic scoring engine (preserved from VibeFinder 1.0)

Same algorithm as before — genre +2.0, mood +1.0, energy similarity 0–1.0,
tempo bonus +0.5. Implemented in [src/recommender.py](src/recommender.py:24).

### 3b. Agent (`src/agent.py`)

A six-step reasoning chain orchestrated in Python (not a free-form ReAct loop).
Each step yields a `StepEvent` so the calling UI can render the chain live:

| # | Step | Powered by | Purpose |
|---|------|------------|---------|
| 1 | Parse query | Gemini 2.5 Flash + JSON schema | Turn natural language into a `UserProfile` |
| 2 | Score catalog | Pure Python (deterministic) | Rank all 20 songs |
| 3 | Retrieve artist bios | Local file lookup | RAG source #1 |
| 4 | Web search context | Gemini Google Search grounding | RAG source #2 |
| 5 | Draft recommendation | Gemini 2.5 Flash | Compose final answer |
| 6 | Self-critique | Gemini 2.5 Flash + JSON schema | Detect hallucinations, filter bubbles, conflicts |

The orchestration is in code (not LLM-decided) so the reasoning chain is
predictable — important for a teaching demo where the rubric requires a
visible thought process.

### 3c. Persona / System Prompt

The agent uses a strict librarian persona (see `PERSONA` in
[src/agent.py:31-50](src/agent.py#L31-L50)) with five explicit rules:

  1. Only recommend songs from the catalog (no invented titles).
  2. Use bios verbatim where they add value (no invented bios).
  3. Every response ends with self-critique flagging filter bubble, conflicts,
     low-confidence picks.
  4. Always emit a confidence score 0–10.
  5. Be concise — the UI already shows the reasoning chain.

This is **measurably different** from a generic chatbot: when asked
"Recommend me some Taylor Swift," the agent maps the request to a catalog
profile and explicitly notes that Taylor Swift is not in the catalog with a
lower confidence score (4/10 in evaluation) — a generic Gemini chat happily
invents Taylor Swift discography.

## 4. Data and Knowledge Sources

| Source | Type | Used in step | File |
|--------|------|--------------|------|
| Song catalog | structured CSV (20 rows) | 2 (scoring) | [data/songs.csv](data/songs.csv) |
| Artist bios | local Markdown | 3 (RAG #1) | [data/artist_bios.md](data/artist_bios.md) |
| Live web context | Google Search grounding | 4 (RAG #2) | (Gemini built-in) |

Two RAG sources, as required by the rubric. The local bios are deterministic
and grounded in the simulation universe; the web search is non-deterministic
and adds real-world references the agent cites with URLs.

## 5. Evaluation Methodology

The system is evaluated by [evaluator.py](evaluator.py) against **5 golden
inputs** covering both happy paths and edge cases:

| # | Name | Tests |
|---|------|-------|
| 1 | happy_pop_workout | Standard request, expect strong matches |
| 2 | chill_indie_study | Standard request, low-energy expectations |
| 3 | intense_rock | Standard request, narrow catalog subset |
| 4 | edge_case_conflict | "Sad folk + high energy" — internally inconsistent |
| 5 | edge_case_out_of_catalog | "Recommend Taylor Swift" — not in catalog |

For each golden, a **separate Gemini judge** (different prompt, lower
temperature) scores the agent's full trace against pre-declared pass/fail
criteria. The judge uses a separate prompt, but the same model family; this may reduce
self-grading bias.

**Historical saved run:** 19/19 model-judged criteria passed — see
[eval_report.md](eval_report.md). This was achieved after fixing one prompt
bug discovered during the first eval run (the self-critique step was passing
only song titles, not (title, artist) pairs, causing false-positive
hallucination flags on valid catalog artists).

## 6. Observed Failure Modes (honest)

Even with 100% on the criteria above, the agent has clear limitations that the
evaluation surfaced or that I observed during development:

1. **The agent flags filter bubbles but cannot prevent them.** Every
   genre-aligned query (chill indie, happy pop, intense rock) returned a top-5
   list dominated by one genre. The self-critique reliably reports this, but
   the underlying scorer keeps picking the same genre because the +2.0 genre
   weight is structural. Mitigation would require re-weighting or adding a
   diversity term — neither is implemented.

2. **Sad-folk-high-energy is unsatisfiable in this catalog.** The conflict
   golden gets confidence 3/10 because no folk song in the catalog is both sad
   AND high-energy. The agent surfaces the conflict cleanly, but the user
   still gets recommendations they didn't ask for. This is a catalog limit,
   not a model limit.

3. **Specific-artist requests get mapped to a generic profile.** Given
   "Taylor Swift," the parser produces `{pop, energetic, 0.7, 120}` and
   continues. The self-critique now correctly flags the mismatch and lowers
   confidence to 4/10, but the agent never refuses outright — the rubric
   would arguably prefer a refusal here. Trade-off: refusing on every unknown
   artist would block useful adjacent recommendations.

4. **The web RAG step is non-deterministic and occasionally adds little.**
   Some runs return only generic music writing that doesn't sharpen the
   recommendation. It's still useful to demonstrate live grounding, but for a
   production system I would gate the call behind a relevance check.

5. **Gemini structured output sometimes wraps JSON in code fences.** Even with
   `response_mime_type="application/json"` set. I work around this with a
   `_strip_code_fence` helper in [src/agent.py:96-101](src/agent.py#L96-L101).
   Worth knowing for any future work with this SDK.

6. **The judge model is the same family as the agent** (both Gemini 2.5 Flash).
   This introduces correlated bias — the judge may share the agent's blind
   spots. A more rigorous eval would use a different model family (e.g.
   Claude or GPT) as the independent judge.

## 7. Intended Use and Non-Intended Use

**Intended use:**
- Educational demonstration of an Agentic RAG system end-to-end.
- Showing how a deterministic scoring engine can be embedded as a tool inside
  an LLM-orchestrated workflow.
- Stress-testing how a small system handles ambiguous, conflicting, and
  out-of-scope inputs.

**NOT intended for:**
- Real music recommendation — the catalog is fictional and 20 songs.
- Any high-stakes decision where a self-graded confidence score is treated as
  ground truth (see failure mode #6).
- A chat product — the agent is narrow on purpose and will refuse off-topic
  requests.

## 8. Ideas for Improvement

1. **Diversity reranker** as step 5.5 — penalize multiple picks from the same
   genre to break the filter bubble the agent already flags.
2. **Independent judge model** — swap the evaluator's Gemini call for a
   different family (Claude or GPT-4) to remove correlated bias.
3. **Tool-calling loop** instead of fixed orchestration — let the agent decide
   when to call web search vs. when local bios suffice. Trade-off: less
   predictable reasoning chain (worse for a demo, better for production).
4. **Genre similarity matrix** so indie ↔ folk gets partial credit instead of
   binary match/no-match (carried over from VibeFinder 1.0 model card).
5. **Real catalog** — Spotify API for song metadata (danceability, valence)
   would give the scorer more signal and reduce filter bubble.

## Portfolio verification boundary

Normal CI runs only deterministic scorer and evaluation-accounting tests with no
API keys. The saved 19/19 result is historical, small-sample and model-judged; it
has not been rerun in this modernization and is not a general accuracy estimate.
The evaluator now counts failed agent runs in the planned denominator and rejects
missing, duplicate or unknown judgment criteria. Confidence is model self-assessment,
not calibrated probability. Agent stages are a fixed workflow, not autonomous tool
selection. Live web retrieval and Gemini evaluation remain optional manual runs.
