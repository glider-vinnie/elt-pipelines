

// ── State ────────────────────────────────────────────────────────
const state = {
    sort: "rating",
    order: "desc",
    limit: 20,
    search: "",
    category: "",
    decade: "",
    genre: "",
};

let debounceTimer = null;

// ── Init ─────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
    loadStats();
    loadRatingDistribution();
    loadDecadeDistribution();
    loadAvgByDecade();
    loadVotesDistribution();
    loadGenres();
    loadMovies();

    // Search input
    document.getElementById("search-input").addEventListener("input", (e) => {
        state.search = e.target.value.trim();
        state.limit = 20;
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(() => loadMovies(), 300);
    });

    // Filter dropdowns
    document.getElementById("filter-category").addEventListener("change", (e) => {
        state.category = e.target.value;
        state.limit = 20;
        loadMovies();
    });

    document.getElementById("filter-decade").addEventListener("change", (e) => {
        state.decade = e.target.value;
        state.limit = 20;
        loadMovies();
    });

    document.getElementById("filter-genre").addEventListener("change", (e) => {
        state.genre = e.target.value;
        state.limit = 20;
        loadMovies();
    });

    // Sortable headers
    document.querySelectorAll(".sortable").forEach((th) => {
        th.addEventListener("click", () => {
            const col = th.dataset.sort;
            if (state.sort === col) {
                state.order = state.order === "desc" ? "asc" : "desc";
            } else {
                state.sort = col;
                state.order = col === "title" ? "asc" : "desc";
            }
            state.limit = 20;
            updateSortArrows();
            loadMovies();
        });
    });

    // Load more
    document.getElementById("load-more-btn").addEventListener("click", () => {
        state.limit += 20;
        loadMovies();
    });
});

// ── API Helpers ──────────────────────────────────────────────────
async function fetchJSON(url) {
    const res = await fetch(url);
    return res.json();
}

function formatNum(n) {
    if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + "M";
    if (n >= 1_000) return (n / 1_000).toFixed(1) + "K";
    return n.toLocaleString();
}

// ── Stats ────────────────────────────────────────────────────────
async function loadStats() {
    const s = await fetchJSON("/api/stats");
    animateValue("val-total", 0, s.total_movies, 800);
    document.getElementById("val-rating").textContent = s.avg_rating;
    document.getElementById("val-votes").textContent = formatNum(s.avg_votes);
    document.getElementById("val-years").textContent = s.year_range;
    document.getElementById("val-genres").textContent = s.unique_genres;
    if (s.top_rated) {
        document.getElementById("val-top").textContent = s.top_rated.rating + " ⭐";
        document.getElementById("lbl-top").textContent = s.top_rated.title + " (" + s.top_rated.year + ")";
    }
}

function animateValue(id, start, end, duration) {
    const el = document.getElementById(id);
    const range = end - start;
    const step = Math.max(1, Math.floor(range / 60));
    let current = start;
    const timer = setInterval(() => {
        current += step;
        if (current >= end) {
            current = end;
            clearInterval(timer);
        }
        el.textContent = current.toLocaleString();
    }, duration / 60);
}

// ── Rating Distribution ──────────────────────────────────────────
async function loadRatingDistribution() {
    const data = await fetchJSON("/api/rating-distribution");
    const container = document.getElementById("rating-bars");
    const max = Math.max(...data.map((d) => d.count));
    const total = data.reduce((a, b) => a + b.count, 0);

    const colorMap = {
        Excellent: "bar-excellent",
        Good: "bar-good",
        Average: "bar-average",
        Poor: "bar-poor",
    };

    container.innerHTML = data
        .map((d) => {
            const pct = ((d.count / max) * 100).toFixed(1);
            const share = ((d.count / total) * 100).toFixed(1);
            const cls = colorMap[d.category] || "bar-default";
            return `<div class="bar-row">
                <span class="bar-label">${d.category || "N/A"}</span>
                <div class="bar-track">
                    <div class="bar-fill ${cls}" style="width: ${pct}%">
                        <span class="bar-fill-text">${share}%</span>
                    </div>
                </div>
                <span class="bar-count">${formatNum(d.count)}</span>
            </div>`;
        })
        .join("");
}

// ── Decade Distribution ──────────────────────────────────────────
async function loadDecadeDistribution() {
    const data = await fetchJSON("/api/decade-distribution");
    const container = document.getElementById("decade-bars");
    const max = Math.max(...data.map((d) => d.count));

    // Populate decade filter
    const sel = document.getElementById("filter-decade");
    data.forEach((d) => {
        const opt = document.createElement("option");
        opt.value = d.decade;
        opt.textContent = d.decade;
        sel.appendChild(opt);
    });

    container.innerHTML = data
        .map((d, i) => {
            const pct = ((d.count / max) * 100).toFixed(1);
            const cls = "bar-decade-" + (i % 6);
            return `<div class="bar-row">
                <span class="bar-label">${d.decade}</span>
                <div class="bar-track">
                    <div class="bar-fill ${cls}" style="width: ${pct}%">
                        <span class="bar-fill-text">${d.count.toLocaleString()}</span>
                    </div>
                </div>
                <span class="bar-count">${formatNum(d.count)}</span>
            </div>`;
        })
        .join("");
}

