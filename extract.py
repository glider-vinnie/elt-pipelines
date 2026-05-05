"""
extract.py  –  Movie Ratings ETL · Extract Phase
Loads a CSV, validates & cleans it, saves raw output, prints a summary.
"""

import sys
import io
import logging
import pandas as pd
from pathlib import Path

# ── CONFIG (edit these) ────────────────────────────────────────────────
CONFIG = {
    "csv_path":    r"C:\Users\Vaishnavi\.cache\kagglehub\datasets\abdallahwagih\movies\versions\1\movies.csv",
    "api_key":     "",                   # reserved for future API-based extraction
    "output_dir":  "data",               # where raw_movies.csv lands
    "max_rows":    None,                  # None = all rows; set int to limit
}

# ── COLUMN MAP  (source name → canonical name) ────────────────────────
COLUMN_MAP = {
    "title":        "title",
    "release_date": "year",
    "vote_average": "rating",
    "vote_count":   "votes",
    "genres":       "genre",
}

REQUIRED = set(COLUMN_MAP.keys())

# ── Logging ────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(levelname)-8s │ %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("extract")


# ── EXTRACT ────────────────────────────────────────────────────────────
def extract() -> pd.DataFrame:
    """Read, validate, clean, and return a DataFrame with the canonical schema."""
    src = Path(CONFIG["csv_path"])

    # 1. Read
    try:
        df = pd.read_csv(src, nrows=CONFIG["max_rows"])
        log.info("Loaded %d rows from %s", len(df), src.name)
    except Exception as exc:
        log.error("Cannot read CSV: %s", exc)
        sys.exit(1)

    # 2. Check required columns exist
    missing = REQUIRED - set(df.columns)
    if missing:
        log.error("Missing columns: %s", missing)
        sys.exit(1)

    # 3. Keep & rename only the columns we care about
    df = df[list(COLUMN_MAP.keys())].rename(columns=COLUMN_MAP)

    # 4. Clean – coerce types, handle dirty data
    df["year"]   = pd.to_datetime(df["year"], errors="coerce").dt.year
    df["rating"] = pd.to_numeric(df["rating"], errors="coerce")
    df["votes"]  = pd.to_numeric(df["votes"],  errors="coerce")
    df["genre"]  = df["genre"].fillna("Unknown")
    df["title"]  = df["title"].fillna("Untitled")

    before = len(df)
    df.dropna(subset=["year", "rating", "votes"], inplace=True)
    dropped = before - len(df)
    if dropped:
        log.warning("Dropped %d rows with unusable nulls", dropped)

    df["year"] = df["year"].astype(int)
    log.info("Extraction done - %d clean rows", len(df))
    return df


# ── SAVE ───────────────────────────────────────────────────────────────
def save_raw(df: pd.DataFrame) -> Path:
    out_dir = Path(CONFIG["output_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "raw_movies.csv"
    df.to_csv(out_path, index=False)
    log.info("Saved → %s", out_path)
    return out_path


# ── SUMMARY ────────────────────────────────────────────────────────────
def print_summary(df: pd.DataFrame) -> None:
    bar = "=" * 55
    print(f"\n{bar}")
    print("  EXTRACTION SUMMARY")
    print(f"{bar}\n")
    print(f"  Rows    : {len(df):,}")
    print(f"  Columns : {list(df.columns)}")
    print(f"  Nulls   : {df.isna().sum().sum()}")
    print(f"  Years   : {int(df['year'].min())} – {int(df['year'].max())}")
    print(f"  Rating  : {df['rating'].mean():.2f} avg  (min {df['rating'].min()}, max {df['rating'].max()})")
    print(f"\n  First 5 rows:\n{df.head().to_string(index=False)}")
    print(f"\n{bar}\n  [OK] Extract phase complete!\n{bar}\n")


# ── MAIN ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    print("\n Movie Ratings ETL - EXTRACT\n")
    df = extract()
    save_raw(df)
    print_summary(df)
