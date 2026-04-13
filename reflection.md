# Reflection

## What was your biggest learning moment during this project?

Before this project, I genuinely didn't know the difference between collaborative and content-based filtering. I thought recommendation systems were all one thing — some kind of magic algorithm that "just knows" what you'll like. Learning that collaborative filtering relies on patterns from other users' behavior while content-based filtering matches attributes of the items themselves was a big shift in understanding. It made me realize that every recommendation I see on Spotify or TikTok is the result of a deliberate design choice about which signals to pay attention to and how much to weight them.

## How did using AI tools help you, and when did you need to double-check them?

AI was extremely helpful for generating the initial scoring logic and for expanding the dataset with diverse songs. It saved a lot of time on boilerplate code like CSV reading and output formatting. Where I had to be careful was with the scoring math — when I first asked for a scoring function, the AI suggested a distance formula that looked correct but actually penalized songs in the wrong direction (closer songs got lower scores). I had to read through the logic carefully and test it with a specific example to catch that. It reinforced that AI-generated code still needs a human to verify the logic matches the intent.

## What surprised you about how simple algorithms can still "feel" like recommendations?

The biggest surprise was that even with just four features and basic addition, the system produced recommendations that actually felt reasonable. When I set the profile to "Chill Lofi," the top results really were the mellow, low-energy tracks I'd pick myself. It makes you realize that real recommendation systems aren't necessarily doing anything conceptually more complex — they just do it at massive scale with many more features. The simplicity also made the biases obvious: the "Sad Acoustic" edge case exposed how genre weight dominates everything, which wouldn't have been as visible in a more complex system.

## What would you try next if you extended this project?

I'd want to add a genre similarity matrix so that related genres (like indie and folk, or pop and r&b) can get partial matching credit instead of the current all-or-nothing approach. I'd also want to pull in a real dataset from Spotify's API with features like danceability and valence so the recommender has more nuance to work with. Finally, I'd be interested in adding a simple feedback mechanism where the user can rate recommendations and the system adjusts the weights over time — that would start bridging the gap between pure content-based and a hybrid approach.

## Profile Comparison Notes

**High-Energy Pop vs. Chill Lofi:** These two profiles produced completely different top-5 lists with no overlap, which makes sense — they're on opposite ends of the energy spectrum and prefer different genres. The system correctly separated them, showing that the combination of genre + mood + energy is enough to distinguish very different tastes.

**Deep Intense Rock vs. Sad Acoustic (Edge Case):** The rock profile got clean, high-confidence results (scores of 4.45–4.50) because rock + intense + high energy is an internally consistent preference. The Sad Acoustic profile, which combines folk + sad with contradictory high energy, produced much lower scores (max 2.65). This shows the system struggles when a user's preferences are internally inconsistent — it can't find songs that satisfy everything, so genre wins by default. In a real system, this might mean a user gets stuck in a genre bubble even when their actual mood calls for something different.

**EDM profile (inferred from data):** High-energy electronic songs like "Gym Hero" and "Bass Drop City" appeared in multiple profiles' results wherever energy was the driving factor, demonstrating that energy similarity is the most universal feature — it crosses genre boundaries in a way that genre matching cannot.
