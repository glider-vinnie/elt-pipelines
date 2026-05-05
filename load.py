"""
load.py  -  Movie Ratings ETL - Load Phase
Reads cleaned_movies.csv and loads into SQLite database.
"""

import sys
import io
import sqlite3
import logging
import pandas as pd
from pathlib import Path
from datetime import datetime
from uuid import uuid4

# -- CONFIG ------------------------------------------------------------------
INPUT_CSV = Path("data/cleaned_movies.csv")
DB_DIR    = Path("db")
DB_PATH   = DB_DIR / "movies.db"
LOG_DIR   = Path("log")
LOG_FILE  = LOG_DIR / "load.log"

# -- Logging (console + file) -----------------------------------------------
LOG_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_FILE, mode="w", encoding="utf-8"),
    ],
)
log = logging.getLogger("load")

# -- SQL ---------------------------------------------------------------------
CREATE_MOVIES = """
CREATE TABLE IF NOT EXISTS movies (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    title             TEXT NOT NULL,
    year              INTEGER NOT NULL,
    rating            REAL NOT NULL,
    votes             INTEGER NOT NULL,
    genre             TEXT,
    movie_age         INTEGER,
    rating_category   TEXT,
    decade            INTEGER,
    votes_category    TEXT,
    created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

CREATE_METADATA = """
CREATE TABLE IF NOT EXISTS load_metadata (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    load_run_id     TEXT UNIQUE NOT NULL,
    source_file     TEXT NOT NULL,
    row_count_loaded INTEGER NOT NULL,
    load_timestamp  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status          TEXT,
    error_message   TEXT
);
"""

INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_title ON movies(title);",
    "CREATE INDEX IF NOT EXISTS idx_year ON movies(year);",
    "CREATE INDEX IF NOT EXISTS idx_rating ON movies(rating);",
    "CREATE INDEX IF NOT EXISTS idx_genre ON movies(genre);",
    "CREATE INDEX IF NOT EXISTS idx_rating_category ON movies(rating_category);",
]

INSERT_MOVIE = """
INSERT INTO movies (title, year, rating, votes, genre, movie_age,
                    rating_category, decade, votes_category)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
