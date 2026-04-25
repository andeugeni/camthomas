import pandas as pd, json

df = pd.read_csv('data/processed/player_cards_2025.csv')
df.to_json('frontend/src/data/players.json', orient='records', indent=2)
print(f'Wrote {len(df)} players')