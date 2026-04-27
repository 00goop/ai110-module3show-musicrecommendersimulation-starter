"""MELODY — Agentic RAG music recommender.

Orchestrates a six-step reasoning chain that combines a deterministic
content-based scoring engine with Gemini-powered parsing, enrichment, and
self-critique. Each step yields a structured event so the calling UI
(Streamlit, terminal, evaluator) can stream the agent's thought process.

Reasoning chain:
    1. parse_query        — Gemini turns natural-language input into a UserProfile
    2. score_catalog      — deterministic scorer ranks all songs
    3. enrich_with_bios   — local RAG: artist bios from data/artist_bios.md
    4. enrich_with_web    — live RAG: Gemini Google Search grounding
    5. draft_response     — Gemini drafts the recommendation using all context
    6. self_critique      — Gemini reviews its own draft, outputs confidence
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Any, Iterator

from dotenv import load_dotenv
from google import genai
from google.genai import types

try:
    from recommender import load_songs, recommend_songs
except ModuleNotFoundError:
    from src.recommender import load_songs, recommend_songs


load_dotenv()

MODEL = "gemini-2.5-flash"

PERSONA = """You are MELODY, a careful music librarian agent for a curated catalog of 20 songs.

Your job is to help users discover music from THIS catalog only. You operate inside a
strict reasoning chain (parse -> score -> enrich -> draft -> critique) and follow these
rules without exception:

  RULE 1  Only recommend songs that appear in the provided catalog. Never invent titles
          or artists. If the user asks for a specific out-of-catalog song, refuse and
          explain that you only know the 20 songs in this catalog.
  RULE 2  Use the provided artist bios verbatim where they add value. Do not invent
          biographical details.
  RULE 3  Every final response ends with a self-critique that flags:
            - filter-bubble risk (all picks same genre)
            - internal conflicts in the user's request (e.g. "sad folk + high energy")
            - low-confidence picks where the score is < 2.0
  RULE 4  Always emit a confidence score 0-10 for the overall recommendation set.
  RULE 5  Be concise. The user reads the reasoning chain step-by-step in a UI; you
          don't need to repeat context they already saw.

You are NOT a general-purpose chatbot. You only handle music discovery for this catalog.
"""


# ---------------------------------------------------------------------------
# Step events — what the agent yields back to the caller
# ---------------------------------------------------------------------------

@dataclass
class StepEvent:
    """A single step in the reasoning chain, streamed to the UI."""
    step: int
    name: str
    status: str           # "running" | "done" | "error"
    summary: str          # one-line human-readable summary
    data: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Gemini helpers
# ---------------------------------------------------------------------------

def _client() -> genai.Client:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY not set. Add it to .env or export it in your shell."
        )
    return genai.Client(api_key=api_key)


def _strip_code_fence(text: str) -> str:
    """Gemini sometimes wraps JSON in ```json ... ``` even with response_mime_type."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text


# ---------------------------------------------------------------------------
# Step 1 — parse natural-language query into a UserProfile
# ---------------------------------------------------------------------------

PARSE_SCHEMA = {
    "type": "object",
    "properties": {
        "favorite_genre": {
            "type": "string",
            "enum": ["pop", "rock", "electronic", "indie", "folk", "r&b", "country"],
        },
        "favorite_mood": {
            "type": "string",
            "enum": ["happy", "chill", "energetic", "sad", "intense"],
        },
        "target_energy": {"type": "number"},
        "target_tempo": {"type": "integer"},
        "interpretation_notes": {"type": "string"},
    },
    "required": [
        "favorite_genre",
        "favorite_mood",
        "target_energy",
        "target_tempo",
        "interpretation_notes",
    ],
}


def parse_query(client: genai.Client, query: str) -> dict[str, Any]:
    """Turn a natural-language query into a structured UserProfile."""
    prompt = f"""{PERSONA}

The user said: "{query}"

Extract a UserProfile from this query. Map their words to the closest catalog
values. The catalog uses these enums:
  genres: pop, rock, electronic, indie, folk, r&b, country
  moods:  happy, chill, energetic, sad, intense

Energy is 0.0-1.0 (low to high). Tempo is in BPM (typical range 70-160).

In `interpretation_notes`, briefly explain how you mapped vague language to
concrete values (e.g. "user said 'study music' -> mapped to indie/chill/0.3/80").
Return strictly valid JSON matching the schema."""

    resp = client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=PARSE_SCHEMA,
            temperature=0.2,
        ),
    )
    return json.loads(_strip_code_fence(resp.text))