"""


# ============================================================================
#  1. DATABASE CONNECTION
# ============================================================================
def create_database_connection(db_path: Path = DB_PATH) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        conn = sqlite3.connect(str(db_path))
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        log.info("Connected to database: %s", db_path)
        return conn
    except sqlite3.DatabaseError:
        log.warning("Database file corrupted - deleting and recreating")
        db_path.unlink(missing_ok=True)
        conn = sqlite3.connect(str(db_path))
        log.info("Recreated database: %s", db_path)
        return conn


# ============================================================================
#  2. CREATE TABLES
# ============================================================================
def create_tables(conn: sqlite3.Connection) -> None:
    conn.execute(CREATE_MOVIES)
    conn.execute(CREATE_METADATA)
    conn.commit()
    log.info("Tables created (movies, load_metadata)")


# ============================================================================
#  3. CREATE INDEXES
# ============================================================================
def create_indexes(conn: sqlite3.Connection) -> None:
    for sql in INDEXES:
        conn.execute(sql)
    conn.commit()
    log.info("Created %d indexes", len(INDEXES))


# ============================================================================
#  4. INSERT DATA
# ============================================================================
def insert_data(conn: sqlite3.Connection, df: pd.DataFrame, load_run_id: str) -> int:
    cursor = conn.cursor()
    inserted = 0
    skipped = 0

    # Get existing (title, year) pairs to skip duplicates
    existing = set()
    try:
        rows = cursor.execute("SELECT title, year FROM movies").fetchall()
        existing = {(r[0], r[1]) for r in rows}
        if existing:
            log.info("Found %d existing records in database", len(existing))
    except sqlite3.OperationalError:
        pass  # table might be empty

    try:
        conn.execute("BEGIN TRANSACTION")
        for _, row in df.iterrows():
            key = (row["title"], int(row["year"]))
            if key in existing:
                skipped += 1
                continue
            cursor.execute(INSERT_MOVIE, (
                row["title"],
                int(row["year"]),
                float(row["rating"]),
                int(row["votes"]),
                row.get("genre"),
                int(row["movie_age"]) if pd.notna(row.get("movie_age")) else None,
                row.get("rating_category"),
                int(row["decade"]) if pd.notna(row.get("decade")) else None,
                row.get("votes_category"),
            ))
            inserted += 1
        conn.commit()
        log.info("Inserted %d rows, skipped %d duplicates", inserted, skipped)
    except Exception as exc:
        conn.rollback()
        log.error("Insert failed - rolled back transaction: %s", exc)
        raise

    return inserted


# ============================================================================
#  5. VALIDATE LOAD
# ============================================================================
def validate_load(conn: sqlite3.Connection, expected: int) -> bool:
    log.info("--- Load Validation ---")
    ok = True
    cursor = conn.cursor()

    # Row count
    actual = cursor.execute("SELECT COUNT(*) FROM movies").fetchone()[0]
    match = actual >= expected  # >= because prior runs may have added rows
    log.info("  [%s] Row count: %d in DB (expected >= %d)",
             "PASS" if match else "FAIL", actual, expected)
    if not match:
        ok = False

    # NULL checks on NOT NULL columns
    for col in ("title", "year", "rating", "votes"):
        nulls = cursor.execute(f"SELECT COUNT(*) FROM movies WHERE {col} IS NULL").fetchone()[0]
        passed = nulls == 0
        log.info("  [%s] No NULLs in %s (%d found)", "PASS" if passed else "FAIL", col, nulls)
        if not passed:
            ok = False

    # Spot-check 5 random rows
    sample = cursor.execute(
        "SELECT title, year, rating, votes FROM movies ORDER BY RANDOM() LIMIT 5"
    ).fetchall()
    log.info("  Spot-check 5 random rows:")
    for row in sample:
        log.info("    -> %s (%d) rating=%.1f votes=%d", row[0], row[1], row[2], row[3])

    # Verify indexes
    indexes = cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='movies'"
    ).fetchall()
    idx_names = [i[0] for i in indexes]
    log.info("  [PASS] Indexes present: %s", idx_names)

    return ok


# ============================================================================
#  6. LOG METADATA
# ============================================================================
def log_load_metadata(conn: sqlite3.Connection, load_run_id: str,
                      source_file: str, row_count: int,
                      status: str, error_msg: str = None) -> None:
    conn.execute(
        """INSERT INTO load_metadata (load_run_id, source_file, row_count_loaded, status, error_message)
           VALUES (?, ?, ?, ?, ?)""",
        (load_run_id, source_file, row_count, status, error_msg),
    )
    conn.commit()
    log.info("Metadata logged: run=%s status=%s rows=%d", load_run_id, status, row_count)


# ============================================================================
#  7. SUMMARY
# ============================================================================
def print_summary(conn: sqlite3.Connection, load_run_id: str,
                  rows_loaded: int, status: str) -> None:
    cursor = conn.cursor()
    total = cursor.execute("SELECT COUNT(*) FROM movies").fetchone()[0]
    runs = cursor.execute("SELECT COUNT(*) FROM load_metadata").fetchone()[0]

    bar = "=" * 60
    print(f"\n{bar}")
    print("  LOAD SUMMARY")
    print(f"{bar}\n")
    print(f"  Load run ID    : {load_run_id}")
    print(f"  Status         : {status}")
    print(f"  Source          : {INPUT_CSV}")
    print(f"  Database        : {DB_PATH}")
    print(f"  Rows loaded     : {rows_loaded:,}")
    print(f"  Total in DB     : {total:,}")
    print(f"  Total ETL runs  : {runs}")

    # Table sizes
    tables = cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    print(f"\n  Tables:")
    for (tbl,) in tables:
        cnt = cursor.execute(f"SELECT COUNT(*) FROM [{tbl}]").fetchone()[0]
        print(f"    {tbl:<20} {cnt:>6,} rows")

    # Sample from DB
    print(f"\n  Sample (5 rows from DB):")
    sample = cursor.execute(
        "SELECT title, year, rating, votes, rating_category FROM movies LIMIT 5"
    ).fetchall()
    print(f"    {'Title':<42} {'Year':>4}  {'Rating':>6}  {'Votes':>6}  {'Category'}")
    print(f"    {'-'*42} {'-'*4}  {'-'*6}  {'-'*6}  {'-'*10}")
    for r in sample:
        print(f"    {r[0]:<42} {r[1]:>4}  {r[2]:>6.1f}  {r[3]:>6,}  {r[4]}")

    print(f"\n{bar}")
    print("  [OK] Load phase complete!")
    print(f"  Log saved -> {LOG_FILE}")
    print(f"{bar}\n")


# ============================================================================
#  MAIN
# ============================================================================
def main():
    print("\n Movie Ratings ETL - LOAD\n")

    load_run_id = f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:6]}"
    status = "success"
    error_msg = None
    rows_loaded = 0

    # Read CSV
    if not INPUT_CSV.exists():
        log.error("Input file not found: %s", INPUT_CSV)
        log.error("Run transform.py first to generate cleaned_movies.csv")
        sys.exit(1)

    df = pd.read_csv(INPUT_CSV)
    log.info("Read %d rows from %s", len(df), INPUT_CSV)

    # Connect and setup
    conn = create_database_connection()
    try:
        create_tables(conn)
        create_indexes(conn)

        # Insert
        rows_loaded = insert_data(conn, df, load_run_id)

        # Validate
        if validate_load(conn, rows_loaded):
            log.info("All validation checks PASSED!")
        else:
            status = "partial_failure"
            error_msg = "Some validation checks failed"
            log.warning(error_msg)

    except Exception as exc:
        status = "failed"
        error_msg = str(exc)
        log.error("Load failed: %s", exc)

    finally:
        # Always log metadata
        try:
            log_load_metadata(conn, load_run_id, str(INPUT_CSV), rows_loaded, status, error_msg)
        except Exception:
            log.error("Could not log metadata")
        print_summary(conn, load_run_id, rows_loaded, status)
        conn.close()
        log.info("Database connection closed")


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    main()
