# MLB Tracker ⚾

A daily MLB matchup model that scores every game 1–10 across four weighted categories, compares head-to-head, and automatically tracks how accurate each confidence tier is over the season.

## How It Works

Scores each team using a weighted formula:

| Category | Weight |
|---|---|
| Hitting (weighted OPS — last 5 games 65%, season 35%) | 40% |
| Starting Pitching (ERA + WHIP + home/away splits) | 32% |
| Relief Pitching (bullpen ERA + WHIP) | 18% |
| Team Record (win %) | 10% |

The difference between the two team scores is the **edge**. Picks are sorted into four tiers:

| Tier | Edge |
|---|---|
| Top Algorithm Favourites | 3.0+ |
| Strong Edge | 2.0 – 2.9 |
| Slight Edge | 1.0 – 1.9 |
| Toss-Up | < 1.0 |

## Features

- Pulls today's schedule and probable pitchers automatically from the MLB Stats API
- Generates a local HTML report that opens in your browser
- **Results Tracker** — the next day it fetches final scores, resolves wins/losses, and updates per-tier win rates so you can see how the algorithm performs over time
- Daily file-based cache so repeat runs are instant

## Setup

```bash
pip install requests
python mlb_matchup_model.py              # today's games
python mlb_matchup_model.py 2026-04-25  # specific date
```

The script opens a browser tab automatically. No server needed — fully local.

## Data Source

All stats via the free [MLB Stats API](https://statsapi.mlb.com). No API key required.

## Disclaimer

For entertainment and educational purposes only.
