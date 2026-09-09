import re
import sqlite3
import pandas as pd
import requests
import streamlit as st

# --- DATENBANK & API LOGIK ---
DB_PATH = "autodarts_league.db"


def init_db():
    """Initialisiert die SQLite-Tabellen für Spiele und Statistiken."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS matches (
                match_id TEXT PRIMARY KEY,
                created_at TEXT,
                variant TEXT,
                mode TEXT,
                player1 TEXT,
                player2 TEXT,
                p1_legs INTEGER,
                p2_legs INTEGER,
                winner TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS match_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                match_id TEXT,
                player_name TEXT,
                legs_won INTEGER,
                sets_won INTEGER,
                avg_3dart REAL,
                first9_avg REAL,
                checkout_pct REAL,
                high_checkout INTEGER,
                s100 INTEGER,
                s140 INTEGER,
                s180 INTEGER,
                FOREIGN KEY (match_id) REFERENCES matches (match_id),
                UNIQUE(match_id, player_name)
            )
        """)
        conn.commit()


def extract_match_id(url_or_id: str) -> str:
    """Extrahiert die Match-UUID aus einem Autodarts-Link oder Text."""
    uuid_pattern = (
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
    )
    match = re.search(uuid_pattern, url_or_id, re.IGNORECASE)
    if match:
        return match.group(0)
    raise ValueError("Keine gültige Autodarts Match-ID gefunden.")


