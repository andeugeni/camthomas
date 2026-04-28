"""
fetch.py
--------
Pull NBA player data from Basketball Reference and write CSVs to data/raw/.

Three data sources, three fetch functions:

  fetch_season(year)          -> player_totals_{year}.csv
      Box-score counting stats via the scraper library (FG, REB, AST, etc.)

  fetch_advanced_season(year) -> player_advanced_{year}.csv
      Advanced stats via the scraper library (BPM, DBPM, TS%, USG%, TRB%,
      AST%, STL%, BLK%, TOV%, VORP, WS/48, PER, 3PA-rate, FTA-rate)

  fetch_player_bio(year)      -> player_bio_{year}.csv
      Height and weight via direct BR per_game page scrape.
      BR only recently added these to season pages; pre-~2000 may be sparse.

  fetch_draft_positions()     -> draft_positions.csv  (all-time, one-shot)
      Overall pick number per player slug via direct BR draft page scrape.
      Draft year is per-player not per-season, so this is fetched once and
      joined by slug in pipeline.py.

Multi-team handling
~~~~~~~~~~~~~~~~~~~
  Totals table: traded players have team=None after enum parsing (BR changed
    "TOT" to "2TM"/"3TM", which aren't in the enum).
  Advanced table: is_combined_totals=True flags multi-team summary rows.
  In both cases we keep the summary row and drop individual team rows.

Usage
~~~~~
    python -m src.data.fetch                          # everything, 1980-2025
    python -m src.data.fetch --seasons 2024 2025      # specific seasons
    python -m src.data.fetch --since 2020             # 2020 onward
    python -m src.data.fetch --type advanced          # advanced stats only
    python -m src.data.fetch --type bio               # height/weight only
    python -m src.data.fetch --type draft             # draft positions only
    python -m src.data.fetch --seasons 2025 --force   # re-fetch existing
"""

import argparse
import logging
import time
from pathlib import Path

from typing import Optional
import pandas as pd
import requests
from bs4 import BeautifulSoup
from basketball_reference_web_scraper import client

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

RAW_DIR        = Path(__file__).resolve().parents[2] / "data" / "raw"
FIRST_SEASON   = 1980
CURRENT_SEASON = 2025
BR_BASE        = "https://www.basketball-reference.com"

# Polite scraping headers — BR blocks bare requests
BR_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.basketball-reference.com/",
}

# ---------------------------------------------------------------------------
# Rename maps
# ---------------------------------------------------------------------------

TOTALS_RENAME = {
    "slug":                              "player_id",
    "name":                              "player",
    "age":                               "age",
    "games_played":                      "g",
    "games_started":                     "gs",
    "minutes_played":                    "mp",
    "made_field_goals":                  "fg",
    "attempted_field_goals":             "fga",
    "made_three_point_field_goals":      "x3p",
    "attempted_three_point_field_goals": "x3pa",
    "made_free_throws":                  "ft",
    "attempted_free_throws":             "fta",
    "offensive_rebounds":                "orb",
    "defensive_rebounds":                "drb",
    "assists":                           "ast",
    "steals":                            "stl",
    "blocks":                            "blk",
    "turnovers":                         "tov",
    "personal_fouls":                    "pf",
    "points":                            "pts",
}

ADVANCED_RENAME = {
    "slug":                          "player_id",
    "name":                          "player",
    "age":                           "age",
    "games_played":                  "g",
    "minutes_played":                "mp",
    "player_efficiency_rating":      "per",
    "true_shooting_percentage":      "ts_pct",
    "three_point_attempt_rate":      "x3pa_rate",
    "free_throw_attempt_rate":       "fta_rate",
    "offensive_rebound_percentage":  "orb_pct",
    "defensive_rebound_percentage":  "drb_pct",
    "total_rebound_percentage":      "trb_pct",
    "assist_percentage":             "ast_pct",
    "steal_percentage":              "stl_pct",
    "block_percentage":              "blk_pct",
    "turnover_percentage":           "tov_pct",
    "usage_percentage":              "usg_pct",
    "offensive_win_shares":          "ows",
    "defensive_win_shares":          "dws",
    "win_shares":                    "ws",
    "win_shares_per_48_minutes":     "ws_per48",
    "offensive_box_plus_minus":      "obpm",
    "defensive_box_plus_minus":      "dbpm",
    "box_plus_minus":                "bpm",
    "value_over_replacement_player": "vorp",
}

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Shared retry helper
# ---------------------------------------------------------------------------

