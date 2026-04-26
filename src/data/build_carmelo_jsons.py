import pandas as pd, json

df = pd.read_csv('data/processed/carmelo_projections_2026.csv')
df.to_json('frontend/src/data/carmelo.json', orient='records', indent=2)
print(f'Wrote {len(df)} players')