# ---------------------------------------------------------------------------
# Step 3 — local RAG: artist bios
# ---------------------------------------------------------------------------

def load_artist_bios(filepath: str | None = None) -> dict[str, str]:
    """Parse data/artist_bios.md into {artist_name: bio_text}."""
    if filepath is None:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        filepath = os.path.join(base_dir, "data", "artist_bios.md")

    with open(filepath, encoding="utf-8") as f:
        text = f.read()

    bios: dict[str, str] = {}
    current_artist: str | None = None
    current_lines: list[str] = []

    for line in text.splitlines():
        if line.startswith("## "):
            if current_artist:
                bios[current_artist] = "\n".join(current_lines).strip()
            current_artist = line[3:].strip()
            current_lines = []
        elif current_artist:
            current_lines.append(line)

    if current_artist:
        bios[current_artist] = "\n".join(current_lines).strip()

    return bios


def lookup_bios(top_recs: list, bios: dict[str, str]) -> dict[str, str]:
    """Return {artist: bio} for every artist in the top recs."""
    return {
        song["artist"]: bios.get(song["artist"], "(no bio on file)")
        for song, _score, _reasons in top_recs
    }


# ---------------------------------------------------------------------------
# Step 4 — live RAG: Gemini Google Search grounding
# ---------------------------------------------------------------------------

def enrich_with_web(client: genai.Client, profile: dict, query: str) -> dict[str, Any]:
    """Use Gemini's Google Search grounding to fetch real-world context.

    Returns the grounded text plus the source URLs Gemini cited. This is the
    second RAG source — live web data complementing the local artist bios.
    """
    grounding_query = (
        f"What real-world music or playlist context is relevant for someone who "
        f"asked: '{query}' and prefers {profile['favorite_genre']} {profile['favorite_mood']} "
        f"music at energy {profile['target_energy']:.1f} and {profile['target_tempo']} BPM? "
        f"Reply in 2-3 sentences with concrete musical reference points."
    )

    resp = client.models.generate_content(
        model=MODEL,
        contents=grounding_query,
        config=types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())],
            temperature=0.3,
        ),
    )

    sources: list[str] = []
    if resp.candidates and resp.candidates[0].grounding_metadata:
        gm = resp.candidates[0].grounding_metadata
        if gm.grounding_chunks:
            for chunk in gm.grounding_chunks:
                if chunk.web and chunk.web.uri:
                    sources.append(chunk.web.uri)

    return {"text": resp.text, "sources": sources}


# ---------------------------------------------------------------------------
# Step 5 — draft the final recommendation
# ---------------------------------------------------------------------------

def draft_response(
    client: genai.Client,
    query: str,
    profile: dict,
    top_recs: list,
    bios: dict[str, str],
    web: dict[str, Any],
) -> str:
    """Compose the user-facing recommendation using everything we've gathered."""
    rec_lines = []
    for rank, (song, score, reasons) in enumerate(top_recs, start=1):
        rec_lines.append(
            f"  #{rank} {song['title']} by {song['artist']} "
            f"(genre={song['genre']}, mood={song['mood']}, "
            f"energy={song['energy']}, tempo={song['tempo_bpm']}) "
            f"- score {score:.2f} - reasons: {', '.join(reasons)}"
        )
    rec_block = "\n".join(rec_lines)

    bio_block = "\n".join(f"  - {a}: {b}" for a, b in bios.items())

    prompt = f"""{PERSONA}

USER QUERY: "{query}"

PARSED PROFILE: {json.dumps(profile, indent=2)}

TOP-K CANDIDATES FROM SCORING ENGINE:
{rec_block}

LOCAL ARTIST BIOS (RAG source #1):
{bio_block}

LIVE WEB CONTEXT (RAG source #2 — Gemini Google Search):
{web['text']}

Write a recommendation in this exact format:

  Profile interpretation: <one sentence on how you read the user's request>

  Top picks:
    1. <Title> by <Artist> - <one sentence using the bio + score reasoning>
    2. ...
    (up to 5)

  Why these fit: <2-3 sentences tying picks back to the parsed profile>

Do NOT include the self-critique here — that comes in the next step. Be concise.
"""

    resp = client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(temperature=0.4),
    )
    return resp.text.strip()


