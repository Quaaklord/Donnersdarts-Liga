import json
import sqlite3
import pandas as pd
import streamlit as st

# --- DATENBANK LOGIK ---
DB_PATH = "autodarts_league.db"

def init_db():
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

def save_match_to_db(match_data: dict):
    match_id = match_data.get("id")
    if not match_id:
        return  # Überspringen, falls keine ID vorhanden ist

    variant = match_data.get("variant", "501")
    mode = match_data.get("mode", "Legs")
    created_at = match_data.get("createdAt", "")

    players = match_data.get("players", [])
    p1 = players[0] if len(players) > 0 else {}
    p2 = players[1] if len(players) > 1 else {}

    p1_name = p1.get("name", "Spieler 1")
    p1_legs = p1.get("legs", p1.get("score", 0))
    
    p2_name = p2.get("name", "Spieler 2")
    p2_legs = p2.get("legs", p2.get("score", 0))

    winner = p1_name if p1_legs > p2_legs else p2_name
    stats_list = match_data.get("stats", [])

    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO matches VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (match_id, created_at, variant, mode, p1_name, p2_name, p1_legs, p2_legs, winner),
        )

        for idx, p in enumerate(players):
            p_name = p.get("name", f"Spieler {idx+1}")
            p_stats = p.get("stats", {}) or (stats_list[idx] if idx < len(stats_list) else {})

            ppd = p_stats.get("ppd", 0)
            avg_3dart = round(ppd * 3, 2) if ppd else 0.0

            f9_ppd = p_stats.get("first9Ppd", 0)
            first9_avg = round(f9_ppd * 3, 2) if f9_ppd else 0.0

            s100 = int(p_stats.get("s100", p_stats.get("scores100s", 0)))
            s140 = int(p_stats.get("s140", p_stats.get("scores140s", 0)))
            s180 = int(p_stats.get("s180", p_stats.get("scores180s", 0)))
            high_co = int(p_stats.get("highCheckout", p_stats.get("highestCheckout", 0)))
            co_pct = float(p_stats.get("checkoutPercent", 0))

            cursor.execute(
                """
                INSERT OR REPLACE INTO match_stats 
                (match_id, player_name, legs_won, sets_won, avg_3dart, first9_avg, checkout_pct, high_checkout, s100, s140, s180)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (match_id, p_name, p.get("legs", p.get("score", 0)), p.get("sets", 0), avg_3dart, first9_avg, 
                 co_pct, high_co, s100, s140, s180),
            )
        conn.commit()

def get_league_table() -> pd.DataFrame:
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

st.set_page_config(page_title="Autodarts Liga", page_icon="🎯", layout="wide")
st.title("🎯 Autodarts Liga-Dashboard")

with st.sidebar:
    st.header("📂 Match JSON Upload")
    st.markdown("Lade die exportierte Match-Datei von Autodarts hoch.")
    
    uploaded_file = st.file_uploader("Match-Daten (.json)", type=["json"])

    if uploaded_file is not None:
        try:
            match_data = json.load(uploaded_file)
            
            # Unterstützt sowohl einzelne Match-Objekte als auch Listen von Matches
            if isinstance(match_data, list):
                for m in match_data:
                    save_match_to_db(m)
                st.success(f"✓ {len(match_data)} Spiele erfolgreich eingetragen!")
            elif isinstance(match_data, dict):
                save_match_to_db(match_data)
                st.success("✓ Spiel inkl. Stats erfolgreich eingetragen!")
            
            st.rerun()
        except Exception as e:
            st.error(f"Fehler beim Verarbeiten der Datei: {e}")

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

    col1.metric("Höchster Turnier-Average", f"{best_avg_row['Ø Average']}", best_avg_row["Spieler"])
    col2.metric("Meiste 180er", f"{most_180s_row['180er']}x", most_180s_row["Spieler"])
    col3.metric("Höchstes Checkout", f"{high_co_row['High Checkout']}", high_co_row["Spieler"])
else:
    st.info("Noch keine Spiele in der Datenbank vorhanden. Lade links deine Match-JSON-Datei hoch.")