def _retry(fn, label: str, retries: int = 3, backoff: float = 8.0):
    """Call fn(), retrying up to `retries` times with exponential backoff."""
    for attempt in range(1, retries + 1):
        try:
            return fn()
        except Exception as exc:
            if attempt == retries:
                raise RuntimeError(f"Failed to fetch {label} after {retries} attempts") from exc
            wait = backoff * attempt
            log.warning("Attempt %d/%d for %s failed: %s. Retrying in %.0fs ...",
                        attempt, retries, label, exc, wait)
            time.sleep(wait)


# ---------------------------------------------------------------------------
# 1. Season totals
# ---------------------------------------------------------------------------

def fetch_season(end_year: int, retries: int = 3, backoff: float = 8.0) -> pd.DataFrame:
    """
    Fetch counting stat totals for one season.
    Returns one row per player; multi-team players get their combined row.
    """
    raw = _retry(
        lambda: client.players_season_totals(season_end_year=end_year),
        label=f"totals {end_year}", retries=retries, backoff=backoff,
    )
    if not raw:
        raise RuntimeError(f"Season {end_year} totals returned empty.")

    df = pd.DataFrame(raw)

    # Multi-team: keep combined (team=None) rows; for single-team players keep
    # their one row regardless of team value.
    slug_counts = df.groupby("slug")["slug"].transform("count")
    df = df[(slug_counts == 1) | (df["team"].isna())].copy()

    def _team_str(t) -> str:
        if t is None:
            return "TOT"
        try:
            return t.value
        except AttributeError:
            return str(t)

    df["tm"] = df["team"].apply(_team_str)
    df = df.drop(columns=["team"])

    if "positions" in df.columns:
        df["pos"] = df["positions"].apply(
            lambda ps: "|".join(p.value for p in ps) if ps else ""
        )
        df = df.drop(columns=["positions"])

    df = df.rename(columns={k: v for k, v in TOTALS_RENAME.items() if k in df.columns})

    # Derived
    df["x2p"]  = df["fg"]  - df["x3p"]
    df["x2pa"] = df["fga"] - df["x3pa"]
    df["trb"]  = df["orb"] + df["drb"]
    df["mpg"]  = df["mp"]  / df["g"].replace(0, pd.NA)
    df["season"] = end_year

    log.info("Totals   %d: %d players", end_year, len(df))
    return df.reset_index(drop=True)


# ---------------------------------------------------------------------------
# 2. Advanced stats
# ---------------------------------------------------------------------------

def fetch_advanced_season(end_year: int, retries: int = 3, backoff: float = 8.0) -> pd.DataFrame:
    """
    Fetch advanced stats for one season (BPM, DBPM, TS%, USG%, TRB%, etc.)
    Returns one row per player; multi-team players get their combined row.

    The scraper's include_combined_values=True returns ALL rows (individual
    team rows + combined summary rows). We then keep only combined rows for
    multi-team players, mirroring the totals dedup logic.
    """
    raw = _retry(
        lambda: client.players_advanced_season_totals(
            season_end_year=end_year,
            include_combined_values=True,
        ),
        label=f"advanced {end_year}", retries=retries, backoff=backoff,
    )
    if not raw:
        raise RuntimeError(f"Season {end_year} advanced returned empty.")

    df = pd.DataFrame(raw)

    # is_combined_totals=True means this is the multi-team summary row (2TM/3TM).
    # Keep combined rows for multi-team players; keep the single row for everyone else.
    slug_counts = df.groupby("slug")["slug"].transform("count")
    df = df[(slug_counts == 1) | (df["is_combined_totals"] == True)].copy()
    df = df.drop(columns=["is_combined_totals"])

    # team enum -> string, same pattern as totals
    def _team_str(t) -> str:
        if t is None:
            return "TOT"
        try:
            return t.value
        except AttributeError:
            return str(t)

    if "team" in df.columns:
        df["tm"] = df["team"].apply(_team_str)
        df = df.drop(columns=["team"])

    if "positions" in df.columns:
        df = df.drop(columns=["positions"])

    df = df.rename(columns={k: v for k, v in ADVANCED_RENAME.items() if k in df.columns})
    df["season"] = end_year

    log.info("Advanced %d: %d players", end_year, len(df))
    return df.reset_index(drop=True)


