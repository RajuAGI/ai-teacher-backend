from flask import Flask, request, jsonify
from flask_cors import CORS
import sqlite3
import hashlib
import jwt
import os
import random
import string
from datetime import datetime, timedelta, date
from functools import wraps

app = Flask(__name__)
CORS(app, origins="*")

SECRET_KEY = os.environ.get("SECRET_KEY", "teamcoin_secret_2025")
DB_PATH = "teamcoin.db"

# ===== COIN REWARDS =====
COINS = {
    "daily_login": 5,
    "vote": 2,
    "become_leader": 50,
    "refer_user": 20,
    "join_team": 10,
    "create_team": 15
}

TEAM_SIZE = 9

# ===== DB SETUP =====
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()

    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        coins REAL DEFAULT 0,
        referral_code TEXT UNIQUE,
        referred_by INTEGER,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        last_login TEXT,
        photo_url TEXT DEFAULT ''
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS teams (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        level INTEGER DEFAULT 1,
        parent_team_id INTEGER,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS team_members (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        team_id INTEGER,
        user_id INTEGER,
        joined_at TEXT DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(user_id, team_id)
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS votes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        voter_id INTEGER,
        candidate_id INTEGER,
        team_id INTEGER,
        vote_date TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(voter_id, team_id, vote_date)
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS team_leaders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        team_id INTEGER,
        leader_id INTEGER,
        leader_date TEXT,
        vote_count INTEGER DEFAULT 0,
        UNIQUE(team_id, leader_date)
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS coin_transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        from_user_id INTEGER,
        to_user_id INTEGER NOT NULL,
        amount REAL NOT NULL,
        reason TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )''')

    conn.commit()
    conn.close()

init_db()

# ===== HELPERS =====
def gen_referral():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))

def hash_password(p):
    return hashlib.sha256(p.encode()).hexdigest()

def add_coins(user_id, amount, reason, conn=None):
    close = False
    if conn is None:
        conn = get_db()
        close = True
    conn.execute("UPDATE users SET coins = coins + ? WHERE id = ?", (amount, user_id))
    conn.execute("INSERT INTO coin_transactions (from_user_id, to_user_id, amount, reason) VALUES (NULL, ?, ?, ?)",
                 (user_id, amount, reason))
    if close:
        conn.commit()
        conn.close()

def make_token(user_id):
    payload = {"user_id": user_id, "exp": datetime.utcnow() + timedelta(days=7)}
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")

def auth_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get("Authorization", "").replace("Bearer ", "")
        if not token:
            return jsonify({"error": "Token required"}), 401
        try:
            data = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
            request.user_id = data["user_id"]
        except:
            return jsonify({"error": "Invalid token"}), 401
        return f(*args, **kwargs)
    return decorated

def update_leaders(team_id, vote_date, conn):
    rows = conn.execute('''
        SELECT candidate_id, COUNT(*) as cnt FROM votes
        WHERE team_id = ? AND vote_date = ?
        GROUP BY candidate_id ORDER BY cnt DESC LIMIT 1
    ''', (team_id, vote_date)).fetchone()

    if rows:
        leader_id = rows["candidate_id"]
        vote_count = rows["cnt"]
        existing = conn.execute(
            "SELECT * FROM team_leaders WHERE team_id = ? AND leader_date = ?",
            (team_id, vote_date)).fetchone()

        if existing:
            old_leader = existing["leader_id"]
            conn.execute(
                "UPDATE team_leaders SET leader_id = ?, vote_count = ? WHERE team_id = ? AND leader_date = ?",
                (leader_id, vote_count, team_id, vote_date))
        else:
            old_leader = None
            conn.execute(
                "INSERT INTO team_leaders (team_id, leader_id, leader_date, vote_count) VALUES (?, ?, ?, ?)",
                (team_id, leader_id, vote_date, vote_count))

        # Leader बनने पर coins दो (नया leader ही हो)
        if old_leader != leader_id:
            add_coins(leader_id, COINS["become_leader"], "Leader बनने पर", conn)

        conn.commit()
        check_upper_team(team_id, vote_date, conn)

def check_upper_team(team_id, vote_date, conn):
    """अगर 9 teams के leaders बन गए तो upper level team बनाओ"""
    team = conn.execute("SELECT * FROM teams WHERE id = ?", (team_id,)).fetchone()
    if not team: return

    parent_id = team["parent_team_id"]
    level = team["level"]

    if parent_id:
        # Parent team already exists
        update_leaders(parent_id, vote_date, conn)
        return

    # इस level की सभी teams जिनका leader आज बना
    sibling_leaders = conn.execute('''
        SELECT tl.leader_id, t.id as team_id FROM team_leaders tl
        JOIN teams t ON t.id = tl.team_id
        WHERE t.level = ? AND tl.leader_date = ? AND t.parent_team_id IS NULL
    ''', (level, vote_date)).fetchall()

    if len(sibling_leaders) >= TEAM_SIZE:
        # Check if upper team already formed
        first_team_ids = [r["team_id"] for r in sibling_leaders[:TEAM_SIZE]]
        existing_upper = conn.execute(
            "SELECT * FROM teams WHERE level = ? AND created_at >= date('now')",
            (level + 1,)).fetchone()

        if not existing_upper:
            # New upper team बनाओ
            conn.execute("INSERT INTO teams (name, level) VALUES (?, ?)",
                        (f"Level {level+1} Team", level + 1))
            upper_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

            for r in sibling_leaders[:TEAM_SIZE]:
                conn.execute(
                    "UPDATE teams SET parent_team_id = ? WHERE id = ?",
                    (upper_id, r["team_id"]))
                conn.execute(
                    "INSERT OR IGNORE INTO team_members (team_id, user_id) VALUES (?, ?)",
                    (upper_id, r["leader_id"]))

            conn.commit()

# ===== ROUTES =====
@app.route("/")
def home():
    return jsonify({"status": "TeamCoin Backend Running!"})

@app.route("/register", methods=["POST"])
def register():
    try:
        d = request.json
        username = d.get("username", "").strip()
        email = d.get("email", "").strip().lower()
        password = d.get("password", "")
        ref_code = d.get("referral_code", "").strip().upper()

        if not username or not email or not password:
            return jsonify({"error": "सभी fields भरें"}), 400
        if len(password) < 6:
            return jsonify({"error": "Password कम से कम 6 characters का हो"}), 400

        conn = get_db()

        if conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone():
            conn.close()
            return jsonify({"error": "Email पहले से registered है"}), 400
        if conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone():
            conn.close()
            return jsonify({"error": "Username पहले से लिया हुआ है"}), 400

        referrer_id = None
        if ref_code:
            ref_user = conn.execute("SELECT id FROM users WHERE referral_code = ?", (ref_code,)).fetchone()
            if ref_user:
                referrer_id = ref_user["id"]

        new_ref = gen_referral()
        conn.execute(
            "INSERT INTO users (username, email, password, referral_code, referred_by, coins) VALUES (?, ?, ?, ?, ?, ?)",
            (username, email, hash_password(password), new_ref, referrer_id, 10))
        new_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        conn.execute(
            "INSERT INTO coin_transactions (from_user_id, to_user_id, amount, reason) VALUES (NULL, ?, 10, 'Registration Bonus')",
            (new_id,))

        if referrer_id:
            add_coins(referrer_id, COINS["refer_user"], f"@{username} को refer करने पर", conn)

        conn.commit()
        conn.close()

        token = make_token(new_id)
        return jsonify({"token": token, "message": "Registration सफल! 10 TeamCoins मिले!", "referral_code": new_ref})

    except Exception as e:
        print("Register ERROR:", e)
        return jsonify({"error": str(e)}), 500

@app.route("/login", methods=["POST"])
def login():
    try:
        d = request.json
        email = d.get("email", "").strip().lower()
        password = d.get("password", "")

        conn = get_db()
        user = conn.execute(
            "SELECT * FROM users WHERE email = ? AND password = ?",
            (email, hash_password(password))).fetchone()

        if not user:
            conn.close()
            return jsonify({"error": "Email या Password गलत है"}), 401

        user_id = user["id"]
        today = str(date.today())
        bonus = 0
        message = "Login सफल!"

        # Daily login bonus
        if user["last_login"] != today:
            add_coins(user_id, COINS["daily_login"], "Daily Login Bonus", conn)
            bonus = COINS["daily_login"]
            message = f"Welcome back! +{bonus} Daily Login Coins मिले!"

        conn.execute("UPDATE users SET last_login = ? WHERE id = ?", (today, user_id))
        conn.commit()
        conn.close()

        token = make_token(user_id)
        return jsonify({"token": token, "message": message, "daily_bonus": bonus})

    except Exception as e:
        print("Login ERROR:", e)
        return jsonify({"error": str(e)}), 500

@app.route("/me", methods=["GET"])
@auth_required
def get_me():
    try:
        conn = get_db()
        user = conn.execute(
            "SELECT id, username, email, coins, referral_code, created_at, last_login FROM users WHERE id = ?",
            (request.user_id,)).fetchone()

        # My team info
        my_team = conn.execute('''
            SELECT t.id, t.name, t.level, COUNT(tm2.user_id) as member_count
            FROM team_members tm
            JOIN teams t ON t.id = tm.team_id
            LEFT JOIN team_members tm2 ON tm2.team_id = t.id
            WHERE tm.user_id = ? AND t.level = 1
            GROUP BY t.id LIMIT 1
        ''', (request.user_id,)).fetchone()

        # Today's leader in my team
        today = str(date.today())
        today_leader = None
        if my_team:
            leader = conn.execute('''
                SELECT u.username, tl.vote_count FROM team_leaders tl
                JOIN users u ON u.id = tl.leader_id
                WHERE tl.team_id = ? AND tl.leader_date = ?
            ''', (my_team["id"], today)).fetchone()
            if leader:
                today_leader = dict(leader)

        # My vote today
        my_vote = None
        if my_team:
            vote = conn.execute(
                "SELECT candidate_id FROM votes WHERE voter_id = ? AND team_id = ? AND vote_date = ?",
                (request.user_id, my_team["id"], today)).fetchone()
            if vote:
                voted_user = conn.execute("SELECT username FROM users WHERE id = ?", (vote["candidate_id"],)).fetchone()
                my_vote = voted_user["username"] if voted_user else None

        # Recent transactions
        txns = conn.execute('''
            SELECT ct.amount, ct.reason, ct.created_at,
                   u.username as from_user
            FROM coin_transactions ct
            LEFT JOIN users u ON u.id = ct.from_user_id
            WHERE ct.to_user_id = ?
            ORDER BY ct.created_at DESC LIMIT 5
        ''', (request.user_id,)).fetchall()

        conn.close()
        return jsonify({
            "user": dict(user),
            "team": dict(my_team) if my_team else None,
            "today_leader": today_leader,
            "my_vote": my_vote,
            "recent_transactions": [dict(t) for t in txns]
        })

    except Exception as e:
        print("Me ERROR:", e)
        return jsonify({"error": str(e)}), 500

@app.route("/team/create", methods=["POST"])
@auth_required
def create_team():
    try:
        d = request.json
        name = d.get("name", "").strip() or f"Team #{random.randint(1000,9999)}"
        conn = get_db()

        # Already in a team?
        existing = conn.execute(
            "SELECT tm.id FROM team_members tm JOIN teams t ON t.id = tm.team_id WHERE tm.user_id = ? AND t.level = 1",
            (request.user_id,)).fetchone()
        if existing:
            conn.close()
            return jsonify({"error": "आप पहले से एक team में हैं"}), 400

        conn.execute("INSERT INTO teams (name, level) VALUES (?, 1)", (name,))
        team_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.execute("INSERT INTO team_members (team_id, user_id) VALUES (?, ?)", (team_id, request.user_id))
        add_coins(request.user_id, COINS["create_team"], "Team बनाने पर", conn)
        conn.commit()
        conn.close()

        return jsonify({
            "team_id": team_id,
            "message": f"Team '{name}' बन गई! +{COINS['create_team']} TeamCoins मिले!",
            "invite_code": str(team_id)
        })

    except Exception as e:
        print("Create team ERROR:", e)
        return jsonify({"error": str(e)}), 500

@app.route("/team/join", methods=["POST"])
@auth_required
def join_team():
    try:
        d = request.json
        team_id = d.get("team_id")
        conn = get_db()

        # Already in team?
        existing = conn.execute(
            "SELECT tm.id FROM team_members tm JOIN teams t ON t.id = tm.team_id WHERE tm.user_id = ? AND t.level = 1",
            (request.user_id,)).fetchone()
        if existing:
            conn.close()
            return jsonify({"error": "आप पहले से एक team में हैं"}), 400

        team = conn.execute("SELECT * FROM teams WHERE id = ? AND level = 1", (team_id,)).fetchone()
        if not team:
            conn.close()
            return jsonify({"error": "Team नहीं मिली"}), 404

        count = conn.execute("SELECT COUNT(*) as c FROM team_members WHERE team_id = ?", (team_id,)).fetchone()["c"]
        if count >= TEAM_SIZE:
            conn.close()
            return jsonify({"error": f"Team भर गई है! (maximum {TEAM_SIZE} members)"}), 400

        conn.execute("INSERT INTO team_members (team_id, user_id) VALUES (?, ?)", (team_id, request.user_id))
        add_coins(request.user_id, COINS["join_team"], "Team join करने पर", conn)
        conn.commit()
        conn.close()

        return jsonify({"message": f"Team join कर ली! +{COINS['join_team']} TeamCoins मिले!"})

    except Exception as e:
        print("Join team ERROR:", e)
        return jsonify({"error": str(e)}), 500

@app.route("/team/info/<int:team_id>", methods=["GET"])
@auth_required
def team_info(team_id):
    try:
        conn = get_db()
        team = conn.execute("SELECT * FROM teams WHERE id = ?", (team_id,)).fetchone()
        if not team:
            conn.close()
            return jsonify({"error": "Team नहीं मिली"}), 404

        members = conn.execute('''
            SELECT u.id, u.username, u.coins, u.photo_url
            FROM team_members tm JOIN users u ON u.id = tm.user_id
            WHERE tm.team_id = ?
        ''', (team_id,)).fetchall()

        today = str(date.today())
        leader = conn.execute('''
            SELECT u.id, u.username, tl.vote_count FROM team_leaders tl
            JOIN users u ON u.id = tl.leader_id
            WHERE tl.team_id = ? AND tl.leader_date = ?
        ''', (team_id, today)).fetchone()

        votes_today = conn.execute(
            "SELECT candidate_id, COUNT(*) as cnt FROM votes WHERE team_id = ? AND vote_date = ? GROUP BY candidate_id",
            (team_id, today)).fetchall()

        vote_map = {v["candidate_id"]: v["cnt"] for v in votes_today}

        conn.close()
        return jsonify({
            "team": dict(team),
            "members": [dict(m) for m in members],
            "member_count": len(members),
            "spots_left": TEAM_SIZE - len(members),
            "today_leader": dict(leader) if leader else None,
            "vote_counts": vote_map
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/team/vote", methods=["POST"])
@auth_required
def vote():
    try:
        d = request.json
        candidate_id = d.get("candidate_id")
        conn = get_db()

        # My team
        my_team = conn.execute('''
            SELECT t.id FROM team_members tm JOIN teams t ON t.id = tm.team_id
            WHERE tm.user_id = ? AND t.level = 1
        ''', (request.user_id,)).fetchone()

        if not my_team:
            conn.close()
            return jsonify({"error": "पहले कोई team join करें"}), 400

        team_id = my_team["id"]
        today = str(date.today())

        # Candidate same team में है?
        in_team = conn.execute(
            "SELECT id FROM team_members WHERE team_id = ? AND user_id = ?",
            (team_id, candidate_id)).fetchone()
        if not in_team:
            conn.close()
            return jsonify({"error": "यह user आपकी team में नहीं है"}), 400

        # खुद को vote नहीं दे सकते
        if candidate_id == request.user_id:
            conn.close()
            return jsonify({"error": "खुद को vote नहीं दे सकते"}), 400

        # Already voted today?
        existing = conn.execute(
            "SELECT id FROM votes WHERE voter_id = ? AND team_id = ? AND vote_date = ?",
            (request.user_id, team_id, today)).fetchone()

        if existing:
            # Update vote
            conn.execute(
                "UPDATE votes SET candidate_id = ? WHERE voter_id = ? AND team_id = ? AND vote_date = ?",
                (candidate_id, request.user_id, team_id, today))
            msg = "Vote update हो गया!"
        else:
            conn.execute(
                "INSERT INTO votes (voter_id, candidate_id, team_id, vote_date) VALUES (?, ?, ?, ?)",
                (request.user_id, candidate_id, team_id, today))
            add_coins(request.user_id, COINS["vote"], "Vote देने पर", conn)
            msg = f"Vote दे दिया! +{COINS['vote']} TeamCoins मिले!"

        conn.commit()
        update_leaders(team_id, today, conn)
        conn.close()

        candidate = get_db().execute("SELECT username FROM users WHERE id = ?", (candidate_id,)).fetchone()
        return jsonify({"message": msg, "voted_for": candidate["username"] if candidate else ""})

    except Exception as e:
        print("Vote ERROR:", e)
        return jsonify({"error": str(e)}), 500

@app.route("/coins/transfer", methods=["POST"])
@auth_required
def transfer_coins():
    try:
        d = request.json
        to_username = d.get("to_username", "").strip()
        amount = float(d.get("amount", 0))

        if amount <= 0:
            return jsonify({"error": "Amount 0 से ज़्यादा होना चाहिए"}), 400

        conn = get_db()
        sender = conn.execute("SELECT * FROM users WHERE id = ?", (request.user_id,)).fetchone()

        if sender["coins"] < amount:
            conn.close()
            return jsonify({"error": f"आपके पास सिर्फ {sender['coins']} TeamCoins हैं"}), 400

        receiver = conn.execute("SELECT * FROM users WHERE username = ?", (to_username,)).fetchone()
        if not receiver:
            conn.close()
            return jsonify({"error": "User नहीं मिला"}), 404

        if receiver["id"] == request.user_id:
            conn.close()
            return jsonify({"error": "खुद को transfer नहीं कर सकते"}), 400

        conn.execute("UPDATE users SET coins = coins - ? WHERE id = ?", (amount, request.user_id))
        conn.execute("UPDATE users SET coins = coins + ? WHERE id = ?", (amount, receiver["id"]))
        conn.execute(
            "INSERT INTO coin_transactions (from_user_id, to_user_id, amount, reason) VALUES (?, ?, ?, ?)",
            (request.user_id, receiver["id"], amount, f"@{sender['username']} से transfer"))
        conn.commit()
        conn.close()

        return jsonify({"message": f"@{to_username} को {amount} TeamCoins transfer हो गए!"})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/leaderboard", methods=["GET"])
def leaderboard():
    try:
        conn = get_db()
        today = str(date.today())

        # Top coin holders
        top_coins = conn.execute('''
            SELECT id, username, coins, photo_url FROM users
            ORDER BY coins DESC LIMIT 10
        ''').fetchall()

        # Top level leaders today
        top_leaders = conn.execute('''
            SELECT u.id, u.username, u.coins, u.photo_url,
                   t.level, tl.vote_count
            FROM team_leaders tl
            JOIN users u ON u.id = tl.leader_id
            JOIN teams t ON t.id = tl.team_id
            WHERE tl.leader_date = ?
            ORDER BY t.level DESC, tl.vote_count DESC LIMIT 10
        ''', (today,)).fetchall()

        # Highest level today
        max_level = conn.execute(
            "SELECT MAX(level) as ml FROM teams").fetchone()["ml"] or 1

        # Top leader at highest level
        top_leader = conn.execute('''
            SELECT u.id, u.username, u.photo_url, t.level, tl.vote_count
            FROM team_leaders tl
            JOIN users u ON u.id = tl.leader_id
            JOIN teams t ON t.id = tl.team_id
            WHERE tl.leader_date = ? AND t.level = ?
            ORDER BY tl.vote_count DESC LIMIT 1
        ''', (today, max_level)).fetchone()

        conn.close()
        return jsonify({
            "top_coin_holders": [dict(u) for u in top_coins],
            "top_leaders": [dict(l) for l in top_leaders],
            "top_leader": dict(top_leader) if top_leader else None,
            "max_level": max_level,
            "today": today
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/teams/open", methods=["GET"])
@auth_required
def open_teams():
    try:
        conn = get_db()
        teams = conn.execute('''
            SELECT t.id, t.name, t.created_at,
                   COUNT(tm.user_id) as member_count
            FROM teams t
            LEFT JOIN team_members tm ON tm.team_id = t.id
            WHERE t.level = 1
            GROUP BY t.id
            HAVING member_count < ?
            ORDER BY member_count DESC LIMIT 20
        ''', (TEAM_SIZE,)).fetchall()
        conn.close()
        return jsonify({"teams": [dict(t) for t in teams]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/stats", methods=["GET"])
def stats():
    try:
        conn = get_db()
        total_users = conn.execute("SELECT COUNT(*) as c FROM users").fetchone()["c"]
        total_teams = conn.execute("SELECT COUNT(*) as c FROM teams").fetchone()["c"]
        total_coins = conn.execute("SELECT SUM(coins) as s FROM users").fetchone()["s"] or 0
        max_level = conn.execute("SELECT MAX(level) as m FROM teams").fetchone()["m"] or 1
        conn.close()
        return jsonify({
            "total_users": total_users,
            "total_teams": total_teams,
            "total_coins_distributed": round(total_coins, 2),
            "max_level": max_level
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(debug=True)
