"""Evaluator — runs MELODY against 5 golden inputs and has Gemini judge each run.

This is the test harness required by the rubric. For each golden input we:
  1. Run the agent end-to-end and capture every step.
  2. Send the full transcript + the golden criteria to a separate "judge" Gemini
     call that scores each criterion pass/fail with a short rationale.
  3. Aggregate to a final report (printed + written to eval_report.md).

The judge call uses a different prompt and lower temperature than the agent so
the evaluation is independent of the recommender persona.

Run with:
    python evaluator.py
"""

from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime

from dotenv import load_dotenv
from google import genai
from google.genai import types

from src.agent import MODEL, MusicAgent

load_dotenv()


# ---------------------------------------------------------------------------
# Golden inputs — each is a query + a list of binary criteria the agent must meet
# ---------------------------------------------------------------------------

GOLDEN: list[dict] = [
    {
        "name": "happy_pop_workout",
        "query": "Give me high-energy happy pop for a workout",
        "criteria": [
            "At least 2 of the top 5 picks have genre 'pop'",
            "At least 1 pick has mood 'happy'",
            "Top pick has score >= 4.0",
            "Confidence score is >= 7",
            "Hallucination check returned 'clean' or equivalent (no out-of-catalog songs)",
        ],
    },
    {
        "name": "chill_indie_study",
        "query": "I need chill indie music for studying",
        "criteria": [
            "Top pick is one of: Code & Coffee, Deep Focus, Lullaby Lane, Rainy Thoughts",
            "All top 5 picks have energy <= 0.5",
            "Confidence score >= 7",
            "Hallucination check is clean",
        ],
    },
    {
        "name": "intense_rock",
        "query": "Heavy intense rock for late-night driving",
        "criteria": [
            "At least 2 of the top 5 picks have genre 'rock'",
            "At least 1 pick has mood 'intense'",
            "Top pick has score >= 3.5",
            "Confidence score >= 6",
        ],
    },
    {
        "name": "edge_case_conflict",
        "query": "Sad folk songs but with really high energy and a fast tempo",
        "criteria": [
            "Critique flags an internal conflict in the user's request "
            "(folk+sad is low-energy but user asked for high-energy/fast tempo)",
            "Confidence score is <= 6 because the catalog cannot satisfy this well",
            "Hallucination check is clean (no invented songs)",
        ],
    },
    {
        "name": "edge_case_out_of_catalog",
        "query": "Recommend me some Taylor Swift",
        "criteria": [
            "Final answer makes clear that Taylor Swift is not in the catalog "
            "OR returns generic catalog picks rather than inventing Taylor Swift songs",
            "Hallucination check is clean — no fabricated Taylor Swift titles",
            "Confidence score reflects the mismatch (<= 6)",
        ],
    },
]


# ---------------------------------------------------------------------------
# Judge — independent Gemini call that scores the agent's run against criteria
# ---------------------------------------------------------------------------

JUDGE_PROMPT = """You are an impartial evaluator for an AI music recommender system.

You will be given:
  1. A user query.
  2. The agent's full reasoning trace (parsed profile, top picks with scores,
     final draft, self-critique, confidence score).
  3. A list of pass/fail criteria.

For each criterion, decide PASS or FAIL based strictly on the trace. Be strict
but fair — if the trace doesn't have evidence for the criterion, that's a FAIL.

Return JSON matching the schema. Keep rationales under 25 words each.
"""

JUDGE_SCHEMA = {
    "type": "object",
    "properties": {
        "results": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "criterion": {"type": "string"},
                    "verdict": {"type": "string", "enum": ["PASS", "FAIL"]},
                    "rationale": {"type": "string"},
                },
                "required": ["criterion", "verdict", "rationale"],
            },
        },
        "overall_pass_rate": {"type": "number"},
        "summary": {"type": "string"},
    },
    "required": ["results", "overall_pass_rate", "summary"],
}


def _strip_code_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text


def judge_run(client: genai.Client, query: str, trace: dict, criteria: list[str]) -> dict:
    payload = {
        "user_query": query,
        "trace": trace,
        "criteria": criteria,
    }
    resp = client.models.generate_content(
        model=MODEL,
        contents=JUDGE_PROMPT + "\n\n" + json.dumps(payload, indent=2, default=str),
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=JUDGE_SCHEMA,
            temperature=0.1,
        ),
    )
    return json.loads(_strip_code_fence(resp.text))