# ---------------------------------------------------------------------------
# Step 6 — self-critique
# ---------------------------------------------------------------------------

CRITIQUE_SCHEMA = {
    "type": "object",
    "properties": {
        "hallucination_check": {"type": "string"},
        "filter_bubble_check": {"type": "string"},
        "conflict_check": {"type": "string"},
        "low_confidence_picks": {"type": "string"},
        "confidence_score": {"type": "integer"},
        "revised_summary": {"type": "string"},
    },
    "required": [
        "hallucination_check",
        "filter_bubble_check",
        "conflict_check",
        "low_confidence_picks",
        "confidence_score",
        "revised_summary",
    ],
}


def self_critique(
    client: genai.Client,
    query: str,
    profile: dict,
    top_recs: list,
    draft: str,
    full_catalog: list[dict],
) -> dict[str, Any]:
    """Have Gemini review its own draft for hallucinations, filter bubble, etc."""
    valid_pairs = [
        f"  - '{song['title']}' by '{song['artist']}'"
        for song in full_catalog
    ]
    valid_block = "\n".join(valid_pairs)

    genres = [song["genre"] for song, _, _ in top_recs]
    low_score_picks = [
        f"{song['title']} (score {score:.2f})"
        for song, score, _ in top_recs
        if score < 2.0
    ]

    prompt = f"""{PERSONA}

You drafted the following recommendation. Now critique YOUR OWN draft.

ORIGINAL QUERY: "{query}"
PARSED PROFILE: {json.dumps(profile)}

YOUR DRAFT:
\"\"\"
{draft}
\"\"\"

THE FULL CATALOG (these are the ONLY valid title/artist pairs — anything in
your draft NOT in this list is a hallucination):
{valid_block}

Genres in your top picks: {genres}
Picks with score < 2.0 (low confidence): {low_score_picks or 'none'}

Critique on these axes (return JSON matching the schema):
  hallucination_check    — Scan your draft for any song title or artist name. If
                           every (title, artist) pair you mentioned appears in the
                           full catalog above, return "clean". Otherwise quote the
                           offending phrase. Do NOT count valid catalog artists as
                           hallucinations.
  filter_bubble_check    — Are all your picks the same genre? If yes, flag it.
  conflict_check         — Did the user's request have an internal conflict
                           (e.g. asking for sad folk at high energy)? Did you address it?
                           Also: did the user name a SPECIFIC artist (e.g. "Taylor Swift")
                           who is not in the catalog? If yes, flag that as a conflict and
                           lower confidence accordingly.
  low_confidence_picks   — Did you flag the low-score picks to the user? Why or why not?
  confidence_score       — Integer 0-10 reflecting how well the recommendation matches
                           the user's actual request. Low scores for: edge-case profiles
                           the catalog can't satisfy, requests for specific out-of-catalog
                           artists, or genre/mood/energy conflicts.
  revised_summary        — A 1-2 sentence revised takeaway the UI will show as the
                           final answer. Incorporate any flags you raised.
"""

    resp = client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=CRITIQUE_SCHEMA,
            temperature=0.2,
        ),
    )
    return json.loads(_strip_code_fence(resp.text))


# ---------------------------------------------------------------------------
# Main agent loop — yields StepEvents
# ---------------------------------------------------------------------------