def save_match_to_db(match_data: dict):
    """Speichert Match-Ergebnisse und Spieler-Statistiken in SQLite."""
    match_id = match_data.get("id")
    variant = match_data.get("variant", "501")
    mode = match_data.get("mode", "Legs")
    created_at = match_data.get("createdAt", "")

    players = match_data.get("players", [])
    p1 = players[0] if len(players) > 0 else {}
    p2 = players[1] if len(players) > 1 else {}

    p1_name, p1_legs = p1.get("name", "Spieler 1"), p1.get("legs", 0)
    p2_name, p2_legs = p2.get("name", "Spieler 2"), p2.get("legs", 0)

    # Es gibt nur einen Sieger (3 Punkte), kein Unentschieden
    winner = p1_name if p1_legs > p2_legs else p2_name
    stats_list = match_data.get("stats", [])

    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO matches VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                match_id,
                created_at,
                variant,
                mode,
                p1_name,
                p2_name,
                p1_legs,
                p2_legs,
                winner,
            ),
        )

        for idx, p in enumerate(players):
            p_name = p.get("name", f"Spieler {idx+1}")
            p_stats = p.get("stats", {}) or (
                stats_list[idx] if idx < len(stats_list) else {}
            )

            ppd = p_stats.get("ppd", 0)
            avg_3dart = round(ppd * 3, 2) if ppd else 0.0

            f9_ppd = p_stats.get("first9Ppd", 0)
            first9_avg = round(f9_ppd * 3, 2) if f9_ppd else 0.0

            cursor.execute(
                """
                INSERT OR REPLACE INTO match_stats 
                (match_id, player_name, legs_won, sets_won, avg_3dart, first9_avg, checkout_pct, high_checkout, s100, s140, s180)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    match_id,
                    p_name,
                    p.get("legs", 0),
                    p.get("sets", 0),
                    avg_3dart,
                    first9_avg,
                    float(p_stats.get("checkoutPercent", 0)),
                    int(p_stats.get("highCheckout", 0)),
                    int(p_stats.get("s100", 0)),
                    int(p_stats.get("s140", 0)),
                    int(p_stats.get("s180", 0)),
                ),
            )
        conn.commit()


def get_league_table() -> pd.DataFrame:
    """Berechnet die Ligatabelle inkl. 3-Punkte-Regel, Leg-Diff & direktem Vergleich."""
    query = """
        WITH player_stats AS (
            SELECT 
                ms.player_name as "Spieler",
                COUNT(ms.match_id) as "Spiele",
                SUM(CASE WHEN m.winner = ms.player_name THEN 1 ELSE 0 END) as "Siege",
                SUM(CASE WHEN m.winner != ms.player_name THEN 1 ELSE 0 END) as "Niederlagen",
                SUM(CASE WHEN m.winner = ms.player_name THEN 3 ELSE 0 END) as "Punkte",
                SUM(ms.legs_won) as "Legs_Plus",
                SUM(CASE WHEN m.player1 = ms.player_name THEN m.p2_legs ELSE m.p1_legs END) as "Legs_Minus",
                ROUND(AVG(ms.avg_3dart), 2) as "Ø Average",
                SUM(ms.s180) as "180er",
                MAX(ms.high_checkout) as "High Checkout"
            FROM match_stats ms
            JOIN matches m ON ms.match_id = m.match_id
            GROUP BY ms.player_name
        ),
        direct_matches AS (
            SELECT 
                m.winner as player,
                CASE WHEN m.winner = m.player1 THEN m.player2 ELSE m.player1 END as opponent,
                COUNT(*) as direct_wins
            FROM matches m
            GROUP BY m.winner, opponent
        )
        SELECT 
            ps."Spieler",
            ps."Spiele",
            ps."Siege",
            ps."Niederlagen",
            ps."Punkte",
            (ps."Legs_Plus" || ':' || ps."Legs_Minus") as "Legs (P:M)",
            (ps."Legs_Plus" - ps."Legs_Minus") as "Leg-Diff",
            ps."Legs_Plus" as "Legs Gewonnen",
            ps."Ø Average",
            ps."180er",
            ps."High Checkout"
        FROM player_stats ps
        LEFT JOIN direct_matches dm ON dm.player = ps."Spieler"
        GROUP BY ps."Spieler"
        ORDER BY 
            ps."Punkte" DESC, 
            "Leg-Diff" DESC, 
            ps."Legs_Plus" DESC, 
            SUM(COALESCE(dm.direct_wins, 0)) DESC,
            ps."Ø Average" DESC
    """
    with sqlite3.connect(DB_PATH) as conn:
        return pd.read_sql_query(query, conn)


# --- STREAMLIT BENUTZEROBERFLÄCHE ---
init_db()

st.set_page_config(
    page_title="Autodarts Liga", page_icon="🎯", layout="wide"
)

st.title("🎯 Autodarts Liga-Dashboard")

# Seitenleiste zum Importieren
with st.sidebar:
    st.header("Match Importieren")
    match_input = st.text_input(
        "Autodarts Match-Link oder ID:",
        placeholder="https://play.autodarts.io/...",
    )

    if st.button("Spiel Speichern", type="primary"):
        if match_input:
            try:
                m_id = extract_match_id(match_input)
                res = requests.get(
                    f"https://api.autodarts.io/ms/v1/matches/{m_id}",
                    headers={
                        "User-Agent": (
                            "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
                        )
                    },
                )
                if res.status_code == 200:
                    save_match_to_db(res.json())
                    st.success("✓ Spiel erfolgreich eingetragen!")
                    st.rerun()
                else:
                    st.error(
                        "Match konnte nicht von Autodarts abgerufen werden."
                    )
            except Exception as e:
                st.error(f"Fehler: {e}")
        else:
            st.warning("Bitte einen Link oder eine ID eingeben.")

# Hauptbereich mit Tabellen und Highlights
st.subheader("📊 Aktuelle Ligatabelle")
df = get_league_table()

if not df.empty:
    st.dataframe(df, use_container_width=True, hide_index=True)

    st.markdown("---")
    st.subheader("⭐ Liga-Highlights")
    col1, col2, col3 = st.columns(3)

    best_avg_row = df.loc[df["Ø Average"].idxmax()]
    most_180s_row = df.loc[df["180er"].idxmax()]
    high_co_row = df.loc[df["High Checkout"].idxmax()]

    col1.metric(
        "Höchster Turnier-Average",
        f"{best_avg_row['Ø Average']}",
        best_avg_row["Spieler"],
    )
    col2.metric(
        "Meiste 180er",
        f"{most_180s_row['180er']}x",
        most_180s_row["Spieler"],
    )
    col3.metric(
        "Höchstes Checkout",
        f"{high_co_row['High Checkout']}",
        high_co_row["Spieler"],
    )
else:
    st.info(
        "Noch keine Spiele in der Datenbank vorhanden. Trage links in der Seitenleiste ein Match ein!"
    )
