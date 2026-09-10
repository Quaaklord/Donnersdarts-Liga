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

def get_existing_players():
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT player_name FROM match_stats")
        rows = cursor.fetchall()
        return [r[0] for r in rows] if rows else ["the unfroggettable", "elkiki"]

# --- STREAMLIT BENUTZEROBERFLÄCHE ---
init_db()

st.set_page_config(page_title="Autodarts Liga", page_icon="🎯", layout="wide")
st.title("🎯 Autodarts Liga-Dashboard")

with st.sidebar:
    st.header("✍️ Match manuell eintragen")
    st.markdown("Bypass für das JSON-Chaos: Einfach schnell eintragen.")
    
    known_players = get_existing_players()
    
    with st.form("manual_match_form"):
        col_p1, col_p2 = st.columns(2)
        with col_p1:
            p1_name = st.text_input("Spieler 1", value="the unfroggettable")
            p1_legs = st.number_input("Legs P1", min_value=0, max_value=20, value=3)
            p1_avg = st.number_input("Average P1", min_value=0.0, max_value=180.0, value=50.0, step=0.1)
            p1_co = st.number_input("High CO P1", min_value=0, max_value=170, value=40)
            p1_180 = st.number_input("180er P1", min_value=0, max_value=10, value=0)
            
        with col_p2:
            p2_name = st.text_input("Spieler 2", value="elkiki")
            p2_legs = st.number_input("Legs P2", min_value=0, max_value=20, value=1)
            p2_avg = st.number_input("Average P2", min_value=0.0, max_value=180.0, value=45.0, step=0.1)
            p2_co = st.number_input("High CO P2", min_value=0, max_value=170, value=0)
            p2_180 = st.number_input("180er P2", min_value=0, max_value=10, value=0)

        submitted = st.form_submit_button("Match speichern")
        
        if submitted:
            if p1_name.strip() == p2_name.strip():
                st.error("Spieler müssen unterschiedlich sein!")
            else:
                match_id = f"manual_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}"
                winner = p1_name if p1_legs > p2_legs else p2_name
                created_at = pd.Timestamp.now().isoformat()
                
                with sqlite3.connect(DB_PATH) as conn:
                    cursor = conn.cursor()
                    # Match speichern
                    cursor.execute(
                        "INSERT OR REPLACE INTO matches VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (match_id, created_at, "501", "Legs", p1_name, p2_name, p1_legs, p2_legs, winner),
                    )
                    # Stats P1
                    cursor.execute(
                        """
                        INSERT OR REPLACE INTO match_stats 
                        (match_id, player_name, legs_won, sets_won, avg_3dart, first9_avg, checkout_pct, high_checkout, s100, s140, s180)
                        VALUES (?, ?, ?, 0, ?, 0, 0, ?, 0, 0, ?)
                        """,
                        (match_id, p1_name, p1_legs, p1_avg, p1_co, p1_180),
                    )
                    # Stats P2
                    cursor.execute(
                        """
                        INSERT OR REPLACE INTO match_stats 
                        (match_id, player_name, legs_won, sets_won, avg_3dart, first9_avg, checkout_pct, high_checkout, s100, s140, s180)
                        VALUES (?, ?, ?, 0, ?, 0, 0, ?, 0, 0, ?)
                        """,
                        (match_id, p2_name, p2_legs, p2_avg, p2_co, p2_180),
                    )
                    conn.commit()
                st.success("✓ Match erfolgreich gespeichert!")
                st.rerun()

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
    st.info("Noch keine Spiele in der Datenbank vorhanden. Trage links dein erstes Match ein.")
