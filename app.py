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

# --- STREAMLIT BENUTZEROBERFLÄCHE ---
init_db()

st.set_page_config(page_title="Autodarts Liga", page_icon="🎯", layout="wide")
st.title("🎯 Autodarts Liga-Dashboard")

# Session State für Leg-by-Leg Eingabe initialisieren
if "match_legs" not in st.session_state:
    st.session_state.match_legs = []
if "p1_name" not in st.session_state:
    st.session_state.p1_name = "Spieler 1"
if "p2_name" not in st.session_state:
    st.session_state.p2_name = "Spieler 2"

with st.sidebar:
    st.header("🎯 Match Leg für Leg erfassen")
    
    st.session_state.p1_name = st.text_input("Spieler 1", value=st.session_state.p1_name)
    st.session_state.p2_name = st.text_input("Spieler 2", value=st.session_state.p2_name)
    
    st.markdown("---")
    st.subheader("Neues Leg hinzufügen")
    
    with st.form("leg_form", clear_on_submit=True):
        leg_winner = st.selectbox("Wer hat das Leg gewonnen?", [st.session_state.p1_name, st.session_state.p2_name])
        
        col_d1, col_d2 = st.columns(2)
        with col_d1:
            darts_p1 = st.number_input(f"Darts {st.session_state.p1_name}", min_value=1, max_value=200, value=18)
        with col_d2:
            darts_p2 = st.number_input(f"Darts {st.session_state.p2_name}", min_value=1, max_value=200, value=18)
            
        loser_name = st.session_state.p2_name if leg_winner == st.session_state.p1_name else st.session_state.p1_name
        loser_rest = st.number_input(f"Restpunkte Verlierer ({loser_name})", min_value=0, max_value=500, value=0)
        
        checkout_val = st.number_input("Checkout-Wert (des Gewinners)", min_value=2, max_value=170, value=40)
        
        col_180_1, col_180_2 = st.columns(2)
        with col_180_1:
            s180_p1 = st.number_input(f"180er {st.session_state.p1_name}", min_value=0, max_value=3, value=0)
        with col_180_2:
            s180_p2 = st.number_input(f"180er {st.session_state.p2_name}", min_value=0, max_value=3, value=0)

        add_leg_submitted = st.form_submit_button("Leg hinzufügen")
        
        if add_leg_submitted:
            leg_data = {
                "winner": leg_winner,
                "darts_p1": darts_p1,
                "darts_p2": darts_p2,
                "loser_rest": loser_rest,
                "checkout": checkout_val,
                "s180_p1": s180_p1,
                "s180_p2": s180_p2
            }
            st.session_state.match_legs.append(leg_data)
            st.success(f"Leg {len(st.session_state.match_legs)} hinzugefügt!")

    if st.session_state.match_legs:
        st.markdown("---")
        if st.button("🗑️ Alle Legs zurücksetzen"):
            st.session_state.match_legs = []
            st.rerun()

# Hauptbereich: Aktuelle Legs des laufenden Matches anzeigen & speichern
st.subheader("📝 Aktuelles Match (Leg-Übersicht)")

if st.session_state.match_legs:
    legs_df = pd.DataFrame(st.session_state.match_legs)
    st.dataframe(legs_df, use_container_width=True, hide_index=True)
    
    # Berechne Live-Zwischenstand
    p1_legs_won = sum(1 for l in st.session_state.match_legs if l["winner"] == st.session_state.p1_name)
    p2_legs_won = sum(1 for l in st.session_state.match_legs if l["winner"] == st.session_state.p2_name)
    
    st.info(f"Zwischenstand: **{st.session_state.p1_name} {p1_legs_won} : {p2_legs_won} {st.session_state.p2_name}**")
    
    if st.button("💾 Gesamtes Match in Datenbank speichern", type="primary"):
        # Statistiken über alle Legs aggregieren
        p1_total_darts = sum(l["darts_p1"] for l in st.session_state.match_legs)
        p2_total_darts = sum(l["darts_p2"] for l in st.session_state.match_legs)
        
        p1_total_points = 0
        p2_total_points = 0
        
        p1_high_co = 0
        p2_high_co = 0
        
        p1_180s = sum(l["s180_p1"] for l in st.session_state.match_legs)
        p2_180s = sum(l["s180_p2"] for l in st.session_state.match_legs)
        
        for l in st.session_state.match_legs:
            if l["winner"] == st.session_state.p1_name:
                p1_total_points += 501
                p2_total_points += (501 - l["loser_rest"])
                if l["checkout"] > p1_high_co:
                    p1_high_co = l["checkout"]
            else:
                p2_total_points += 501
                p1_total_points += (501 - l["loser_rest"])
                if l["checkout"] > p2_high_co:
                    p2_high_co = l["checkout"]
                    
        p1_avg = round((p1_total_points / p1_total_darts) * 3, 2) if p1_total_darts > 0 else 0.0
        p2_avg = round((p2_total_points / p2_total_darts) * 3, 2) if p2_total_darts > 0 else 0.0
        
        match_id = f"match_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}"
        created_at = pd.Timestamp.now().isoformat()
        match_winner = st.session_state.p1_name if p1_legs_won > p2_legs_won else st.session_state.p2_name
        
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT OR REPLACE INTO matches VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (match_id, created_at, "501", "Legs", st.session_state.p1_name, st.session_state.p2_name, p1_legs_won, p2_legs_won, match_winner),
            )
            cursor.execute(
                """
                INSERT OR REPLACE INTO match_stats 
                (match_id, player_name, legs_won, sets_won, avg_3dart, first9_avg, checkout_pct, high_checkout, s100, s140, s180)
                VALUES (?, ?, ?, 0, ?, 0, 0, ?, 0, 0, ?)
                """,
                (match_id, st.session_state.p1_name, p1_legs_won, p1_avg, p1_high_co, p1_180s),
            )
            cursor.execute(
                """
                INSERT OR REPLACE INTO match_stats 
                (match_id, player_name, legs_won, sets_won, avg_3dart, first9_avg, checkout_pct, high_checkout, s100, s140, s180)
                VALUES (?, ?, ?, 0, ?, 0, 0, ?, 0, 0, ?)
                """,
                (match_id, st.session_state.p2_name, p2_legs_won, p2_avg, p2_high_co, p2_180s),
            )
            conn.commit()
            
        st.success("✓ Match erfolgreich in der Ligatabelle gespeichert!")
        st.session_state.match_legs = []
        st.rerun()
else:
    st.info("Noch keine Legs für das aktuelle Match erfasst. Nutze die Sidebar, um Leg für Leg hinzuzufügen.")

st.markdown("---")
st.subheader("📊 Aktuelle Ligatabelle")

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
    st.info("Noch keine Spiele in der Datenbank vorhanden.")
