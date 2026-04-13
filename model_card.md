# Model Card — VibeFinder 1.0

## 1. Model Name

**VibeFinder 1.0** — a content-based music recommendation simulator.

## 2. Goal / Task

VibeFinder takes a user's taste profile (favorite genre, mood, target energy level, and preferred tempo) and recommends the top 5 songs from a catalog that best match those preferences. It simulates how a real streaming service might suggest "what to play next" using song attributes rather than listening history from other users.

## 3. Data Used

The dataset is a hand-curated CSV file containing **20 songs**. Each song has five attributes: `title`, `artist`, `genre`, `mood`, `energy` (0.0–1.0 float), and `tempo_bpm` (integer).

**Limitations of the data:**
- The catalog is very small — only 20 songs across 7 genres.
- Genre distribution is uneven: pop (4 songs) and indie (4 songs) are over-represented, while country (1 song) and r&b (2 songs) are under-represented.
- All song attributes were manually assigned, which introduces subjective bias (e.g., what counts as "chill" vs. "sad" is a judgment call).

## 4. Algorithm Summary

The system scores each song against the user's profile using a weighted point system:

1. **Genre match (+2.0 points):** If the song's genre matches the user's favorite genre.
2. **Mood match (+1.0 point):** If the song's mood matches the user's preferred mood.
3. **Energy similarity (0.0–1.0 points):** Calculated as `1.0 - |song_energy - target_energy|`. Songs with energy closer to the user's target score higher.
4. **Tempo bonus (+0.5 points):** Awarded if the song's tempo is within 15 BPM of the user's target.

After scoring every song, the system sorts them from highest to lowest score and returns the top 5. The maximum possible score is 4.5.

## 5. Observed Behavior / Biases

**Genre dominance creates filter bubbles.** Because genre match is worth +2.0 (nearly half the max score), a song in the "right" genre will almost always outrank a song in the "wrong" genre, even if the second song is a better match on mood and energy. For example, the "Sad Acoustic" edge-case profile wanted folk + sad + high energy. The top results were folk songs that didn't match the mood at all — they ranked higher than a country sad song simply because of the +2.0 genre bonus.

**Small dataset amplifies the problem.** With only 2 folk songs in the catalog, a folk-loving user gets limited variety regardless of their other preferences.

**Binary matching misses nuance.** Genre and mood are treated as exact matches (match or don't), so "indie" and "folk" get zero similarity credit even though they're musically adjacent.

## 6. Evaluation Process

The system was tested with four distinct user profiles:

- **High-Energy Pop** (genre=pop, mood=happy, energy=0.8, tempo=120) — worked as expected, top results were upbeat pop songs.
- **Chill Lofi** (genre=indie, mood=chill, energy=0.3, tempo=80) — strong results, surfaced lo-fi and ambient tracks.
- **Deep Intense Rock** (genre=rock, mood=intense, energy=0.9, tempo=145) — all three rock songs appeared in the top 3, which makes sense given the small catalog.
- **Sad Acoustic / Edge Case** (genre=folk, mood=sad, energy=0.9, tempo=150) — this profile has conflicting preferences (folk songs tend to be low energy, but this user wants 0.9 energy). The system still ranked folk songs first because genre weight (+2.0) overpowers the energy penalty, which revealed the genre-dominance bias clearly.

## 7. Intended Use and Non-Intended Use

**Intended use:**
- Educational simulation to understand how content-based recommenders work.
- Demonstrating the scoring → ranking pipeline in a simple, transparent system.
- Starting point for experimenting with feature weights and observing how changes affect output.

**NOT intended for:**
- Production music streaming — the dataset is far too small and the algorithm too simplistic.
- Any system where fairness across genres/artists matters — the current weighting creates clear biases.
- Replacing collaborative or hybrid recommendation systems that use real user behavior data.

## 8. Ideas for Improvement

1. **Partial genre matching:** Instead of binary match/no-match, use a genre similarity matrix (e.g., indie ↔ folk = 0.7 similarity) so related genres get partial credit.
2. **Normalize feature weights:** Run experiments to find weights that produce the most diverse top-5 lists rather than hard-coding 2.0/1.0/1.0/0.5.
3. **Larger, real-world dataset:** Pull song metadata from an API like Spotify's to get hundreds of songs with professionally tagged features (danceability, acousticness, valence).
4. **User feedback loop:** Let users thumbs-up/down recommendations and adjust weights over time, moving toward a simple hybrid system.