# ---------------------------------------------------------------------------
# Run a single golden through the agent and collect a trace
# ---------------------------------------------------------------------------

def run_one(agent: MusicAgent, golden: dict) -> dict:
    """Execute the agent for one golden and condense the events into a trace dict."""
    trace: dict = {
        "profile": None,
        "top_recs": [],
        "draft": None,
        "critique": None,
        "errors": [],
    }
    for event in agent.run(golden["query"]):
        if event.status == "error":
            trace["errors"].append(f"step {event.step} ({event.name}): {event.summary}")
            continue
        if event.status != "done":
            continue
        if event.step == 1:
            trace["profile"] = event.data["profile"]
        elif event.step == 2:
            trace["top_recs"] = event.data["top_recs"]
        elif event.step == 5:
            trace["draft"] = event.data["draft"]
        elif event.step == 6:
            trace["critique"] = event.data["critique"]
    return trace


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    if not os.environ.get("GEMINI_API_KEY"):
        raise SystemExit("GEMINI_API_KEY not set. Add to .env.")

    print(f"MELODY evaluator — running {len(GOLDEN)} golden inputs\n")
    agent = MusicAgent()
    judge_client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

    report_lines: list[str] = [
        "# MELODY Evaluation Report",
        "",
        f"_Generated {datetime.now().isoformat(timespec='seconds')} — model: {MODEL}_",
        "",
    ]
    overall_pass = 0
    overall_total = 0

    for i, golden in enumerate(GOLDEN, start=1):
        print(f"[{i}/{len(GOLDEN)}] {golden['name']}: {golden['query']!r}")
        t0 = time.time()
        trace = run_one(agent, golden)
        elapsed = time.time() - t0
        print(f"    agent run: {elapsed:.1f}s, errors: {len(trace['errors'])}")

        if trace["errors"]:
            report_lines += [
                f"## {i}. {golden['name']}",
                f"**Query:** {golden['query']}",
                "",
                "**ERRORS:**",
                *[f"- {e}" for e in trace["errors"]],
                "",
            ]
            continue

        verdict = judge_run(judge_client, golden["query"], trace, golden["criteria"])
        passed = sum(1 for r in verdict["results"] if r["verdict"] == "PASS")
        total = len(verdict["results"])
        overall_pass += passed
        overall_total += total
        print(f"    judge: {passed}/{total} criteria passed "
              f"(confidence {trace['critique']['confidence_score']}/10)\n")

        report_lines += [
            f"## {i}. {golden['name']}  —  {passed}/{total} criteria passed",
            f"**Query:** {golden['query']}",
            f"**Profile parsed:** `{json.dumps(trace['profile'])}`",
            f"**Confidence:** {trace['critique']['confidence_score']}/10",
            "",
            "### Top picks",
        ]
        for j, rec in enumerate(trace["top_recs"], start=1):
            s = rec["song"]
            report_lines.append(
                f"{j}. **{s['title']}** by *{s['artist']}* — score {rec['score']:.2f} "
                f"({s['genre']}/{s['mood']}, energy {s['energy']}, {s['tempo_bpm']} BPM)"
            )
        report_lines += [
            "",
            "### Final answer (after self-critique)",
            f"> {trace['critique']['revised_summary']}",
            "",
            "### Judge results",
        ]
        for r in verdict["results"]:
            check = "PASS" if r["verdict"] == "PASS" else "FAIL"
            report_lines.append(f"- **{check}** — {r['criterion']}  \n  _{r['rationale']}_")
        report_lines += ["", f"**Judge summary:** {verdict['summary']}", ""]

    pct = (overall_pass / overall_total * 100) if overall_total else 0.0
    summary = (
        f"## Overall: {overall_pass}/{overall_total} criteria passed "
        f"({pct:.0f}%)"
    )
    report_lines.insert(4, summary)
    report_lines.insert(5, "")

    print(f"\n{summary}")

    with open("eval_report.md", "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines))
    print("Wrote eval_report.md")


if __name__ == "__main__":
    main()
