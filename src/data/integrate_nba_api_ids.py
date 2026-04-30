import json
import pandas as pd

# 1. Load the existing player cards
with open("frontend/src/data/player_cards.json") as f:
    player_data = json.load(f)

# 2. Load the NBA IDs CSV
nba_ids_df = pd.read_csv("data/raw/nba_api_ids.csv")

# Create a mapping dictionary { "Player Name": "PERSON_ID" }
# We use names as the key to bridge your custom ID and the NBA ID
id_map = dict(zip(nba_ids_df["DISPLAY_FIRST_LAST"], nba_ids_df["PERSON_ID"]))

# 3. Integrate the IDs into the JSON structure
for player in player_data:
    name = player.get("player")
    if name in id_map:
        # Save as a string or int depending on your frontend preference
        player["nba_person_id"] = str(id_map[name])
    else:
        player["nba_person_id"] = None  # Or handle missing IDs as needed

# 4. Save the updated JSON
with open("frontend/src/data/player_cards.json", "w") as f:
    json.dump(player_data, f, indent=4)

print("Successfully integrated NBA Person IDs.")