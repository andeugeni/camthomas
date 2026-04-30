from nba_api.stats.endpoints import commonallplayers
import logging
from pathlib import Path


RAW_DIR        = Path(__file__).resolve().parents[2] / "data" / "raw"
out_path = RAW_DIR / "nba_api_ids.csv"
# Fetch the data
players = commonallplayers.CommonAllPlayers(is_only_current_season=0).get_data_frames()[0]


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

log.info(players.columns)
# Filter for the columns you want

df_ids = players[["PERSON_ID", "DISPLAY_FIRST_LAST"]]

# Save to CSV
df_ids.to_csv(out_path, index=False)