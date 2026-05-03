import os
import sys
import logging
import pandas as pd
import numpy as np
from pathlib import Path

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(levelname)-8s │ %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("extract")


# ── Constants ──────────────────────────────────────────────────────────────
RAW_DATA_DIR = Path("data")
RAW_CSV_PATH = RAW_DATA_DIR / "raw_movies.csv"
SOURCE_CSV   = Path("data") / "source_movies.csv"   # generated if missing
MIN_ROWS     = 5_000


# =====================================================================
#  1.  SYNTHETIC DATA GENERATOR  (runs only when source CSV is absent)
# =====================================================================
def _generate_source_csv(path: Path, n_rows: int = 6_000) -> Path:
    """
    Create a realistic IMDb-style CSV so the pipeline can run out-of-the-box
    without downloading anything.  Titles are procedurally assembled from
    real-sounding fragments; ratings follow a realistic distribution.
    """
    log.info("Source CSV not found — generating %s synthetic movie records …", n_rows)
    rng = np.random.default_rng(42)

    # ── Title building blocks ──────────────────────────────────────────
    adjectives = [
        "Dark", "Lost", "Silent", "Broken", "Last", "Eternal", "Hidden",
        "Crimson", "Golden", "Iron", "Frozen", "Burning", "Savage", "Fallen",
        "Sacred", "Wicked", "Brave", "Midnight", "Rising", "Shattered",
        "Distant", "Hollow", "Fading", "Twisted", "Bitter", "Rogue",
        "Velvet", "Ancient", "Neon", "Electric", "Cursed", "Phantom",
        "Steel", "Shadow", "Crystal", "Amber", "Scarlet", "Emerald",
        "Cosmic", "Deadly", "Infinite", "Rapid", "Noble", "Primal",
        "Mystic", "Serene", "Fierce", "Gentle", "Radiant", "Obscure",
    ]
    nouns = [
        "Knight", "Storm", "Empire", "Dream", "Hunter", "Legacy", "Horizon",
        "Requiem", "Shadow", "Throne", "Fury", "Voyage", "Blade", "Phoenix",
        "Enigma", "Fortress", "Redemption", "Inferno", "Echo", "Vanguard",
        "Destiny", "Harbor", "Frontier", "Chronicle", "Oath", "Reckoning",
        "Cascade", "Labyrinth", "Mirage", "Zenith", "Abyss", "Tundra",
        "Citadel", "Dominion", "Parish", "Reverie", "Specter", "Tempest",
        "Wanderer", "Oracle", "Glacier", "Meridian", "Paradox", "Nexus",
        "Pulse", "Rift", "Solstice", "Titan", "Vortex", "Wraith",
    ]
    patterns = [
        lambda a, n: f"The {a} {n}",
        lambda a, n: f"{n} of the {a}",
        lambda a, n: f"{a} {n}",
        lambda a, n: f"The {n}",
        lambda a, n: f"{n}: {a} Rising",
        lambda a, n: f"{a} {n}s",
        lambda a, n: f"Project {n}",
        lambda a, n: f"The Last {n}",
        lambda a, n: f"Beyond the {a} {n}",
        lambda a, n: f"{n} Protocol",
    ]

    genres_pool = [
        "Action", "Drama", "Comedy", "Thriller", "Sci-Fi", "Horror",
        "Romance", "Adventure", "Crime", "Mystery", "Animation",
        "Fantasy", "Documentary", "Biography", "War", "Musical",
        "Western", "Family", "Sport", "History",
    ]

    # ── Generate rows ─────────────────────────────────────────────────
    titles = []
    seen = set()
    while len(titles) < n_rows:
        a = rng.choice(adjectives)
        n = rng.choice(nouns)
        pat = rng.choice(patterns)
        t = pat(a, n)
        if t not in seen:
            seen.add(t)
            titles.append(t)

    years    = rng.integers(1970, 2027, size=n_rows)
    ratings  = np.round(rng.normal(loc=6.5, scale=1.4, size=n_rows).clip(1.0, 10.0), 1)
    votes    = (10 ** rng.uniform(2, 6, size=n_rows)).astype(int)

    genre_lists = []
    for _ in range(n_rows):
        k = rng.integers(1, 4)  # 1-3 genres per movie
        g = rng.choice(genres_pool, size=k, replace=False)
        genre_lists.append(", ".join(g))

    df = pd.DataFrame({
        "title":  titles,
        "year":   years,
        "rating": ratings,
        "votes":  votes,
        "genre":  genre_lists,
    })

    # Inject a tiny amount of realistic messiness (< 1 %)
    messy_idx = rng.choice(n_rows, size=int(n_rows * 0.005), replace=False)
    df.loc[messy_idx[:len(messy_idx)//2], "rating"] = np.nan
    df.loc[messy_idx[len(messy_idx)//2:], "votes"]  = np.nan

    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    log.info("Synthetic source saved → %s  (%s rows)", path, len(df))
    return path


# =====================================================================
#  2.  EXTRACT
# =====================================================================
def extract(source_path: Path = SOURCE_CSV) -> pd.DataFrame:
    """
    Load movie data from *source_path*, validate it, and return a clean
    DataFrame with the canonical schema.

    Parameters
    ----------
    source_path : Path
        Path to the source CSV.  If it doesn't exist a synthetic file is
        generated automatically.

    Returns
    -------
    pd.DataFrame
        Columns: title, year, rating, votes, genre
    """
    # ── Ensure source exists ──────────────────────────────────────────
    if not source_path.exists():
        log.warning("Source file '%s' not found.", source_path)
        _generate_source_csv(source_path)

    # ── Read CSV ──────────────────────────────────────────────────────
    try:
        log.info("Reading CSV → %s", source_path)
        df = pd.read_csv(source_path)
    except FileNotFoundError:
        log.error("File not found: %s. Check the path and try again.", source_path)
        sys.exit(1)
    except pd.errors.EmptyDataError:
        log.error("File is empty: %s", source_path)
        sys.exit(1)
    except pd.errors.ParserError as exc:
        log.error("CSV parse error: %s", exc)
        sys.exit(1)
    except Exception as exc:
        log.error("Unexpected error reading CSV: %s", exc)
        sys.exit(1)

    # ── Validate schema ──────────────────────────────────────────────
    required_cols = {"title", "year", "rating", "votes", "genre"}
    missing_cols  = required_cols - set(df.columns)
    if missing_cols:
        log.error("Missing required columns: %s", missing_cols)
        sys.exit(1)

    # Keep only the canonical columns (in order)
    df = df[["title", "year", "rating", "votes", "genre"]].copy()

    # ── Coerce types (skip invalid rows) ─────────────────────────────
    initial_len = len(df)

    df["year"]   = pd.to_numeric(df["year"],   errors="coerce")
    df["rating"] = pd.to_numeric(df["rating"], errors="coerce")
    df["votes"]  = pd.to_numeric(df["votes"],  errors="coerce")

    # Drop rows that are entirely empty
    df.dropna(how="all", inplace=True)

    skipped = initial_len - len(df)
    if skipped:
        log.warning("Skipped %d fully-empty rows.", skipped)

    # ── Validate row count ────────────────────────────────────────────
    if df.empty:
        log.error("DataFrame is empty after loading — aborting.")
        sys.exit(1)

    if len(df) < MIN_ROWS:
        log.warning(
            "Dataset has only %d rows (minimum recommended: %d).",
            len(df), MIN_ROWS,
        )

    log.info("Extraction complete — %d rows loaded.", len(df))
    return df


# =====================================================================
#  3.  SAVE RAW DATA
# =====================================================================
def save_raw(df: pd.DataFrame, path: Path = RAW_CSV_PATH) -> None:
    """Persist the extracted DataFrame to CSV."""
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    log.info("Raw data saved → %s", path)


# =====================================================================
#  4.  SUMMARY REPORT
# =====================================================================
def print_summary(df: pd.DataFrame) -> None:
    """Print a rich summary of the extracted data."""
    sep = "─" * 60

    print(f"\n{'═' * 60}")
    print("  📊  EXTRACTION SUMMARY")
    print(f"{'═' * 60}\n")

    # ── Total rows ────────────────────────────────────────────────────
    print(f"  Total rows extracted : {len(df):,}")
    print(f"  Total columns        : {len(df.columns)}")
    print()

    # ── Column names & dtypes ─────────────────────────────────────────
    print(f"  {'Column':<12} {'Dtype':<12} {'Non-Null':>10} {'Null':>8}")
    print(f"  {sep}")
    for col in df.columns:
        non_null = df[col].notna().sum()
        null     = df[col].isna().sum()
        dtype    = str(df[col].dtype)
        print(f"  {col:<12} {dtype:<12} {non_null:>10,} {null:>8,}")
    print()

    # ── Missing values total ──────────────────────────────────────────
    total_missing = df.isna().sum().sum()
    print(f"  Total missing values : {total_missing:,}")
    if total_missing:
        print("  Missing breakdown    :")
        for col, cnt in df.isna().sum().items():
            if cnt:
                print(f"    • {col}: {cnt:,}")
    print()

    # ── Rating statistics ─────────────────────────────────────────────
    print(f"  {sep}")
    print("  Rating Statistics")
    print(f"  {sep}")
    print(f"  {'Mean':<10} : {df['rating'].mean():.2f}")
    print(f"  {'Median':<10} : {df['rating'].median():.2f}")
    print(f"  {'Std Dev':<10} : {df['rating'].std():.2f}")
    print(f"  {'Min':<10} : {df['rating'].min():.1f}")
    print(f"  {'Max':<10} : {df['rating'].max():.1f}")
    print()

    # ── Year range ────────────────────────────────────────────────────
    print(f"  Year range : {int(df['year'].min())} – {int(df['year'].max())}")
    print()

    # ── Top genres ────────────────────────────────────────────────────
    all_genres = df["genre"].dropna().str.split(r",\s*").explode()
    top_genres = all_genres.value_counts().head(10)
    print(f"  {sep}")
    print("  Top 10 Genres")
    print(f"  {sep}")
    for genre, count in top_genres.items():
        bar = "█" * int(count / top_genres.max() * 25)
        print(f"  {genre:<14} {count:>5,}  {bar}")
    print()

    # ── Sample rows ───────────────────────────────────────────────────
    print(f"  {sep}")
    print("  First 5 Rows")
    print(f"  {sep}")
    print(df.head().to_string(index=False))

    print(f"\n{'═' * 60}")
    print("  ✅  Extraction phase complete!")
    print(f"{'═' * 60}\n")


# =====================================================================
#  MAIN
# =====================================================================
def main() -> pd.DataFrame:
    """Run the full extract pipeline and return the DataFrame."""
    print("\n🎬  Movie Ratings ETL — EXTRACT phase starting …\n")

    df = extract()
    save_raw(df)
    print_summary(df)

    return df


if __name__ == "__main__":
    main()