# ---------------------------------------------------------------------------
# 3. Player bio (height + weight) — custom scrape
# ---------------------------------------------------------------------------

def fetch_player_bio(
    api_key: str,
    retries: int = 3,
    backoff: float = 30.0,
    delay: float = 15.0,
    skip_existing: bool = True,
) -> pd.DataFrame:
    """
    Fetch player bio data (height, weight, draft info) from the BallDontLie API.

    Endpoint: GET https://api.balldontlie.io/v1/players
    Docs:     https://nba.balldontlie.io/#get-all-players

    BDL uses its own numeric player IDs, not BR slugs.  We join to our BR-keyed
    data by normalised full name.  The output includes a bdl_id column so the
    crosswalk can be inspected and corrected if needed.

    Name collision handling: if two BR players share an identical normalised name
    we flag both rows with name_collision=True and leave player_id blank so the
    pipeline skips them rather than silently mis-joining.

    Returns a DataFrame saved to data/raw/player_bio.csv with columns:
        player_id (BR slug), bdl_id, height_in, weight_lbs,
        draft_year, draft_round, draft_pick, name_collision
    """
    out_path = RAW_DIR / "player_bio.csv"
    if skip_existing and out_path.exists():
        log.info("Player bio already at %s — skipping.", out_path)
        return pd.read_csv(out_path)

    from balldontlie import BalldontlieAPI
    bdl = BalldontlieAPI(api_key=api_key)

    # ------------------------------------------------------------------
    # 1. Paginate through all BDL players using the SDK
    # ------------------------------------------------------------------
    all_players = []
    cursor: int | None = None
    page = 0

    while True:
        response = _retry(
            lambda c=cursor: bdl.nba.players.list(per_page=100, cursor=c),
            label=f"BDL players page {page}",
            retries=retries, backoff=backoff,
        )

        all_players.extend(response.data)
        page += 1

        cursor = response.meta.next_cursor
        if not cursor:
            break

        time.sleep(delay)

    log.info("BDL: fetched %d players total", len(all_players))

    # ------------------------------------------------------------------
    # 2. Build BDL lookup: normalised_name -> list of NBAPlayer objects
    # ------------------------------------------------------------------
    def _normalise(first: str, last: str) -> str:
        """Lowercase, strip accents, collapse whitespace."""
        import unicodedata
        name = f"{first} {last}".lower().strip()
        name = unicodedata.normalize("NFD", name)
        name = "".join(c for c in name if unicodedata.category(c) != "Mn")
        return " ".join(name.split())

    bdl_by_name: dict[str, list] = {}
    for p in all_players:
        key = _normalise(p.first_name or "", p.last_name or "")
        bdl_by_name.setdefault(key, []).append(p)

    # ------------------------------------------------------------------
    # 3. Load all known BR slugs from raw totals CSVs to build name->slug map
    # ------------------------------------------------------------------
    br_by_name: dict[str, list[str]] = {}  # normalised_name -> [slug, ...]
    for csv_path in sorted(RAW_DIR.glob("player_totals_*.csv")):
        try:
            df_br = pd.read_csv(csv_path, usecols=["player_id", "player"])
            for _, row in df_br.iterrows():
                key = _normalise(*row["player"].split(" ", 1)) if " " in row["player"]                       else _normalise(row["player"], "")
                br_by_name.setdefault(key, []).append(row["player_id"])
        except Exception:
            pass

    # Deduplicate slugs per name
    br_unique: dict[str, list[str]] = {
        k: list(dict.fromkeys(v)) for k, v in br_by_name.items()
    }

    # ------------------------------------------------------------------
    # 4. Join BDL -> BR by normalised name
    # ------------------------------------------------------------------
    def _height_in(h: Optional[str]) -> Optional[int]:
        if not h or "-" not in h:
            return None
        try:
            feet, inches = h.split("-")
            return int(feet) * 12 + int(inches)
        except ValueError:
            return None

    rows = []
    for norm_name, bdl_players in bdl_by_name.items():
        br_slugs = br_unique.get(norm_name, [])

        # Take the first BDL entry (usually only one per name)
        p = bdl_players[0]

        try:
            new_weight = int(p.weight) if p.weight is not None else None
        except (ValueError, TypeError):
            new_weight = None

        row: dict = {
            "bdl_id":      p.id,
            "height_in":   _height_in(p.height),
            "weight_lbs":  new_weight,
            "draft_year":  p.draft_year,
            "draft_round": p.draft_round,
            "draft_pick":  p.draft_number,
        }

        if len(br_slugs) == 0:
            # BDL player not in our BR data — skip (historical or G-League only)
            continue
        elif len(br_slugs) == 1:
            row["player_id"]     = br_slugs[0]
            row["name_collision"] = False
            row["player_name"] = p.first_name + " " + p.last_name
        else:
            # Multiple BR slugs with the same name — flag for review
            log.warning(
                "Name collision for '%s': BR slugs %s — leaving player_id blank.",
                norm_name, br_slugs,
            )
            row["player_id"]     = None
            row["name_collision"] = True

        rows.append(row)

    df = pd.DataFrame(rows)
    if df.empty:
        log.warning("fetch_player_bio: no rows produced — check api_key and raw totals CSVs.")
        return df

    # Drop rows with no player_id (unmatched or collisions)
    matched   = df[df["player_id"].notna() & ~df["name_collision"]].copy()
    unmatched = df[df["player_id"].isna()].copy()
    collisions = df[df["name_collision"] == True].copy()

    log.info(
        "Bio: %d matched, %d unmatched (no BR data), %d name collisions",
        len(matched), len(unmatched), len(collisions),
    )

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    matched.to_csv(out_path, index=False)
    log.info("Saved -> %s", out_path)

    # Save a separate file for manual review of collisions/unmatched if any exist
    if not collisions.empty:
        col_path = RAW_DIR / "player_bio_collisions.csv"
        collisions.to_csv(col_path, index=False)
        log.info("Name collisions saved for review -> %s", col_path)

    return matched

