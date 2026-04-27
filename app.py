"""MELODY — Streamlit UI for the Agentic RAG music recommender.

Renders each step of the reasoning chain in real time using st.status containers
so the user can watch the agent think.

Run with:
    streamlit run app.py
"""

import streamlit as st

from src.agent import MusicAgent


SAMPLE_QUERIES = [
    "I want chill indie music for studying",
    "Give me high-energy pop for a workout",
    "I'm sad but I want something acoustic and folky",
    "Sad folk songs with really high energy and fast tempo",  # edge case: conflict
    "Recommend me some Taylor Swift",                           # edge case: out of catalog
]


st.set_page_config(page_title="MELODY — Agentic Music Recommender",
                   page_icon=None, layout="wide")

st.title("MELODY")
st.caption("Agentic RAG music recommender — Gemini 2.5 Flash + content-based scoring")

with st.sidebar:
    st.header("About")
    st.markdown(
        "MELODY is an agentic recommender that runs a six-step reasoning chain:\n\n"
        "1. **Parse** the natural-language query into a UserProfile\n"
        "2. **Score** the catalog with deterministic content-based scoring\n"
        "3. **Retrieve** local artist bios (RAG source #1)\n"
        "4. **Search** the web via Gemini grounding (RAG source #2)\n"
        "5. **Draft** the final recommendation\n"
        "6. **Self-critique** for hallucinations, filter bubbles, conflicts\n\n"
        "Each step streams to the UI so you can watch the agent think."
    )
    st.divider()
    st.subheader("Try a sample query")
    for sq in SAMPLE_QUERIES:
        if st.button(sq, key=f"sample_{sq}", use_container_width=True):
            st.session_state["query"] = sq

query = st.text_input(
    "What do you want to listen to?",
    value=st.session_state.get("query", "I want chill indie music for studying"),
    placeholder="e.g. high-energy pop for a workout",
)

go = st.button("Recommend", type="primary")

if go and query.strip():
    try:
        agent = MusicAgent()
    except RuntimeError as e:
        st.error(str(e))
        st.stop()

    st.subheader("Reasoning chain")

    containers: dict[int, "st.delta_generator.DeltaGenerator"] = {}
    final_data: dict[str, object] = {}

    for event in agent.run(query.strip()):
        if event.status == "running":
            cont = st.status(f"Step {event.step}: {event.name}", expanded=True)
            with cont:
                st.write(event.summary)
            containers[event.step] = cont
            continue

        cont = containers.get(event.step) or st.status(
            f"Step {event.step}: {event.name}", expanded=True
        )
        state = "complete" if event.status == "done" else "error"
        cont.update(label=f"Step {event.step}: {event.name} — {event.summary}",
                    state=state, expanded=False)

        with cont:
            if event.step == 1 and "profile" in event.data:
                p = event.data["profile"]
                st.json(p)
                st.caption(f"How Gemini interpreted you: {p.get('interpretation_notes', '')}")

            elif event.step == 2 and "top_recs" in event.data:
                for i, rec in enumerate(event.data["top_recs"], start=1):
                    s = rec["song"]
                    st.markdown(
                        f"**#{i} {s['title']}** by *{s['artist']}* — "
                        f"score `{rec['score']:.2f}`"
                    )
                    st.caption(
                        f"genre={s['genre']} · mood={s['mood']} · "
                        f"energy={s['energy']} · tempo={s['tempo_bpm']} BPM · "
                        f"reasons: {', '.join(rec['reasons'])}"
                    )

            elif event.step == 3 and "bios" in event.data:
                for artist, bio in event.data["bios"].items():
                    with st.expander(artist):
                        st.write(bio)

            elif event.step == 4 and "web" in event.data:
                st.write(event.data["web"]["text"])
                if event.data["web"]["sources"]:
                    st.caption("Sources:")
                    for url in event.data["web"]["sources"][:5]:
                        st.markdown(f"- {url}")

            elif event.step == 5 and "draft" in event.data:
                st.markdown(event.data["draft"])
                final_data["draft"] = event.data["draft"]

            elif event.step == 6 and "critique" in event.data:
                c = event.data["critique"]
                col_a, col_b = st.columns([1, 3])
                with col_a:
                    score = c["confidence_score"]
                    color = "green" if score >= 7 else ("orange" if score >= 4 else "red")
                    st.markdown(f"### :{color}[Confidence: {score}/10]")
                with col_b:
                    st.markdown(f"**Hallucination check:** {c['hallucination_check']}")
                    st.markdown(f"**Filter bubble check:** {c['filter_bubble_check']}")
                    st.markdown(f"**Conflict check:** {c['conflict_check']}")
                    st.markdown(f"**Low-confidence picks:** {c['low_confidence_picks']}")
                final_data["final"] = c["revised_summary"]

    st.divider()
    st.subheader("Final answer")
    if "final" in final_data:
        st.success(final_data["final"])
    elif "draft" in final_data:
        st.info(final_data["draft"])
    else:
        st.warning("Agent did not complete — see the reasoning chain above for the failure point.")