class MusicAgent:
    """Stateful agent that runs the six-step reasoning chain."""

    def __init__(self, k: int = 5):
        self.client = _client()
        self.songs = load_songs()
        self.bios = load_artist_bios()
        self.k = k

    def run(self, query: str) -> Iterator[StepEvent]:
        # Step 1 — parse
        yield StepEvent(1, "Parse query", "running",
                        f"Asking Gemini to extract a UserProfile from: {query!r}")
        try:
            profile = parse_query(self.client, query)
        except Exception as e:
            yield StepEvent(1, "Parse query", "error", f"Parse failed: {e}")
            return
        yield StepEvent(
            1, "Parse query", "done",
            f"Profile: {profile['favorite_genre']} / {profile['favorite_mood']} / "
            f"energy={profile['target_energy']} / tempo={profile['target_tempo']}",
            data={"profile": profile},
        )

        # Step 2 — score catalog (deterministic)
        yield StepEvent(2, "Score catalog", "running",
                        f"Running deterministic scorer over {len(self.songs)} songs")
        top_recs = recommend_songs(profile, self.songs, k=self.k)
        yield StepEvent(
            2, "Score catalog", "done",
            f"Top pick: {top_recs[0][0]['title']} (score {top_recs[0][1]:.2f})",
            data={"top_recs": [
                {"song": s, "score": sc, "reasons": rs}
                for s, sc, rs in top_recs
            ]},
        )

        # Step 3 — local RAG (artist bios)
        yield StepEvent(3, "Retrieve artist bios (local RAG)", "running",
                        f"Looking up bios for {len(top_recs)} artists in data/artist_bios.md")
        bios_for_recs = lookup_bios(top_recs, self.bios)
        yield StepEvent(
            3, "Retrieve artist bios (local RAG)", "done",
            f"Loaded {len(bios_for_recs)} bios",
            data={"bios": bios_for_recs},
        )

        # Step 4 — live RAG (Google Search grounding)
        yield StepEvent(4, "Web search context (live RAG)", "running",
                        "Calling Gemini with Google Search grounding for live context")
        try:
            web = enrich_with_web(self.client, profile, query)
        except Exception as e:
            web = {"text": f"(web grounding unavailable: {e})", "sources": []}
        yield StepEvent(
            4, "Web search context (live RAG)", "done",
            f"Got {len(web['sources'])} web sources",
            data={"web": web},
        )

        # Step 5 — draft
        yield StepEvent(5, "Draft recommendation", "running",
                        "Asking Gemini to compose the recommendation")
        try:
            draft = draft_response(
                self.client, query, profile, top_recs, bios_for_recs, web
            )
        except Exception as e:
            yield StepEvent(5, "Draft recommendation", "error", f"Draft failed: {e}")
            return
        yield StepEvent(5, "Draft recommendation", "done",
                        "Draft written", data={"draft": draft})

        # Step 6 — self-critique
        yield StepEvent(6, "Self-critique", "running",
                        "Gemini reviews its own draft for hallucinations and bias")
        try:
            critique = self_critique(self.client, query, profile, top_recs, draft, self.songs)
        except Exception as e:
            yield StepEvent(6, "Self-critique", "error", f"Critique failed: {e}")
            return
        yield StepEvent(
            6, "Self-critique", "done",
            f"Confidence: {critique['confidence_score']}/10",
            data={"critique": critique, "final": critique["revised_summary"]},
        )


# ---------------------------------------------------------------------------
# Terminal entrypoint — prints the reasoning chain
# ---------------------------------------------------------------------------

def run_terminal(query: str) -> None:
    agent = MusicAgent()
    for event in agent.run(query):
        marker = {"running": "...", "done": " ok", "error": "ERR"}[event.status]
        print(f"[Step {event.step} {marker}] {event.name}: {event.summary}")
        if event.status == "done" and event.step == 5:
            print("\n--- DRAFT ---")
            print(event.data["draft"])
            print("--- /DRAFT ---\n")
        if event.status == "done" and event.step == 6:
            c = event.data["critique"]
            print("\n--- CRITIQUE ---")
            print(f"Hallucination check  : {c['hallucination_check']}")
            print(f"Filter bubble check  : {c['filter_bubble_check']}")
            print(f"Conflict check       : {c['conflict_check']}")
            print(f"Low confidence picks : {c['low_confidence_picks']}")
            print(f"Confidence score     : {c['confidence_score']}/10")
            print(f"\nFinal: {c['revised_summary']}")
            print("--- /CRITIQUE ---")


if __name__ == "__main__":
    import sys
    q = " ".join(sys.argv[1:]) or "I want chill indie music for studying"
    run_terminal(q)