// ── Avg Rating by Decade ─────────────────────────────────────────
async function loadAvgByDecade() {
    const data = await fetchJSON("/api/rating-by-decade");
    const container = document.getElementById("avg-decade-chart");

    container.innerHTML = '<div class="dot-chart">' +
        data
            .map((d) => {
                const pct = ((d.avg_rating / 10) * 100).toFixed(1);
                return `<div class="dot-row">
                    <span class="dot-label">${d.decade}</span>
                    <div class="dot-track">
                        <div class="dot-fill" style="width: ${pct}%">
                            <div class="dot-marker"></div>
                        </div>
                    </div>
                    <span class="dot-value">${d.avg_rating}</span>
                </div>`;
            })
            .join("") +
        "</div>";
}

// ── Votes Distribution ───────────────────────────────────────────
async function loadVotesDistribution() {
    const data = await fetchJSON("/api/votes-distribution");
    const container = document.getElementById("votes-bars");
    const max = Math.max(...data.map((d) => d.count));
    const total = data.reduce((a, b) => a + b.count, 0);

    container.innerHTML = data
        .map((d, i) => {
            const pct = ((d.count / max) * 100).toFixed(1);
            const share = ((d.count / total) * 100).toFixed(1);
            const cls = "bar-votes-" + (i % 4);
            return `<div class="bar-row">
                <span class="bar-label">${d.category || "N/A"}</span>
                <div class="bar-track">
                    <div class="bar-fill ${cls}" style="width: ${pct}%">
                        <span class="bar-fill-text">${share}%</span>
                    </div>
                </div>
                <span class="bar-count">${formatNum(d.count)}</span>
            </div>`;
        })
        .join("");
}

// ── Genres ────────────────────────────────────────────────────────
async function loadGenres() {
    const data = await fetchJSON("/api/genres");
    const container = document.getElementById("genre-cloud");

    // Populate genre filter
    const sel = document.getElementById("filter-genre");
    data.forEach((d) => {
        const opt = document.createElement("option");
        opt.value = d.genre;
        opt.textContent = d.genre;
        sel.appendChild(opt);
    });

    container.innerHTML = data
        .slice(0, 25)
        .map(
            (d, i) =>
                `<span class="genre-tag" style="animation-delay: ${i * 0.04}s" onclick="filterByGenre('${d.genre}')">
                    ${d.genre}
                    <span class="genre-count">${formatNum(d.count)}</span>
                </span>`
        )
        .join("");
}

function filterByGenre(genre) {
    document.getElementById("filter-genre").value = genre;
    state.genre = genre;
    state.limit = 20;
    loadMovies();
    document.getElementById("section-movies").scrollIntoView({ behavior: "smooth" });
}

// ── Movies Table ─────────────────────────────────────────────────
async function loadMovies() {
    const params = new URLSearchParams({
        limit: state.limit,
        sort: state.sort,
        order: state.order,
    });
    if (state.search) params.set("search", state.search);
    if (state.category) params.set("category", state.category);
    if (state.decade) params.set("decade", state.decade);
    if (state.genre) params.set("genre", state.genre);

    const data = await fetchJSON("/api/top-movies?" + params);
    const tbody = document.getElementById("movie-tbody");
    const info = document.getElementById("table-info");
    const btn = document.getElementById("load-more-btn");

    info.textContent = `Showing ${data.movies.length} of ${data.total.toLocaleString()} movies`;
    btn.style.display = data.movies.length < data.total ? "inline-block" : "none";

    tbody.innerHTML = data.movies
        .map((m) => {
            const catCls = (m.rating_category || "").toLowerCase();
            const starCls = m.rating >= 8 ? "high" : m.rating >= 6 ? "mid" : "low";
            return `<tr>
                <td>${escapeHTML(m.title)}</td>
                <td>${m.year}</td>
                <td><span class="rating-star ${starCls}">${m.rating.toFixed(1)}</span></td>
                <td>${m.votes.toLocaleString()}</td>
                <td>${escapeHTML(m.genre || "—")}</td>
                <td><span class="rating-badge ${catCls}">${m.rating_category || "—"}</span></td>
            </tr>`;
        })
        .join("");
}

function updateSortArrows() {
    document.querySelectorAll(".sortable").forEach((th) => {
        const arrow = th.querySelector(".sort-arrow");
        if (th.dataset.sort === state.sort) {
            th.classList.add("active");
            arrow.textContent = state.order === "desc" ? " ▼" : " ▲";
        } else {
            th.classList.remove("active");
            arrow.textContent = "";
        }
    });
}

function escapeHTML(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
}