# ---------------------------------------------------------------------------
# 4. Draft positions — one-time all-history fetch
# ---------------------------------------------------------------------------

def fetch_draft_positions(
    first_year: int = 1980,
    last_year: int = 2026,
    retries: int = 3,
    backoff: float = 8.0,
    delay: float = 4.0,
    skip_existing: bool = True,
) -> pd.DataFrame:
    """
    Scrape overall draft pick number for every player across all draft classes.

    URL: https://www.basketball-reference.com/draft/NBA_{year}.html

    Returns a DataFrame with columns: player_id (slug), draft_year, draft_pick.
    Undrafted players will have no row — pipeline.py fills with NaN on join.
    Saves to data/raw/draft_positions.csv and returns the DataFrame.
    """
    out_path = RAW_DIR / "draft_positions.csv"
    if skip_existing and out_path.exists():
        log.info("Draft positions already at %s — skipping.", out_path)
        return pd.read_csv(out_path)

    all_rows = []
    failed_years = []

    for year in range(first_year, last_year + 1):
        url = f"{BR_BASE}/draft/NBA_{year}.html"

        def _scrape(u=url):
            resp = requests.get(u, headers=BR_HEADERS, timeout=30)
            resp.raise_for_status()
            return resp.content

        try:
            html = _retry(_scrape, label=f"draft {year}", retries=retries, backoff=backoff)
        except Exception as exc:
            log.warning("Draft %d failed: %s — skipping.", year, exc)
            failed_years.append(year)
            time.sleep(delay)
            continue

        soup = BeautifulSoup(html, "lxml")
        table = soup.find("table", {"id": "stats"})
        if table is None:
            log.warning("No draft table found for %d — skipping.", year)
            time.sleep(delay)
            continue

        for tr in table.find("tbody").find_all("tr"):
            if tr.get("class") and "thead" in tr.get("class"):
                continue

            player_td = tr.find("td", {"data-stat": "player"})
            pick_td   = tr.find("td", {"data-stat": "pick_overall"})
            if player_td is None or pick_td is None:
                continue

            a_tag = player_td.find("a")
            if a_tag is None:
                continue

            slug = a_tag["href"].split("/")[-1].replace(".html", "")
            pick_text = pick_td.get_text(strip=True)

            try:
                pick = int(pick_text)
            except ValueError:
                continue

            all_rows.append({
                "player_id":  slug,
                "draft_year": year,
                "draft_pick": pick,
            })

        log.info("Draft %d: scraped.", year)
        time.sleep(delay)

    df = pd.DataFrame(all_rows).drop_duplicates(subset="player_id")

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_path, index=False)
    log.info("Draft positions: %d players saved -> %s", len(df), out_path)

    if failed_years:
        log.warning("Failed draft years: %s", failed_years)

    return df


