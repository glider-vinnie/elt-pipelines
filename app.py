"""
app.py  -  Movie Ratings ETL Dashboard
A Flask web dashboard to explore movie data from the ETL pipeline.
"""

import sqlite3
import json
from flask import Flask, render_template, request, jsonify
from pathlib import Path

# -- CONFIG ------------------------------------------------------------------
DB_PATH = Path("db/movies.db")

app = Flask(__name__, template_folder="templates", static_folder="static")


def get_db():
    """Get a database connection."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


# ============================================================================
#  ROUTES
# ============================================================================

@app.route("/")
def index():
    """Main dashboard page."""
    return render_template("index.html")


@app.route("/api/stats")
def api_stats():
    """Return overview statistics."""
    conn = get_db()
    cur = conn.cursor()

    total = cur.execute("SELECT COUNT(*) FROM movies").fetchone()[0]
    avg_rating = cur.execute("SELECT ROUND(AVG(rating), 2) FROM movies").fetchone()[0]
    avg_votes = cur.execute("SELECT ROUND(AVG(votes), 0) FROM movies").fetchone()[0]
    year_min = cur.execute("SELECT MIN(year) FROM movies").fetchone()[0]
    year_max = cur.execute("SELECT MAX(year) FROM movies").fetchone()[0]
    top_rated = cur.execute(
        "SELECT title, year, rating FROM movies ORDER BY rating DESC, votes DESC LIMIT 1"
    ).fetchone()

    # Genre count
    genres_raw = cur.execute("SELECT DISTINCT genre FROM movies").fetchall()
    unique_genres = set()
    for row in genres_raw:
        if row[0]:
            for g in row[0].split():
                unique_genres.add(g)

    conn.close()

    return jsonify({
        "total_movies": total,
        "avg_rating": avg_rating,
        "avg_votes": int(avg_votes) if avg_votes else 0,
        "year_range": f"{year_min}–{year_max}",
        "top_rated": {"title": top_rated[0], "year": top_rated[1], "rating": top_rated[2]} if top_rated else None,
        "unique_genres": len(unique_genres),
    })


@app.route("/api/rating-distribution")
def api_rating_distribution():
    """Return rating category distribution."""
    conn = get_db()
    rows = conn.execute(
        "SELECT rating_category, COUNT(*) as cnt FROM movies GROUP BY rating_category ORDER BY cnt DESC"
    ).fetchall()
    conn.close()
    return jsonify([{"category": r[0], "count": r[1]} for r in rows])


@app.route("/api/decade-distribution")
def api_decade_distribution():
    """Return decade distribution."""
    conn = get_db()
    rows = conn.execute(
        "SELECT decade, COUNT(*) as cnt FROM movies GROUP BY decade ORDER BY decade"
    ).fetchall()
    conn.close()
    return jsonify([{"decade": f"{r[0]}s", "count": r[1]} for r in rows])


@app.route("/api/top-movies")
def api_top_movies():
    """Return top-rated movies with optional filters."""
    limit = request.args.get("limit", 20, type=int)
    genre = request.args.get("genre", "")
    decade = request.args.get("decade", "", type=str)
    category = request.args.get("category", "")
    search = request.args.get("search", "")
    sort = request.args.get("sort", "rating")
    order = request.args.get("order", "desc")

    query = "SELECT title, year, rating, votes, genre, rating_category, decade, votes_category, movie_age FROM movies WHERE 1=1"
    params = []

    if genre:
        query += " AND genre LIKE ?"
        params.append(f"%{genre}%")
    if decade:
        query += " AND decade = ?"
        params.append(int(decade.replace("s", "")))
    if category:
        query += " AND rating_category = ?"
        params.append(category)
    if search:
        query += " AND title LIKE ?"
        params.append(f"%{search}%")

    # Validate sort column
    valid_sorts = {"rating", "votes", "year", "title", "movie_age"}
    if sort not in valid_sorts:
        sort = "rating"
    order_dir = "DESC" if order == "desc" else "ASC"
    query += f" ORDER BY {sort} {order_dir}"
    query += " LIMIT ?"
    params.append(limit)

    conn = get_db()
    rows = conn.execute(query, params).fetchall()

    # Also get total count for the filters
    count_query = "SELECT COUNT(*) FROM movies WHERE 1=1"
    count_params = []
    if genre:
        count_query += " AND genre LIKE ?"
        count_params.append(f"%{genre}%")
    if decade:
        count_query += " AND decade = ?"
        count_params.append(int(decade.replace("s", "")))
    if category:
        count_query += " AND rating_category = ?"
        count_params.append(category)
    if search:
        count_query += " AND title LIKE ?"
        count_params.append(f"%{search}%")

    total = conn.execute(count_query, count_params).fetchone()[0]
    conn.close()

    return jsonify({
        "total": total,
        "movies": [
            {
                "title": r[0], "year": r[1], "rating": r[2], "votes": r[3],
                "genre": r[4], "rating_category": r[5], "decade": r[6],
                "votes_category": r[7], "movie_age": r[8],
            }
            for r in rows
        ],
    })


@app.route("/api/genres")
def api_genres():
    """Return unique genre keywords."""
    conn = get_db()
    rows = conn.execute("SELECT genre FROM movies").fetchall()
    conn.close()
    genre_counts = {}
    for row in rows:
        if row[0]:
            for g in row[0].split():
                genre_counts[g] = genre_counts.get(g, 0) + 1
    # Sort by count descending
    sorted_genres = sorted(genre_counts.items(), key=lambda x: x[1], reverse=True)
    return jsonify([{"genre": g, "count": c} for g, c in sorted_genres])


@app.route("/api/rating-by-decade")
def api_rating_by_decade():
    """Return average rating per decade."""
    conn = get_db()
    rows = conn.execute(
        "SELECT decade, ROUND(AVG(rating), 2) as avg_rating, COUNT(*) as cnt "
        "FROM movies GROUP BY decade ORDER BY decade"
    ).fetchall()
    conn.close()
    return jsonify([{"decade": f"{r[0]}s", "avg_rating": r[1], "count": r[2]} for r in rows])


@app.route("/api/votes-distribution")
def api_votes_distribution():
    """Return votes category distribution."""
    conn = get_db()
    rows = conn.execute(
        "SELECT votes_category, COUNT(*) as cnt FROM movies GROUP BY votes_category ORDER BY cnt DESC"
    ).fetchall()
    conn.close()
    return jsonify([{"category": r[0], "count": r[1]} for r in rows])


# ============================================================================
#  MAIN
# ============================================================================
if __name__ == "__main__":
    if not DB_PATH.exists():
        print(f"ERROR: Database not found at {DB_PATH}")
        print("Run the ETL pipeline first: python extract.py && python transform.py && python load.py")
        exit(1)
    import io, sys
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    print("\n Movie Ratings Dashboard")
    print("   http://localhost:5000\n")
    app.run(debug=True, host="0.0.0.0", port=5000)
