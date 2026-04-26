import json
import pandas as pd

# Load existing player cards
with open("frontend/src/data/players.json") as f:
    cards = {p["player_id"]: p for p in json.load(f)}

# Load CARMELO projections
carmelo = pd.read_csv("data/processed/carmelo_projections_2026.csv")

for _, row in carmelo.iterrows():
    pid = str(row["player_id"])
    if pid not in cards:
        continue
    cards[pid]["carmelo_y1"] = row.get("carmelo_fpts_y1")
    cards[pid]["carmelo_y2"] = row.get("carmelo_fpts_y2")
    cards[pid]["carmelo_y3"] = row.get("carmelo_fpts_y3")
    cards[pid]["carmelo_y4"] = row.get("carmelo_fpts_y4")
    cards[pid]["carmelo_y5"] = row.get("carmelo_fpts_y5")

with open("data/processed/player_cards.json", "w") as f:
    json.dump(list(cards.values()), f)