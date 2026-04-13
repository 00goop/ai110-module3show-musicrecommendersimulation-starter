"""Music Recommender — core scoring and recommendation logic."""

import csv
import os


def load_songs(filepath=None):
    """Load songs from a CSV file and return a list of dictionaries."""
    if filepath is None:
        # Resolve path relative to the project root (one level up from src/)
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        filepath = os.path.join(base_dir, "data", "songs.csv")
    songs = []
    with open(filepath, newline="", encoding="utf-8") as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            # Convert numerical fields to floats so we can do math later
            row["energy"] = float(row["energy"])
            row["tempo_bpm"] = int(row["tempo_bpm"])
            songs.append(row)
    return songs


def score_song(user_prefs, song):
    """Score a single song against a user's taste profile.

    Returns:
        tuple: (numeric_score, list_of_reasons)
    """
    score = 0.0
    reasons = []

    # --- Genre match: +2.0 points ---
    if song["genre"].lower() == user_prefs["favorite_genre"].lower():
        score += 2.0
        reasons.append(f"genre match '{song['genre']}' (+2.0)")

    # --- Mood match: +1.0 point ---
    if song["mood"].lower() == user_prefs["favorite_mood"].lower():
        score += 1.0
        reasons.append(f"mood match '{song['mood']}' (+1.0)")

    # --- Energy similarity: up to +1.0 point ---
    # Uses inverse distance: the closer the song's energy is to the
    # user's target, the higher the score.  A perfect match = +1.0,
    # the maximum possible gap (1.0) = +0.0.
    energy_gap = abs(song["energy"] - user_prefs["target_energy"])
    energy_score = round(1.0 - energy_gap, 2)
    score += energy_score
    reasons.append(f"energy similarity ({energy_score:+.2f})")

    # --- Tempo bonus: +0.5 if within 15 BPM of target ---
    if "target_tempo" in user_prefs:
        tempo_gap = abs(song["tempo_bpm"] - user_prefs["target_tempo"])
        if tempo_gap <= 15:
            score += 0.5
            reasons.append(f"tempo close to {user_prefs['target_tempo']} BPM (+0.50)")

    return round(score, 2), reasons


def recommend_songs(user_prefs, songs, k=5):
    """Score every song and return the top-k recommendations.

    Returns:
        list of tuples: [(song_dict, score, reasons), ...] sorted high→low
    """
    scored = [(song, *score_song(user_prefs, song)) for song in songs]
    # Sort by score descending; ties broken alphabetically by title
    scored.sort(key=lambda x: (-x[1], x[0]["title"]))
    return scored[:k]