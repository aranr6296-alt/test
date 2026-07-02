# xp_database.py
# Standalone SQLite database module for the Discord bot
# Handles XP, economy, warnings, AFK, and all persistent data

import sqlite3
import json
import os

DB_FILE = "bot_data.db"


def get_conn():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def init():
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS xp_data (
            guild_id   INTEGER,
            user_id    INTEGER,
            message_xp INTEGER DEFAULT 0,
            voice_xp   INTEGER DEFAULT 0,
            PRIMARY KEY (guild_id, user_id)
        );

        CREATE TABLE IF NOT EXISTS economy (
            guild_id    INTEGER,
            user_id     INTEGER,
            wallet      INTEGER DEFAULT 0,
            bank        INTEGER DEFAULT 0,
            last_daily  REAL    DEFAULT 0,
            last_weekly REAL    DEFAULT 0,
            last_work   REAL    DEFAULT 0,
            last_beg    REAL    DEFAULT 0,
            inventory   TEXT    DEFAULT '[]',
            PRIMARY KEY (guild_id, user_id)
        );

        CREATE TABLE IF NOT EXISTS warnings (
            guild_id INTEGER,
            user_id  INTEGER,
            count    INTEGER DEFAULT 0,
            PRIMARY KEY (guild_id, user_id)
        );

        CREATE TABLE IF NOT EXISTS afk_users (
            guild_id  INTEGER,
            user_id   INTEGER,
            reason    TEXT,
            since     REAL,
            old_nick  TEXT,
            image_url TEXT,
            PRIMARY KEY (guild_id, user_id)
        );

        CREATE TABLE IF NOT EXISTS level_channels (
            guild_id   INTEGER PRIMARY KEY,
            channel_id INTEGER
        );

        CREATE TABLE IF NOT EXISTS welcome_channels (
            guild_id   INTEGER PRIMARY KEY,
            channel_id INTEGER
        );
    """)
    conn.commit()
    conn.close()
    print("[DB] bot_data.db initialised ✓")


# ── XP ────────────────────────────────────────────────────────────
def load_xp():
    data = {}
    conn = get_conn()
    for row in conn.execute("SELECT guild_id, user_id, message_xp, voice_xp FROM xp_data"):
        g = str(row["guild_id"])
        u = str(row["user_id"])
        data.setdefault(g, {})[u] = {
            "message_xp": row["message_xp"],
            "voice_xp":   row["voice_xp"],
        }
    conn.close()
    return data


def save_xp(xp_data):
    conn = get_conn()
    for gid, users in xp_data.items():
        for uid, entry in users.items():
            conn.execute(
                "INSERT INTO xp_data (guild_id, user_id, message_xp, voice_xp) VALUES (?,?,?,?) "
                "ON CONFLICT(guild_id, user_id) DO UPDATE SET "
                "message_xp=excluded.message_xp, voice_xp=excluded.voice_xp",
                (int(gid), int(uid), entry.get("message_xp", 0), entry.get("voice_xp", 0))
            )
    conn.commit()
    conn.close()


def save_xp_entry(guild_id, user_id, xp_data):
    entry = xp_data.get(str(guild_id), {}).get(str(user_id), {"message_xp": 0, "voice_xp": 0})
    conn = get_conn()
    conn.execute(
        "INSERT INTO xp_data (guild_id, user_id, message_xp, voice_xp) VALUES (?,?,?,?) "
        "ON CONFLICT(guild_id, user_id) DO UPDATE SET "
        "message_xp=excluded.message_xp, voice_xp=excluded.voice_xp",
        (int(guild_id), int(user_id), entry.get("message_xp", 0), entry.get("voice_xp", 0))
    )
    conn.commit()
    conn.close()


def get_xp_rank(guild_id, user_id, xp_data):
    g = str(guild_id)
    u = str(user_id)
    guild_data = xp_data.get(g, {})
    my_total = sum(guild_data.get(u, {}).values())
    rank = sum(1 for v in guild_data.values() if sum(v.values()) > my_total) + 1
    return rank, len(guild_data)


# ── Economy ───────────────────────────────────────────────────────
def load_economy():
    data = {}
    conn = get_conn()
    for row in conn.execute(
        "SELECT guild_id, user_id, wallet, bank, last_daily, last_weekly, last_work, last_beg, inventory FROM economy"
    ):
        g = str(row["guild_id"])
        u = str(row["user_id"])
        data.setdefault(g, {})[u] = {
            "wallet":      row["wallet"],
            "bank":        row["bank"],
            "last_daily":  row["last_daily"],
            "last_weekly": row["last_weekly"],
            "last_work":   row["last_work"],
            "last_beg":    row["last_beg"],
            "inventory":   json.loads(row["inventory"] or "[]"),
        }
    conn.close()
    return data


def save_economy(economy):
    conn = get_conn()
    for gid, users in economy.items():
        for uid, e in users.items():
            conn.execute(
                "INSERT INTO economy "
                "(guild_id, user_id, wallet, bank, last_daily, last_weekly, last_work, last_beg, inventory) "
                "VALUES (?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(guild_id, user_id) DO UPDATE SET "
                "wallet=excluded.wallet, bank=excluded.bank, "
                "last_daily=excluded.last_daily, last_weekly=excluded.last_weekly, "
                "last_work=excluded.last_work, last_beg=excluded.last_beg, "
                "inventory=excluded.inventory",
                (int(gid), int(uid), e["wallet"], e["bank"],
                 e["last_daily"], e["last_weekly"], e["last_work"], e["last_beg"],
                 json.dumps(e["inventory"]))
            )
    conn.commit()
    conn.close()


# ── Warnings ──────────────────────────────────────────────────────
def load_warnings():
    data = {}
    conn = get_conn()
    for row in conn.execute("SELECT guild_id, user_id, count FROM warnings"):
        g = str(row["guild_id"])
        u = str(row["user_id"])
        data.setdefault(g, {})[u] = row["count"]
    conn.close()
    return data


def save_warnings(warnings_data):
    conn = get_conn()
    for gid, users in warnings_data.items():
        for uid, count in users.items():
            conn.execute(
                "INSERT INTO warnings (guild_id, user_id, count) VALUES (?,?,?) "
                "ON CONFLICT(guild_id, user_id) DO UPDATE SET count=excluded.count",
                (int(gid), int(uid), count)
            )
    conn.commit()
    conn.close()


# ── Level channels ────────────────────────────────────────────────
def load_level_channels():
    data = {}
    conn = get_conn()
    for row in conn.execute("SELECT guild_id, channel_id FROM level_channels"):
        data[str(row["guild_id"])] = row["channel_id"]
    conn.close()
    return data


def save_level_channel(guild_id, channel_id):
    conn = get_conn()
    conn.execute(
        "INSERT INTO level_channels (guild_id, channel_id) VALUES (?,?) "
        "ON CONFLICT(guild_id) DO UPDATE SET channel_id=excluded.channel_id",
        (int(guild_id), int(channel_id))
    )
    conn.commit()
    conn.close()


def remove_level_channel(guild_id):
    conn = get_conn()
    conn.execute("DELETE FROM level_channels WHERE guild_id=?", (int(guild_id),))
    conn.commit()
    conn.close()


if __name__ == "__main__":
    init()
    print("Database ready at", DB_FILE)
