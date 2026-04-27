"""Unit tests for the deterministic scoring engine.

These tests exercise the dict-based API in src/recommender.py. They are
intentionally hermetic — no Gemini calls, no network — so they can run in any
CI environment without API keys.
"""

from src.recommender import load_songs, recommend_songs, score_song


def _small_catalog() -> list[dict]:
    return [
        {
            "title": "Test Pop Track",
            "artist": "Test Artist",
            "genre": "pop",
            "mood": "happy",
            "energy": 0.8,
            "tempo_bpm": 120,
        },
        {
            "title": "Chill Indie Loop",
            "artist": "Test Artist",
            "genre": "indie",
            "mood": "chill",
            "energy": 0.4,
            "tempo_bpm": 80,
        },
    ]


def _pop_user() -> dict:
    return {
        "favorite_genre": "pop",
        "favorite_mood": "happy",
        "target_energy": 0.8,
        "target_tempo": 120,
    }


def test_score_perfect_match_is_max():
    """genre + mood + perfect energy + tempo bonus = 4.5"""
    songs = _small_catalog()
    score, reasons = score_song(_pop_user(), songs[0])
    assert score == 4.5
    assert any("genre match" in r for r in reasons)
    assert any("mood match" in r for r in reasons)
    assert any("tempo close" in r for r in reasons)


def test_score_no_match_only_energy_component():
    """A song with the wrong genre, mood, and far-off tempo only earns
    energy-similarity points."""
    user = {
        "favorite_genre": "country",
        "favorite_mood": "sad",
        "target_energy": 0.4,
        "target_tempo": 60,
    }
    pop_song = _small_catalog()[0]
    score, reasons = score_song(user, pop_song)
    # energy gap = |0.8 - 0.4| = 0.4 -> energy_score = 0.6
    assert score == 0.6
    assert all("genre match" not in r for r in reasons)
    assert all("mood match" not in r for r in reasons)


def test_recommend_returns_sorted_by_score_desc():
    """recommend_songs should rank a perfect match above a weak match."""
    results = recommend_songs(_pop_user(), _small_catalog(), k=2)
    assert len(results) == 2
    assert results[0][1] >= results[1][1]
    assert results[0][0]["genre"] == "pop"


def test_recommend_respects_k():
    """k=1 returns exactly one song even when more candidates exist."""
    results = recommend_songs(_pop_user(), _small_catalog(), k=1)
    assert len(results) == 1


def test_load_songs_default_path_loads_full_catalog():
    """The shipped data/songs.csv has 20 songs."""
    songs = load_songs()
    assert len(songs) == 20
    # Spot-check the first row was type-coerced correctly
    first = songs[0]
    assert isinstance(first["energy"], float)
    assert isinstance(first["tempo_bpm"], int)


def test_tempo_bonus_only_within_15_bpm():
    """Tempo bonus is binary: +0.5 if within 15 BPM of target, otherwise 0."""
    user = _pop_user()  # target_tempo = 120
    near = {**_small_catalog()[0], "tempo_bpm": 130}   # within 15
    far = {**_small_catalog()[0], "tempo_bpm": 200}    # outside 15
    near_score, _ = score_song(user, near)
    far_score, _ = score_song(user, far)
    assert near_score - far_score == 0.5
