"""CLI entry point for the Music Recommender Simulation."""

try:
    from recommender import load_songs, recommend_songs
except ModuleNotFoundError:
    from src.recommender import load_songs, recommend_songs


# ---------------------------------------------------------------------------
# User taste profiles
# ---------------------------------------------------------------------------

PROFILES = {
    "High-Energy Pop": {
        "favorite_genre": "pop",
        "favorite_mood": "happy",
        "target_energy": 0.8,
        "target_tempo": 120,
    },
    "Chill Lofi": {
        "favorite_genre": "indie",
        "favorite_mood": "chill",
        "target_energy": 0.3,
        "target_tempo": 80,
    },
    "Deep Intense Rock": {
        "favorite_genre": "rock",
        "favorite_mood": "intense",
        "target_energy": 0.9,
        "target_tempo": 145,
    },
    "Sad Acoustic (Edge Case)": {
        "favorite_genre": "folk",
        "favorite_mood": "sad",
        "target_energy": 0.9,          # conflicting: wants folk+sad but HIGH energy
        "target_tempo": 150,
    },
}


def print_recommendations(profile_name, prefs, songs, k=5):
    """Pretty-print the top-k recommendations for a profile."""
    recs = recommend_songs(prefs, songs, k)

    print(f"\n{'=' * 60}")
    print(f"  Profile: {profile_name}")
    print(f"  Genre={prefs['favorite_genre']}  Mood={prefs['favorite_mood']}  "
          f"Energy={prefs['target_energy']}  Tempo={prefs.get('target_tempo', 'N/A')}")
    print(f"{'=' * 60}")

    for rank, (song, score, reasons) in enumerate(recs, start=1):
        print(f"\n  #{rank}  {song['title']}  by {song['artist']}")
        print(f"       Score: {score:.2f}")
        print(f"       Reasons: {', '.join(reasons)}")

    print()


def main():
    songs = load_songs()
    print(f"Loaded songs: {len(songs)}")

    for name, prefs in PROFILES.items():
        print_recommendations(name, prefs, songs)


if __name__ == "__main__":
    main()