# ---------------------------------------------------------------------------
# Save helpers
# ---------------------------------------------------------------------------

def save_season(df: pd.DataFrame, end_year: int) -> Path:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    path = RAW_DIR / f"player_totals_{end_year}.csv"
    df.to_csv(path, index=False)
    log.info("Saved -> %s", path)
    return path


def save_advanced(df: pd.DataFrame, end_year: int) -> Path:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    path = RAW_DIR / f"player_advanced_{end_year}.csv"
    df.to_csv(path, index=False)
    log.info("Saved -> %s", path)
    return path



# ---------------------------------------------------------------------------
# Batch runners
# ---------------------------------------------------------------------------

def fetch_all(
    seasons: list[int],
    fetch_types: set[str],
    skip_existing: bool = True,
    delay: float = 4.0,
) -> None:
    """
    Fetch and save totals/advanced for every season in `seasons`.

    fetch_types : set of strings from {"totals", "advanced"}
    Bio is a one-shot fetch handled separately via fetch_player_bio().
    """
    failed: dict[str, list[int]] = {t: [] for t in fetch_types}

    for end_year in seasons:
        if "totals" in fetch_types:
            path = RAW_DIR / f"player_totals_{end_year}.csv"
            if skip_existing and path.exists():
                log.info("Skipping totals   %d (exists)", end_year)
            else:
                try:
                    save_season(fetch_season(end_year), end_year)
                except Exception as exc:
                    log.error("totals %d: %s", end_year, exc)
                    failed["totals"].append(end_year)
                time.sleep(delay)

        if "advanced" in fetch_types:
            path = RAW_DIR / f"player_advanced_{end_year}.csv"
            if skip_existing and path.exists():
                log.info("Skipping advanced %d (exists)", end_year)
            else:
                try:
                    save_advanced(fetch_advanced_season(end_year), end_year)
                except Exception as exc:
                    log.error("advanced %d: %s", end_year, exc)
                    failed["advanced"].append(end_year)
                time.sleep(delay)


    for t, years in failed.items():
        if years:
            log.warning("Failed %s seasons: %s", t, years)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch NBA player data from Basketball Reference"
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--seasons", nargs="+", type=int, metavar="YEAR")
    group.add_argument("--since",   type=int, metavar="YEAR")
    parser.add_argument(
        "--type",
        dest="fetch_type",
        choices=["all", "totals", "advanced", "bio", "draft"],
        default="all",
        help="Which data to fetch (default: all)",
    )
    parser.add_argument("--force",  action="store_true")
    parser.add_argument("--delay",  type=float, default=4.0)
    parser.add_argument(
        "--bdl-key",
        dest="bdl_key",
        default=None,
        help="BallDontLie API key (required for --type bio)",
    )
    args = parser.parse_args()

    if args.seasons:
        seasons = sorted(args.seasons)
    elif args.since:
        seasons = list(range(args.since, CURRENT_SEASON + 1))
    else:
        seasons = list(range(FIRST_SEASON, CURRENT_SEASON + 1))

    if args.fetch_type == "draft":
        fetch_draft_positions(
            skip_existing=not args.force,
            delay=args.delay,
        )
        return

    if args.fetch_type == "bio":
        if not args.bdl_key:
            import sys
            log.error("--bdl-key is required for --type bio")
            sys.exit(1)
        fetch_player_bio(api_key=args.bdl_key, skip_existing=not args.force)
        return

    fetch_types = (
        {"totals", "advanced"}
        if args.fetch_type == "all"
        else {args.fetch_type}
    )

    log.info(
        "Fetching %s for %d season(s): %d-%d",
        fetch_types, len(seasons), seasons[0], seasons[-1],
    )
    fetch_all(seasons, fetch_types, skip_existing=not args.force, delay=args.delay)


if __name__ == "__main__":
    main()