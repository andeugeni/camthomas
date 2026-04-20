# CAMTHOMAS Frontend

**Career Arc Model for Tracking Historical Outputs, Mapping Athletic Statistics**

A fantasy basketball projection dashboard powered by the SPS + CARMELO-style similarity model.

---

## Local Development

```bash
# 1. Install dependencies
npm install

# 2. Start dev server (hot reload)
npm run dev
# → http://localhost:3000
```

## Connecting Real Data

Once `build_player_cards.py` has been run and you have `data/processed/player_cards_2025.csv`:

1. Add a Next.js API route to serve the CSV, or convert it to JSON:
   ```bash
   python -c "
   import pandas as pd, json
   df = pd.read_csv('../data/processed/player_cards_2025.csv')
   df.to_json('src/data/players.json', orient='records')
   "
   ```

2. In `src/app/page.tsx`, replace:
   ```ts
   import { MOCK_PLAYERS } from "@/data/mockPlayers";
   const players = MOCK_PLAYERS;
   ```
   with:
   ```ts
   import players from "@/data/players.json";
   ```

3. The `PlayerCard` interface in `src/data/mockPlayers.ts` matches the CSV schema exactly.

---

## Vercel Deployment

```bash
# 1. Install Vercel CLI
npm i -g vercel

# 2. Deploy (first time — follow prompts)
vercel

# 3. Subsequent deploys
vercel --prod
```

For the weekly data refresh via GitHub Actions, push the updated `players.json` 
(generated from the CSV) to the repo and Vercel will auto-redeploy.

### Environment Variables (when adding backend)
Set in Vercel dashboard → Settings → Environment Variables:
- None required for static CSV mode.

---

## Project Structure

```
src/
  app/
    layout.tsx       # Root layout + fonts
    page.tsx         # Player selector sidebar + main card
  components/
    PlayerCardView.tsx  # Full player card with chart
  data/
    mockPlayers.ts   # Mock data (replace with real CSV-derived JSON)
  styles/
    globals.css
    page.module.css
    PlayerCardView.module.css
```

---

## Schema Reference

The `PlayerCard` interface maps 1:1 to `player_cards_2025.csv` columns.
Key columns: `player_id`, `player`, `age`, `team`, `pos`, `fantasy_pts`,
`proj_y1`–`proj_y5`, `ci_lo_y1`–`ci_hi_y5`, `actual_2018`–`actual_2025`,
plus all percentile `_pct` columns for the stat bars.
