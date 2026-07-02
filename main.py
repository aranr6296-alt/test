import discord
from discord.ext import commands, tasks
import logging
import json
import os
import random
import time
import math
import datetime
import re
import asyncio
import sqlite3
import aiohttp
import concurrent.futures as _cf
import html as html_module
from dotenv import load_dotenv

load_dotenv()
token = os.getenv('DISCORD_TOKEN')

# Fallback: load from token.txt if env var not set
if not token:
    try:
        with open('token.txt', 'r') as _f:
            token = _f.read().strip()
        print("Token loaded from token.txt")
    except FileNotFoundError:
        pass

handler = logging.FileHandler(filename='discord.log', encoding='utf-8', mode='w')
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.voice_states = True
intents.presences = True  # REQUIRED FOR THE COOL STATUS AFK FEATURE

bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)
bot_start_time = time.time()

LEVEL_ICONS = {range(1,5):"🌱", range(5,10):"⚡", range(10,20):"🔥", range(20,30):"💎", range(30,50):"👑"}
def level_icon(lvl):
    return next((v for k,v in LEVEL_ICONS.items() if lvl in k), "🌟")


# 🌍 BILINGUAL LANGUAGE SYSTEM
LANG = {
    "en": {
        "welcome": "Welcome to the server! | بەخێربێیت بۆ سێرڤەر!",
        "help": "Here are my commands | ئەمەش فەرمانەکانم",
        "language_set": "Language changed to English 🇺🇸 | زمان گۆڕدرا بۆ ئینگلیزی",
        "ping": "Bot latency | خێرایی بۆت",
        "success": "Success | سەرکەوتوو",
        "error": "Error | هەڵە"
    },
    "ku": {
        "welcome": "بەخێربێیت بۆ سێرڤەر! | Welcome to the server!",
        "help": "ئەمەش فەرمانەکانم | Here are my commands",
        "language_set": "زمان گۆڕدرا بۆ کوردی 🇹🇯 | Language changed to Kurdish",
        "ping": "خێرایی بۆت | Bot latency",
        "success": "سەرکەوتوو | Success",
        "error": "هەڵە | Error"
    }
}

user_langs = {}

def tr(user_id, key):
    lang = user_langs.get(user_id, "en")
    return LANG.get(lang, LANG["en"]).get(key, key)

guild_langs = {}  # {guild_id_str: "en" | "ku" | "both"}

def _strip_lang(text: str, lang: str) -> str:
    """Filter 'Kurdish | English' bilingual text to one language.
    lang='ku' → Kurdish part, 'en' → English part, 'both' → original."""
    if not text or lang == "both" or "|" not in text:
        return text
    parts = text.split("|", 1)
    return parts[0].strip() if lang == "ku" else parts[1].strip()

def get_guild_lang(guild_id) -> str:
    """Return the server's current language preference (default: 'both')."""
    return guild_langs.get(str(guild_id), "both")

def load_guild_langs():
    global guild_langs
    guild_langs = {}
    conn = get_db()
    for row in conn.execute("SELECT guild_id, lang FROM guild_lang_settings"):
        guild_langs[str(row["guild_id"])] = row["lang"]
    conn.close()



# --- SQLITE DATABASE SETUP ---
DB_FILE = "bot_data.db"

def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    c.executescript("""
        CREATE TABLE IF NOT EXISTS xp_data (
            guild_id INTEGER,
            user_id INTEGER,
            message_xp INTEGER DEFAULT 0,
            voice_xp INTEGER DEFAULT 0,
            PRIMARY KEY (guild_id, user_id)
        );
        CREATE TABLE IF NOT EXISTS economy (
            guild_id INTEGER,
            user_id INTEGER,
            wallet INTEGER DEFAULT 0,
            bank INTEGER DEFAULT 0,
            last_daily REAL DEFAULT 0,
            last_weekly REAL DEFAULT 0,
            last_work REAL DEFAULT 0,
            last_beg REAL DEFAULT 0,
            inventory TEXT DEFAULT '[]',
            PRIMARY KEY (guild_id, user_id)
        );
        CREATE TABLE IF NOT EXISTS warnings (
            guild_id INTEGER,
            user_id INTEGER,
            count INTEGER DEFAULT 0,
            PRIMARY KEY (guild_id, user_id)
        );
        CREATE TABLE IF NOT EXISTS afk_users (
            guild_id INTEGER,
            user_id INTEGER,
            reason TEXT,
            since REAL,
            old_nick TEXT,
            image_url TEXT,
            PRIMARY KEY (guild_id, user_id)
        );
        CREATE TABLE IF NOT EXISTS level_channels (
            guild_id INTEGER PRIMARY KEY,
            channel_id INTEGER
        );
        CREATE TABLE IF NOT EXISTS lucky_leaderboard (
            guild_id INTEGER,
            user_id INTEGER,
            wins INTEGER DEFAULT 0,
            total_guesses INTEGER DEFAULT 0,
            best_guesses INTEGER DEFAULT 0,
            PRIMARY KEY (guild_id, user_id)
        );
        CREATE TABLE IF NOT EXISTS welcome_channels (
            guild_id INTEGER PRIMARY KEY,
            channel_id INTEGER
        );
        CREATE TABLE IF NOT EXISTS ticket_settings (
            guild_id INTEGER PRIMARY KEY,
            staff_role_id INTEGER,
            category_id INTEGER,
            log_channel_id INTEGER,
            panel_channel_id INTEGER
        );
        CREATE TABLE IF NOT EXISTS open_tickets (
            guild_id INTEGER,
            user_id INTEGER,
            channel_id INTEGER,
            PRIMARY KEY (guild_id, user_id)
        );
        CREATE TABLE IF NOT EXISTS open_staff_apps (
            guild_id INTEGER,
            user_id INTEGER,
            channel_id INTEGER,
            PRIMARY KEY (guild_id, user_id)
        );
        CREATE TABLE IF NOT EXISTS staff_submit_log_channels (
            guild_id INTEGER PRIMARY KEY,
            channel_id INTEGER
        );
        CREATE TABLE IF NOT EXISTS rules_settings (
            guild_id  INTEGER PRIMARY KEY,
            text_en   TEXT    DEFAULT '',
            text_ku   TEXT    DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS staff_daily_last_msg (
            guild_id   INTEGER PRIMARY KEY,
            message_id INTEGER
        );
        CREATE TABLE IF NOT EXISTS invite_channels (
            guild_id INTEGER PRIMARY KEY,
            channel_id INTEGER
        );
        CREATE TABLE IF NOT EXISTS invite_counts (
            guild_id INTEGER,
            user_id INTEGER,
            total INTEGER DEFAULT 0,
            left_count INTEGER DEFAULT 0,
            PRIMARY KEY (guild_id, user_id)
        );
        CREATE TABLE IF NOT EXISTS apply_channels (
            guild_id INTEGER PRIMARY KEY,
            channel_id INTEGER
        );
        CREATE TABLE IF NOT EXISTS apply_questions (
            guild_id  INTEGER NOT NULL,
            slot      INTEGER NOT NULL,
            question  TEXT    NOT NULL,
            PRIMARY KEY (guild_id, slot)
        );
        CREATE TABLE IF NOT EXISTS apply_lang (
            guild_id  INTEGER PRIMARY KEY,
            lang      TEXT    NOT NULL DEFAULT 'both'
        );
        CREATE TABLE IF NOT EXISTS log_channels (
            guild_id INTEGER PRIMARY KEY,
            channel_id INTEGER
        );
        CREATE TABLE IF NOT EXISTS rr_panels (
            guild_id INTEGER,
            channel_id INTEGER,
            message_id INTEGER PRIMARY KEY,
            title TEXT,
            description TEXT
        );
        CREATE TABLE IF NOT EXISTS rr_buttons (
            message_id INTEGER,
            role_id INTEGER,
            emoji TEXT,
            label TEXT,
            PRIMARY KEY (message_id, role_id)
        );
        CREATE TABLE IF NOT EXISTS selfrole_reactions (
            guild_id   INTEGER,
            message_id INTEGER,
            emoji      TEXT,
            role_id    INTEGER,
            PRIMARY KEY (message_id, emoji)
        );
        CREATE TABLE IF NOT EXISTS staff_daily_channels (
            guild_id INTEGER PRIMARY KEY,
            channel_id INTEGER
        );
        CREATE TABLE IF NOT EXISTS selfrole_panels (
            guild_id   INTEGER,
            message_id INTEGER PRIMARY KEY,
            channel_id INTEGER,
            title      TEXT
        );
        CREATE TABLE IF NOT EXISTS boost_channels (
            guild_id   INTEGER PRIMARY KEY,
            channel_id INTEGER
        );
        CREATE TABLE IF NOT EXISTS staff_done_log (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id     INTEGER,
            user_id      INTEGER,
            display_name TEXT,
            done_at      TEXT
        );
        CREATE TABLE IF NOT EXISTS staff_done_role (
            guild_id INTEGER PRIMARY KEY,
            role_id  INTEGER
        );
        CREATE TABLE IF NOT EXISTS reklam_settings (
            guild_id   INTEGER PRIMARY KEY,
            channel_id INTEGER,
            role_id    INTEGER
        );
        CREATE TABLE IF NOT EXISTS done_log_channels (
            guild_id   INTEGER PRIMARY KEY,
            channel_id INTEGER
        );
        CREATE TABLE IF NOT EXISTS perk_settings (
            guild_id          INTEGER PRIMARY KEY,
            one_boost_role_id INTEGER,
            two_boost_role_id INTEGER,
            description       TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS welcome_embed_settings (
            guild_id       INTEGER PRIMARY KEY,
            title          TEXT,
            description    TEXT,
            color          INTEGER,
            image_url      TEXT,
            thumbnail_url  TEXT,
            invite_text    TEXT,
            account_text   TEXT,
            channel_id     TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS autorole_settings (
            guild_id INTEGER PRIMARY KEY,
            role_id INTEGER
        );
        CREATE TABLE IF NOT EXISTS link_settings (
            guild_id INTEGER PRIMARY KEY,
            label TEXT,
            url TEXT,
            alignment TEXT DEFAULT 'left'
        );
        CREATE TABLE IF NOT EXISTS tags (
            guild_id    INTEGER,
            tag_name    TEXT,
            response    TEXT    DEFAULT '',
            created_by  INTEGER DEFAULT 0,
            PRIMARY KEY (guild_id, tag_name)
        );
        CREATE TABLE IF NOT EXISTS trivia_scores (
            guild_id INTEGER,
            user_id INTEGER,
            score INTEGER DEFAULT 0,
            PRIMARY KEY (guild_id, user_id)
        );
        CREATE TABLE IF NOT EXISTS guild_lang_settings (
            guild_id INTEGER PRIMARY KEY,
            lang TEXT DEFAULT 'both'
        );
        CREATE TABLE IF NOT EXISTS staff_daily_roles (
            guild_id INTEGER,
            role_id INTEGER,
            PRIMARY KEY (guild_id, role_id)
        );
        CREATE TABLE IF NOT EXISTS islam_settings (
            guild_id   INTEGER PRIMARY KEY,
            channel_id INTEGER,
            role_id    INTEGER,
            text_en    TEXT DEFAULT '',
            text_ku    TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS islam_last_msg (
            guild_id   INTEGER PRIMARY KEY,
            message_id INTEGER
        );
    """)
    conn.commit()
    conn.close()

init_db()

# --- Migrate existing DBs: add columns added after initial release ---
def _migrate_db():
    conn = get_db()
    migrations = [
        "ALTER TABLE welcome_embed_settings ADD COLUMN channel_id TEXT DEFAULT ''",
        "ALTER TABLE perk_settings ADD COLUMN description TEXT DEFAULT ''",
        "ALTER TABLE reklam_settings ADD COLUMN text TEXT DEFAULT ''",
        """CREATE TABLE IF NOT EXISTS invite_custom_text (
            guild_id INTEGER PRIMARY KEY,
            text TEXT DEFAULT ''
        )""",
    ]
    for sql in migrations:
        try:
            conn.execute(sql)
        except Exception:
            pass   # column already exists — safe to ignore
    conn.commit()
    conn.close()
_migrate_db()

secret_role = "Gamer"

MESSAGE_XP_MIN = 15
MESSAGE_XP_MAX = 25
MESSAGE_XP_COOLDOWN = 60
VOICE_XP_PER_MINUTE = 10

xp_data = {}
warnings_data = {}
economy = {}
afk_users = {}
afk_cooldowns = {}
reklam_cooldowns = {}  # {(guild_id, user_id): last_used_timestamp}
level_channels = {}
welcome_channels = {}
welcome_embed_settings = {}  # {guild_id: {title,description,color,image_url,thumbnail_url,invite_text,account_text}}
invite_channels = {}
invite_data = {}
invite_counts = {}   # {guild_id: {user_id: {"total": n, "left": n}}}
invite_cache  = {}   # {guild_id: {code: uses}}  — live snapshot
apply_channels = {}  # {guild_id: channel_id}
apply_questions_map = {}  # {guild_id: [q1, q2, ...]}
apply_lang_map      = {}  # {guild_id: "both"|"ku"|"en"}
_DEFAULT_APPLY_QUESTIONS = [
    "١- دەتوانی کەسێکی باش بیت لەگەڵ کەسانی تر؟ | Can you be a good person with others?",
    "٢- دەتوانی ئەکتیڤ بیت لە ڤۆیس و چات؟ | Can you be active in voice and chat?",
    "٣- دەتوانی 3 ریکلامی ڕۆژانە بکەیت؟ | Can you do 3 daily ads?",
]
log_channels   = {}  # {guild_id: channel_id}
anti_link_guilds = {}  # {guild_id: True/False}  — anti-link toggle per server
staff_daily_channels = {}  # {guild_id: channel_id}  — where daily ping is sent
staff_daily_roles_map = {}  # {guild_id: [role_id, ...]}  — roles to ping
level_enabled = {}
ticket_settings = {}
open_tickets_map = {}
open_staff_apps  = {}  # {(guild_id, user_id): channel_id}
staff_submit_log_channels = {}  # {guild_id: channel_id}
rules_settings   = {}  # {guild_id: {"text_en": str, "text_ku": str}}
staff_daily_last_msg = {}  # {guild_id: message_id}
islam_settings_map = {}   # {guild_id: {channel_id, role_id, text_en, text_ku}}
islam_last_msg_map  = {}  # {guild_id: message_id}
tags_data = {}  # {guild_id_str: {tag_name_lower: {"response": str, "name": str, "created_by": int}}}
message_cooldowns = {}
voice_sessions = {}
rr_data = {}  # {message_id: [(role_id, emoji, label)]}  loaded from DB
selfrole_map = {}  # {message_id: {emoji_str: role_id}}  emoji reaction roles

EIGHT_BALL_RESPONSES = [
    "It is certain. | دڵنیاییە.",
    "Without a doubt. | بێ گومان.",
    "Yes - definitely. | بەڵێ - بەتەواوی.",
    "You may rely on it. | دەتوانیت پشت بدەی پێی.",
    "Most likely. | زۆرجار.",
    "Outlook good. | دیمەن باشە.",
    "Yes. | بەڵێ.",
    "Signs point to yes. | نیشانەکان بەرەو بەڵێ دەکەن.",
    "Reply hazy, try again. | وەڵامەکە شلەوەیە، دووبارە هەوڵبدەرەوە.",
    "Ask again later. | دواتر دووبارە بپرسە.",
    "Better not tell you now. | باشترە ئێستا نەتبڵێم.",
    "Cannot predict now. | ئێستا نایتوانم پێشبینی بکەم.",
    "Concentrate and ask again. | تەمەرکوز بکە و دووبارە بپرسە.",
    "Don't count on it. | سانی مەدە.",
    "My reply is no. | وەڵامم نەخێرە.",
    "My sources say no. | سەرچاوەکانم نەخێر دەڵێن.",
    "Outlook not so good. | دیمەن زۆر باش نییە.",
    "Very doubtful. | زۆر گومانپێکراوە.",
]

# --- SQLITE LOAD/SAVE FUNCTIONS ---

def load_xp():
    global xp_data
    xp_data = {}
    conn = get_db()
    for row in conn.execute("SELECT guild_id, user_id, message_xp, voice_xp FROM xp_data"):
        g = str(row["guild_id"])
        u = str(row["user_id"])
        xp_data.setdefault(g, {})[u] = {"message_xp": row["message_xp"], "voice_xp": row["voice_xp"]}
    conn.close()

def save_xp():
    conn = get_db()
    for gid, users in xp_data.items():
        for uid, entry in users.items():
            conn.execute(
                "INSERT INTO xp_data (guild_id, user_id, message_xp, voice_xp) VALUES (?,?,?,?) "
                "ON CONFLICT(guild_id, user_id) DO UPDATE SET message_xp=excluded.message_xp, voice_xp=excluded.voice_xp",
                (int(gid), int(uid), entry.get("message_xp", 0), entry.get("voice_xp", 0))
            )
    conn.commit()
    conn.close()

def save_xp_entry(guild_id, user_id):
    entry = xp_data.get(str(guild_id), {}).get(str(user_id), {"message_xp": 0, "voice_xp": 0})
    conn = get_db()
    conn.execute(
        "INSERT INTO xp_data (guild_id, user_id, message_xp, voice_xp) VALUES (?,?,?,?) "
        "ON CONFLICT(guild_id, user_id) DO UPDATE SET message_xp=excluded.message_xp, voice_xp=excluded.voice_xp",
        (int(guild_id), int(user_id), entry.get("message_xp", 0), entry.get("voice_xp", 0))
    )
    conn.commit()
    conn.close()

def load_warnings():
    global warnings_data
    warnings_data = {}
    conn = get_db()
    for row in conn.execute("SELECT guild_id, user_id, count FROM warnings"):
        g = str(row["guild_id"])
        u = str(row["user_id"])
        warnings_data.setdefault(g, {})[u] = row["count"]
    conn.close()

def save_warnings():
    conn = get_db()
    for gid, users in warnings_data.items():
        for uid, count in users.items():
            conn.execute(
                "INSERT INTO warnings (guild_id, user_id, count) VALUES (?,?,?) "
                "ON CONFLICT(guild_id, user_id) DO UPDATE SET count=excluded.count",
                (int(gid), int(uid), count)
            )
    conn.commit()
    conn.close()

def load_econ():
    global economy
    economy = {}
    conn = get_db()
    for row in conn.execute("SELECT guild_id, user_id, wallet, bank, last_daily, last_weekly, last_work, last_beg, inventory FROM economy"):
        g = str(row["guild_id"])
        u = str(row["user_id"])
        economy.setdefault(g, {})[u] = {
            "wallet": row["wallet"], "bank": row["bank"],
            "last_daily": row["last_daily"], "last_weekly": row["last_weekly"],
            "last_work": row["last_work"], "last_beg": row["last_beg"],
            "inventory": json.loads(row["inventory"] or "[]"),
        }
    conn.close()

def save_econ():
    conn = get_db()
    for gid, users in economy.items():
        for uid, e in users.items():
            conn.execute(
                "INSERT INTO economy (guild_id, user_id, wallet, bank, last_daily, last_weekly, last_work, last_beg, inventory) "
                "VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(guild_id, user_id) DO UPDATE SET "
                "wallet=excluded.wallet, bank=excluded.bank, last_daily=excluded.last_daily, "
                "last_weekly=excluded.last_weekly, last_work=excluded.last_work, last_beg=excluded.last_beg, "
                "inventory=excluded.inventory",
                (int(gid), int(uid), e["wallet"], e["bank"], e["last_daily"], e["last_weekly"],
                 e["last_work"], e["last_beg"], json.dumps(e["inventory"]))
            )
    conn.commit()
    conn.close()

def load_level_channels():
    global level_channels
    level_channels = {}
    conn = get_db()
    for row in conn.execute("SELECT guild_id, channel_id FROM level_channels"):
        level_channels[str(row["guild_id"])] = row["channel_id"]
    conn.close()

def save_level_channels():
    conn = get_db()
    for gid, cid in level_channels.items():
        conn.execute(
            "INSERT INTO level_channels (guild_id, channel_id) VALUES (?,?) "
            "ON CONFLICT(guild_id) DO UPDATE SET channel_id=excluded.channel_id",
            (int(gid), int(cid))
        )
    conn.commit()
    conn.close()

def load_ticket_settings():
    global ticket_settings, open_tickets_map
    ticket_settings = {}
    open_tickets_map = {}
    conn = get_db()
    for row in conn.execute("SELECT guild_id, staff_role_id, category_id, log_channel_id, panel_channel_id FROM ticket_settings"):
        ticket_settings[str(row["guild_id"])] = {
            "staff_role_id": row["staff_role_id"],
            "category_id": row["category_id"],
            "log_channel_id": row["log_channel_id"],
            "panel_channel_id": row["panel_channel_id"],
        }
    for row in conn.execute("SELECT guild_id, user_id, channel_id FROM open_tickets"):
        open_tickets_map[(str(row["guild_id"]), str(row["user_id"]))] = row["channel_id"]
    conn.close()

def save_ticket_settings():
    conn = get_db()
    for gid, s in ticket_settings.items():
        conn.execute(
            "INSERT INTO ticket_settings (guild_id, staff_role_id, category_id, log_channel_id, panel_channel_id) "
            "VALUES (?,?,?,?,?) ON CONFLICT(guild_id) DO UPDATE SET "
            "staff_role_id=excluded.staff_role_id, category_id=excluded.category_id, "
            "log_channel_id=excluded.log_channel_id, panel_channel_id=excluded.panel_channel_id",
            (int(gid), s.get("staff_role_id"), s.get("category_id"), s.get("log_channel_id"), s.get("panel_channel_id"))
        )
    conn.commit()
    conn.close()

def save_open_tickets():
    conn = get_db()
    conn.execute("DELETE FROM open_tickets")
    for (gid, uid), cid in open_tickets_map.items():
        conn.execute(
            "INSERT INTO open_tickets (guild_id, user_id, channel_id) VALUES (?,?,?)",
            (int(gid), int(uid), int(cid))
        )
    conn.commit()
    conn.close()

def load_staff_submit_log_channels():
    global staff_submit_log_channels, open_staff_apps
    staff_submit_log_channels = {}
    open_staff_apps = {}
    conn = get_db()
    for row in conn.execute("SELECT guild_id, channel_id FROM staff_submit_log_channels"):
        staff_submit_log_channels[str(row["guild_id"])] = row["channel_id"]
    for row in conn.execute("SELECT guild_id, user_id, channel_id FROM open_staff_apps"):
        open_staff_apps[(str(row["guild_id"]), str(row["user_id"]))] = row["channel_id"]
    conn.close()

def save_staff_submit_log_channels():
    conn = get_db()
    for gid, cid in staff_submit_log_channels.items():
        conn.execute(
            "INSERT INTO staff_submit_log_channels (guild_id, channel_id) VALUES (?,?) "
            "ON CONFLICT(guild_id) DO UPDATE SET channel_id=excluded.channel_id",
            (int(gid), int(cid))
        )
    conn.commit()
    conn.close()

def save_open_staff_apps():
    conn = get_db()
    conn.execute("DELETE FROM open_staff_apps")
    for (gid, uid), cid in open_staff_apps.items():
        conn.execute(
            "INSERT INTO open_staff_apps (guild_id, user_id, channel_id) VALUES (?,?,?)",
            (int(gid), int(uid), int(cid))
        )
    conn.commit()
    conn.close()

def load_rules_settings():
    global rules_settings
    rules_settings = {}
    conn = get_db()
    for row in conn.execute("SELECT guild_id, text_en, text_ku FROM rules_settings"):
        rules_settings[str(row["guild_id"])] = {
            "text_en": row["text_en"] or "",
            "text_ku": row["text_ku"] or "",
        }
    conn.close()

def save_rules_settings():
    conn = get_db()
    for gid, s in rules_settings.items():
        conn.execute(
            "INSERT INTO rules_settings (guild_id, text_en, text_ku) VALUES (?,?,?) "
            "ON CONFLICT(guild_id) DO UPDATE SET text_en=excluded.text_en, text_ku=excluded.text_ku",
            (int(gid), s.get("text_en", ""), s.get("text_ku", ""))
        )
    conn.commit()
    conn.close()

def load_staff_daily_last_msg():
    global staff_daily_last_msg
    staff_daily_last_msg = {}
    conn = get_db()
    for row in conn.execute("SELECT guild_id, message_id FROM staff_daily_last_msg"):
        staff_daily_last_msg[str(row["guild_id"])] = row["message_id"]
    conn.close()

def save_staff_daily_last_msg():
    conn = get_db()
    for gid, mid in staff_daily_last_msg.items():
        conn.execute(
            "INSERT INTO staff_daily_last_msg (guild_id, message_id) VALUES (?,?) "
            "ON CONFLICT(guild_id) DO UPDATE SET message_id=excluded.message_id",
            (int(gid), int(mid))
        )
    conn.commit()
    conn.close()

def load_tags():
    global tags_data
    tags_data = {}
    conn = get_db()
    for row in conn.execute("SELECT guild_id, tag_name, response, created_by FROM tags"):
        gid = str(row["guild_id"])
        tags_data.setdefault(gid, {})[row["tag_name"].lower()] = {
            "response":   row["response"] or "",
            "name":       row["tag_name"],
            "created_by": row["created_by"] or 0,
        }
    conn.close()

def save_tag(guild_id: int, tag_name: str, response: str, created_by: int = 0):
    conn = get_db()
    conn.execute(
        "INSERT INTO tags (guild_id, tag_name, response, created_by) VALUES (?,?,?,?) "
        "ON CONFLICT(guild_id, tag_name) DO UPDATE SET "
        "response=excluded.response, created_by=excluded.created_by",
        (guild_id, tag_name, response, created_by),
    )
    conn.commit()
    conn.close()
    gid = str(guild_id)
    tags_data.setdefault(gid, {})[tag_name.lower()] = {
        "response":   response,
        "name":       tag_name,
        "created_by": created_by,
    }

def delete_tag(guild_id: int, tag_name: str) -> bool:
    gid = str(guild_id)
    key = tag_name.lower()
    if key not in tags_data.get(gid, {}):
        return False
    conn = get_db()
    conn.execute(
        "DELETE FROM tags WHERE guild_id=? AND LOWER(tag_name)=LOWER(?)", (guild_id, tag_name)
    )
    conn.commit()
    conn.close()
    tags_data.get(gid, {}).pop(key, None)
    return True


def get_ticket_cfg(guild_id):
    return ticket_settings.get(str(guild_id), {})

async def ticket_log(guild, message):
    cfg = get_ticket_cfg(guild.id)
    log_cid = cfg.get("log_channel_id")
    if not log_cid:
        return
    ch = guild.get_channel(int(log_cid))
    if ch:
        embed = discord.Embed(color=0x5865f2, description=message, timestamp=datetime.datetime.utcnow())
        try:
            await ch.send(embed=embed)
        except (discord.Forbidden, discord.HTTPException):
            pass

def load_welcome_channels():
    global welcome_channels
    welcome_channels = {}
    conn = get_db()
    for row in conn.execute("SELECT guild_id, channel_id FROM welcome_channels"):
        welcome_channels[str(row["guild_id"])] = row["channel_id"]
    conn.close()

def save_welcome_channels():
    conn = get_db()
    for gid, cid in welcome_channels.items():
        conn.execute(
            "INSERT INTO welcome_channels (guild_id, channel_id) VALUES (?,?) "
            "ON CONFLICT(guild_id) DO UPDATE SET channel_id=excluded.channel_id",
            (int(gid), int(cid))
        )
    conn.commit()
    conn.close()

# --- WELCOME EMBED SETTINGS PERSISTENCE ---
_WES_DEFAULTS = {
    "title":        "☀️ بەخێرهاتی بۆ (server)! | Welcome to (server)!",
    "description":  "👋 هەی (user)، بەخێربێیت! ✨\n🌟 هیوادارم کاتێکی خۆش لەگەڵمان بژیت! 🎉\n\n👋 Hey (user), welcome! ✨\n🌟 I hope you'll have a great time with us! 🎉",
    "color":        0xFFD700,
    "image_url":    "",
    "thumbnail_url": "avatar",
    "invite_text":  "🔗 Invited by: (invite.user) | Total invites: (invite.count)",
    "account_text": "📅 Account created: (account.age)",
    "channel_id":    "",
}

def get_welcome_embed_settings(guild_id):
    gid = str(guild_id)
    if gid not in welcome_embed_settings:
        welcome_embed_settings[gid] = dict(_WES_DEFAULTS)
    return welcome_embed_settings[gid]

def save_welcome_embed_setting(guild_id, **kwargs):
    gid = str(guild_id)
    if gid not in welcome_embed_settings:
        welcome_embed_settings[gid] = dict(_WES_DEFAULTS)
    welcome_embed_settings[gid].update(kwargs)
    s = welcome_embed_settings[gid]
    conn = get_db()
    conn.execute(
        "INSERT INTO welcome_embed_settings "
        "(guild_id,title,description,color,image_url,thumbnail_url,invite_text,account_text,channel_id) "
        "VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(guild_id) DO UPDATE SET "
        "title=excluded.title, description=excluded.description, color=excluded.color, "
        "image_url=excluded.image_url, thumbnail_url=excluded.thumbnail_url, "
        "invite_text=excluded.invite_text, account_text=excluded.account_text, channel_id=excluded.channel_id",
        (int(guild_id), s["title"], s["description"], s["color"],
         s["image_url"], s["thumbnail_url"], s["invite_text"], s["account_text"], s.get("channel_id","")))
    conn.commit()
    conn.close()

def load_welcome_embed_settings():
    global welcome_embed_settings
    welcome_embed_settings = {}
    conn = get_db()
    for row in conn.execute("SELECT * FROM welcome_embed_settings"):
        welcome_embed_settings[str(row["guild_id"])] = {
            "title":        row["title"]        or _WES_DEFAULTS["title"],
            "description":  row["description"]  or _WES_DEFAULTS["description"],
            "color":        row["color"]        or _WES_DEFAULTS["color"],
            "image_url":    row["image_url"]    or "",
            "thumbnail_url":row["thumbnail_url"] or "avatar",
            "invite_text":  row["invite_text"]  or _WES_DEFAULTS["invite_text"],
            "account_text": row["account_text"] or _WES_DEFAULTS["account_text"],
            "account_text": row["account_text"] or _WES_DEFAULTS["account_text"],
            "channel_id":   row["channel_id"]   if "channel_id" in row.keys() else "",
        }
def apply_welcome_placeholders(text, member, inviter=None, inv_total=0, channel_id=""):
    """Replace (user), (server), (invite.user), (invite.count), (account.age) etc."""
    if not text:
        return text
    account_created = member.created_at
    now = datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc)
    diff_days = (now - account_created).days
    if diff_days >= 365:
        age_str = f"{diff_days // 365} year{'s' if diff_days//365 != 1 else ''} ago"
    elif diff_days >= 30:
        months = diff_days // 30
        age_str = f"{months} month{'s' if months != 1 else ''} ago"
    else:
        age_str = f"{diff_days} day{'s' if diff_days != 1 else ''} ago"

    text = text.replace("(user)", member.mention)
    text = text.replace("(user.name)", member.display_name)
    text = text.replace("(server)", member.guild.name)
    text = text.replace("(member.count)", f"{member.guild.member_count:,}")
    text = text.replace("(invite.user)", inviter.mention if inviter else "Unknown")
    text = text.replace("(invite.user.name)", inviter.display_name if inviter else "Unknown")
    text = text.replace("(invite.count)", str(inv_total))
    text = text.replace("(account.age)", age_str)
    text = text.replace("(channelid)", f"<#{channel_id}>" if channel_id else "(channelid)")
    return text

# --- INVITE TRACKING PERSISTENCE ---
def load_invite_channels():
    global invite_channels
    invite_channels = {}
    conn = get_db()
    for row in conn.execute("SELECT guild_id, channel_id FROM invite_channels"):
        invite_channels[str(row["guild_id"])] = row["channel_id"]
    conn.close()

def save_invite_channels():
    conn = get_db()
    for gid, cid in invite_channels.items():
        conn.execute(
            "INSERT INTO invite_channels (guild_id, channel_id) VALUES (?,?) "
            "ON CONFLICT(guild_id) DO UPDATE SET channel_id=excluded.channel_id",
            (int(gid), int(cid))
        )
    conn.commit()
    conn.close()

def load_invite_counts():
    global invite_counts
    invite_counts = {}
    conn = get_db()
    for row in conn.execute("SELECT guild_id, user_id, total, left_count FROM invite_counts"):
        g = invite_counts.setdefault(str(row["guild_id"]), {})
        g[str(row["user_id"])] = {"total": row["total"], "left": row["left_count"]}
    conn.close()

def save_invite_counts():
    conn = get_db()
    for gid, users in invite_counts.items():
        for uid, d in users.items():
            conn.execute(
                "INSERT INTO invite_counts (guild_id, user_id, total, left_count) VALUES (?,?,?,?) "
                "ON CONFLICT(guild_id, user_id) DO UPDATE SET total=excluded.total, left_count=excluded.left_count",
                (int(gid), int(uid), d.get("total", 0), d.get("left", 0))
            )
    conn.commit()
    conn.close()

def _get_invite_counts(gid, uid):
    return invite_counts.setdefault(str(gid), {}).setdefault(str(uid), {"total": 0, "left": 0})

def load_apply_channels():
    global apply_channels
    apply_channels = {}
    conn = get_db()
    for row in conn.execute("SELECT guild_id, channel_id FROM apply_channels"):
        apply_channels[str(row["guild_id"])] = row["channel_id"]
    conn.close()

def save_apply_channels():
    conn = get_db()
    for gid, cid in apply_channels.items():
        conn.execute(
            "INSERT INTO apply_channels (guild_id, channel_id) VALUES (?,?) "
            "ON CONFLICT(guild_id) DO UPDATE SET channel_id=excluded.channel_id",
            (int(gid), int(cid))
        )
    conn.commit()
    conn.close()

boost_channels = {}

def load_boost_channels():
    global boost_channels
    boost_channels = {}
    conn = get_db()
    for row in conn.execute("SELECT guild_id, channel_id FROM boost_channels"):
        boost_channels[str(row["guild_id"])] = row["channel_id"]
    conn.close()

def save_boost_channel(guild_id, channel_id):
    conn = get_db()
    conn.execute(
        "INSERT INTO boost_channels (guild_id, channel_id) VALUES (?,?) "
        "ON CONFLICT(guild_id) DO UPDATE SET channel_id=excluded.channel_id",
        (int(guild_id), int(channel_id))
    )
    conn.commit()
    conn.close()

def get_perk_settings(guild_id: int):
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM perk_settings WHERE guild_id=?",
        (int(guild_id),)
    ).fetchone()
    conn.close()
    if row:
        keys = row.keys()
        return {
            "one_boost_role_id": row["one_boost_role_id"],
            "two_boost_role_id": row["two_boost_role_id"],
            "description": row["description"] if "description" in keys else "",
        }
    return None

def save_perk_settings(guild_id: int, one_boost_role_id: int, two_boost_role_id: int):
    conn = get_db()
    conn.execute(
        "INSERT INTO perk_settings (guild_id, one_boost_role_id, two_boost_role_id) VALUES (?,?,?) "
        "ON CONFLICT(guild_id) DO UPDATE SET one_boost_role_id=excluded.one_boost_role_id, two_boost_role_id=excluded.two_boost_role_id",
        (int(guild_id), int(one_boost_role_id), int(two_boost_role_id))
    )
    conn.commit()
    conn.close()

def save_perk_description(guild_id: int, description: str):
    conn = get_db()
    conn.execute(
        "INSERT INTO perk_settings (guild_id, description) VALUES (?,?) "
        "ON CONFLICT(guild_id) DO UPDATE SET description=excluded.description",
        (int(guild_id), description)
    )
    conn.commit()
    conn.close()

def save_perk_role1(guild_id: int, role_id: int):
    conn = get_db()
    conn.execute(
        "INSERT INTO perk_settings (guild_id, one_boost_role_id) VALUES (?,?) "
        "ON CONFLICT(guild_id) DO UPDATE SET one_boost_role_id=excluded.one_boost_role_id",
        (int(guild_id), int(role_id))
    )
    conn.commit()
    conn.close()

def save_perk_role2(guild_id: int, role_id: int):
    conn = get_db()
    conn.execute(
        "INSERT INTO perk_settings (guild_id, two_boost_role_id) VALUES (?,?) "
        "ON CONFLICT(guild_id) DO UPDATE SET two_boost_role_id=excluded.two_boost_role_id",
        (int(guild_id), int(role_id))
    )
    conn.commit()
    conn.close()

def load_log_channels():
    global log_channels
    log_channels = {}
    conn = get_db()
    for row in conn.execute("SELECT guild_id, channel_id FROM log_channels"):
        log_channels[str(row["guild_id"])] = row["channel_id"]
    conn.close()

def save_log_channels():
    conn = get_db()
    for gid, cid in log_channels.items():
        conn.execute(
            "INSERT INTO log_channels (guild_id, channel_id) VALUES (?,?) "
            "ON CONFLICT(guild_id) DO UPDATE SET channel_id=excluded.channel_id",
            (int(gid), int(cid))
        )
    conn.commit()
    conn.close()

def load_staff_daily_channels():
    global staff_daily_channels
    staff_daily_channels = {}
    conn = get_db()
    for row in conn.execute("SELECT guild_id, channel_id FROM staff_daily_channels"):
        staff_daily_channels[str(row["guild_id"])] = row["channel_id"]
    conn.close()

def save_staff_daily_channels():
    conn = get_db()
    for gid, cid in staff_daily_channels.items():
        conn.execute(
            "INSERT INTO staff_daily_channels (guild_id, channel_id) VALUES (?,?) "
            "ON CONFLICT(guild_id) DO UPDATE SET channel_id=excluded.channel_id",
            (int(gid), int(cid))
        )
    conn.commit()
    conn.close()

def load_staff_daily_roles():
    global staff_daily_roles_map
    staff_daily_roles_map = {}
    conn = get_db()
    for row in conn.execute('SELECT guild_id, role_id FROM staff_daily_roles'):
        g = str(row['guild_id'])
        staff_daily_roles_map.setdefault(g, []).append(row['role_id'])
    conn.close()

def save_staff_daily_roles(guild_id: str, role_ids: list):
    conn = get_db()
    conn.execute('DELETE FROM staff_daily_roles WHERE guild_id=?', (int(guild_id),))
    for rid in role_ids:
        conn.execute('INSERT OR IGNORE INTO staff_daily_roles (guild_id, role_id) VALUES (?,?)', (int(guild_id), int(rid)))
    conn.commit()
    conn.close()
    staff_daily_roles_map[guild_id] = list(role_ids)

def load_islam_settings():
    global islam_settings_map, islam_last_msg_map
    islam_settings_map = {}
    islam_last_msg_map = {}
    conn = get_db()
    for row in conn.execute("SELECT guild_id, channel_id, role_id, text_en, text_ku FROM islam_settings"):
        islam_settings_map[str(row["guild_id"])] = {
            "channel_id": row["channel_id"],
            "role_id":    row["role_id"],
            "text_en":    row["text_en"] or "",
            "text_ku":    row["text_ku"] or "",
        }
    for row in conn.execute("SELECT guild_id, message_id FROM islam_last_msg"):
        islam_last_msg_map[str(row["guild_id"])] = row["message_id"]
    conn.close()

def save_islam_settings(guild_id, channel_id=None, role_id=None, text_en=None, text_ku=None):
    gid = str(guild_id)
    cur = islam_settings_map.setdefault(gid, {"channel_id": None, "role_id": None, "text_en": "", "text_ku": ""})
    if channel_id is not None: cur["channel_id"] = channel_id
    if role_id    is not None: cur["role_id"]    = role_id
    if text_en    is not None: cur["text_en"]    = text_en
    if text_ku    is not None: cur["text_ku"]    = text_ku
    conn = get_db()
    conn.execute(
        "INSERT INTO islam_settings (guild_id, channel_id, role_id, text_en, text_ku) VALUES (?,?,?,?,?) "
        "ON CONFLICT(guild_id) DO UPDATE SET channel_id=excluded.channel_id, role_id=excluded.role_id, "
        "text_en=excluded.text_en, text_ku=excluded.text_ku",
        (int(guild_id), cur["channel_id"], cur["role_id"], cur["text_en"], cur["text_ku"])
    )
    conn.commit()
    conn.close()

def save_islam_last_msg(guild_id, message_id):
    gid = str(guild_id)
    islam_last_msg_map[gid] = message_id
    conn = get_db()
    conn.execute(
        "INSERT INTO islam_last_msg (guild_id, message_id) VALUES (?,?) "
        "ON CONFLICT(guild_id) DO UPDATE SET message_id=excluded.message_id",
        (int(guild_id), int(message_id))
    )
    conn.commit()
    conn.close()

def load_apply_questions():
    global apply_questions_map
    apply_questions_map = {}
    conn = get_db()
    for row in conn.execute("SELECT guild_id, slot, question FROM apply_questions ORDER BY guild_id, slot"):
        apply_questions_map.setdefault(str(row["guild_id"]), []).append(row["question"])
    conn.close()

def save_apply_questions(guild_id: int, questions: list):
    apply_questions_map[str(guild_id)] = questions
    conn = get_db()
    conn.execute("DELETE FROM apply_questions WHERE guild_id=?", (guild_id,))
    for i, q in enumerate(questions[:5], start=1):
        conn.execute("INSERT INTO apply_questions (guild_id, slot, question) VALUES (?,?,?)", (guild_id, i, q))
    conn.commit()
    conn.close()

def load_apply_lang():
    global apply_lang_map
    apply_lang_map = {}
    conn = get_db()
    for row in conn.execute("SELECT guild_id, lang FROM apply_lang"):
        apply_lang_map[str(row["guild_id"])] = row["lang"]
    conn.close()

def save_apply_lang(guild_id: int, lang: str):
    apply_lang_map[str(guild_id)] = lang
    conn = get_db()
    conn.execute(
        "INSERT INTO apply_lang (guild_id, lang) VALUES (?,?) ON CONFLICT(guild_id) DO UPDATE SET lang=excluded.lang",
        (guild_id, lang)
    )
    conn.commit()
    conn.close()




def log_staff_done(guild_id: int, user_id: int, display_name: str):
    conn = get_db()
    conn.execute(
        "INSERT INTO staff_done_log (guild_id, user_id, display_name, done_at) VALUES (?,?,?,?)",
        (guild_id, user_id, display_name, datetime.datetime.utcnow().isoformat())
    )
    conn.commit()
    conn.close()


def get_staff_done_since(guild_id: int, since_iso: str):
    conn = get_db()
    rows = conn.execute(
        "SELECT user_id, display_name, done_at FROM staff_done_log "
        "WHERE guild_id=? AND done_at>=? ORDER BY done_at ASC",
        (guild_id, since_iso)
    ).fetchall()
    conn.close()
    return rows


def get_staff_done_role(guild_id: int):
    conn = get_db()
    row = conn.execute(
        "SELECT role_id FROM staff_done_role WHERE guild_id=?", (guild_id,)
    ).fetchone()
    conn.close()
    return row["role_id"] if row else None


def save_staff_done_role(guild_id: int, role_id: int):
    conn = get_db()
    conn.execute(
        "INSERT INTO staff_done_role (guild_id, role_id) VALUES (?,?) "
        "ON CONFLICT(guild_id) DO UPDATE SET role_id=excluded.role_id",
        (guild_id, role_id)
    )
    conn.commit()
    conn.close()


def get_done_log_channel(guild_id: int):
    conn = get_db()
    row = conn.execute(
        "SELECT channel_id FROM done_log_channels WHERE guild_id=?", (guild_id,)
    ).fetchone()
    conn.close()
    return row["channel_id"] if row else None

def save_done_log_channel(guild_id: int, channel_id: int):
    conn = get_db()
    conn.execute(
        "INSERT INTO done_log_channels (guild_id, channel_id) VALUES (?,?) "
        "ON CONFLICT(guild_id) DO UPDATE SET channel_id=excluded.channel_id",
        (guild_id, channel_id)
    )
    conn.commit()
    conn.close()


def get_reklam_settings(guild_id: int):
    conn = get_db()
    row = conn.execute(
        "SELECT channel_id, role_id, text FROM reklam_settings WHERE guild_id=?", (guild_id,)
    ).fetchone()
    conn.close()
    if row:
        return {"channel_id": row["channel_id"], "role_id": row["role_id"], "text": row["text"] or ""}
    return None


def save_reklam_settings(guild_id: int, channel_id: int, role_id: int):
    conn = get_db()
    conn.execute(
        "INSERT INTO reklam_settings (guild_id, channel_id, role_id) VALUES (?,?,?) "
        "ON CONFLICT(guild_id) DO UPDATE SET channel_id=excluded.channel_id, role_id=excluded.role_id",
        (guild_id, channel_id, role_id)
    )
    conn.commit()
    conn.close()


def save_reklam_text(guild_id: int, text: str):
    """Save custom reklam notification text (supports {user} placeholder)."""
    conn = get_db()
    conn.execute(
        "INSERT INTO reklam_settings (guild_id, text) VALUES (?,?) "
        "ON CONFLICT(guild_id) DO UPDATE SET text=excluded.text",
        (guild_id, text)
    )
    conn.commit()
    conn.close()


def get_invite_custom_text(guild_id: int) -> str:
    """Get custom invite announcement text for this guild."""
    conn = get_db()
    row = conn.execute(
        "SELECT text FROM invite_custom_text WHERE guild_id=?", (guild_id,)
    ).fetchone()
    conn.close()
    return row["text"] if row else ""


def save_invite_custom_text(guild_id: int, text: str):
    """Save custom invite announcement text for this guild."""
    conn = get_db()
    conn.execute(
        "INSERT INTO invite_custom_text (guild_id, text) VALUES (?,?) "
        "ON CONFLICT(guild_id) DO UPDATE SET text=excluded.text",
        (guild_id, text)
    )
    conn.commit()
    conn.close()

def load_rr():
    global rr_data
    rr_data = {}
    conn = get_db()
    for row in conn.execute("SELECT message_id, role_id, emoji, label FROM rr_buttons"):
        rr_data.setdefault(row["message_id"], []).append(
            (row["role_id"], row["emoji"], row["label"])
        )
    conn.close()

def _save_rr_panel(guild_id, channel_id, message_id, title, description):
    conn = get_db()
    conn.execute(
        "INSERT INTO rr_panels (guild_id, channel_id, message_id, title, description) VALUES (?,?,?,?,?) "
        "ON CONFLICT(message_id) DO UPDATE SET title=excluded.title, description=excluded.description",
        (guild_id, channel_id, message_id, title, description)
    )
    conn.commit()
    conn.close()

def _save_rr_button(message_id, role_id, emoji, label):
    conn = get_db()
    conn.execute(
        "INSERT INTO rr_buttons (message_id, role_id, emoji, label) VALUES (?,?,?,?) "
        "ON CONFLICT(message_id, role_id) DO UPDATE SET emoji=excluded.emoji, label=excluded.label",
        (message_id, role_id, emoji, label)
    )
    conn.commit()
    conn.close()

def _delete_rr_button(message_id, role_id):
    conn = get_db()
    conn.execute("DELETE FROM rr_buttons WHERE message_id=? AND role_id=?", (message_id, role_id))
    conn.commit()
    conn.close()

def _delete_rr_panel(message_id):
    conn = get_db()
    conn.execute("DELETE FROM rr_buttons WHERE message_id=?", (message_id,))
    conn.execute("DELETE FROM rr_panels  WHERE message_id=?", (message_id,))
    conn.commit()
    conn.close()

async def _send_log(guild, embed):
    """Send an embed to the configured log channel, if set."""
    cid = log_channels.get(str(guild.id))
    if not cid:
        return
    ch = guild.get_channel(int(cid))
    if ch:
        try:
            await ch.send(embed=embed)
        except (discord.Forbidden, discord.HTTPException):
            pass

def load_afk():
    global afk_users
    afk_users = {}
    conn = get_db()
    for row in conn.execute("SELECT guild_id, user_id, reason, since, old_nick, image_url FROM afk_users"):
        key = (row["guild_id"], row["user_id"])
        afk_users[key] = {
            "reason": row["reason"], "since": row["since"],
            "old_nick": row["old_nick"], "image_url": row["image_url"]
        }
    conn.close()

def save_afk():
    conn = get_db()
    conn.execute("DELETE FROM afk_users")
    for (gid, uid), data in afk_users.items():
        conn.execute(
            "INSERT INTO afk_users (guild_id, user_id, reason, since, old_nick, image_url) VALUES (?,?,?,?,?,?)",
            (int(gid), int(uid), data.get("reason"), data.get("since"), data.get("old_nick"), data.get("image_url"))
        )
    conn.commit()
    conn.close()

def get_econ(gid, uid):
    g = economy.setdefault(str(gid), {})
    return g.setdefault(str(uid), {
        "wallet": 0, "bank": 0,
        "last_daily": 0, "last_weekly": 0,
        "last_work": 0, "last_beg": 0,
        "inventory": [],
    })

START_TIME = time.time()

# --- UTILITY FUNCTIONS ---

def fmt_uptime(seconds):
    days, seconds = divmod(int(seconds), 86400)
    hours, seconds = divmod(seconds, 3600)
    mins, secs = divmod(seconds, 60)
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if mins:
        parts.append(f"{mins}m")
    parts.append(f"{secs}s")
    return " ".join(parts)

def get_user_entry(guild_id, user_id):
    g = xp_data.setdefault(str(guild_id), {})
    return g.setdefault(str(user_id), {"message_xp": 0, "voice_xp": 0})

def add_xp(guild_id, user_id, amount, kind):
    entry = get_user_entry(guild_id, user_id)
    entry[kind] = entry.get(kind, 0) + amount
    save_xp_entry(guild_id, user_id)

def total_xp(entry):
    return entry.get("message_xp", 0) + entry.get("voice_xp", 0)

def level_from_xp(xp):
    return int(math.floor(math.sqrt(xp / 100)))

def xp_for_level(level):
    return (level ** 2) * 100

def make_progress_bar(current, total, length=20):
    if total <= 0:
        return "░" * length
    pct = max(0.0, min(1.0, current / total))
    filled = int(pct * length)
    return "█" * filled + "░" * (length - filled)

def humanize_seconds(s):
    s = int(max(0, s))
    if s < 60:
        return f"{s}s"
    m, s = divmod(s, 60)
    if m < 60:
        return f"{m}m {s}s"
    h, m = divmod(m, 60)
    if h < 24:
        return f"{h}h {m}m"
    d, h = divmod(h, 24)
    return f"{d}d {h}h"

def get_level_channel(guild):
    cid = level_channels.get(str(guild.id))
    if cid is None:
        return None
    return guild.get_channel(int(cid))

async def announce_level_up(member, fallback_channel, new_level, source):
    target = get_level_channel(member.guild) or fallback_channel
    if target is None:
        return
    color = discord.Color.from_hsv((min(new_level, 50) / 50) * 0.83, 0.90, 1.0)
    icon = level_icon(new_level)
    next_xp = xp_for_level(new_level + 1) - xp_for_level(new_level)
    embed = discord.Embed(
        title=f"🎉 LEVEL UP! | ئاستت بەرزبووەوە!",
        description=(
            f"### {member.mention} reached {icon} **Level {new_level}**!\n"
            f"گەیشتە {icon} **ئاستی {new_level}**!\n\n"
            f"{'💬 Earned from chatting | کسبکرا لە پەیامدانەوە' if source == 'message' else '🎙️ Earned in voice chat | کسبکرا لە دەنگدانەوە'}"
        ),
        color=color,
        timestamp=datetime.datetime.utcnow(),
    )
    embed.set_author(
        name=member.display_name,
        icon_url=member.display_avatar.url if member.display_avatar else None
    )
    if member.display_avatar:
        embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name=f"{icon} Level | ئاست", value=f"**{new_level}**", inline=True)
    embed.add_field(name="🎯 Next Goal | ئامانجی داهاتوو", value=f"`{next_xp:,}` XP", inline=True)
    embed.add_field(name="⚡ Keep Going!", value="Chat & voice = more XP\nپەیام و دەنگ = زیاتر XP", inline=True)
    embed.set_footer(text=f"GG {member.display_name}! ⚡ Keep climbing • بەردەوام بە!")
    try:
        await target.send(embed=embed)
    except (discord.Forbidden, discord.HTTPException):
        pass

# ─── SELFROLE EMOJI REACTION HELPERS ─────────────────────────────────────────

def load_selfrole():
    global selfrole_map
    selfrole_map = {}
    conn = get_db()
    for row in conn.execute("SELECT message_id, emoji, role_id FROM selfrole_reactions"):
        mid = row["message_id"]
        selfrole_map.setdefault(mid, {})[row["emoji"]] = row["role_id"]
    conn.close()

def _save_selfrole_panel(guild_id, message_id, channel_id, title):
    conn = get_db()
    conn.execute(
        "INSERT OR REPLACE INTO selfrole_panels (guild_id, message_id, channel_id, title) VALUES (?,?,?,?)",
        (guild_id, message_id, channel_id, title)
    )
    conn.commit()
    conn.close()

def _save_selfrole_entry(guild_id, message_id, emoji, role_id):
    conn = get_db()
    conn.execute(
        "INSERT OR REPLACE INTO selfrole_reactions (guild_id, message_id, emoji, role_id) VALUES (?,?,?,?)",
        (guild_id, message_id, emoji, role_id)
    )
    conn.commit()
    conn.close()

def _delete_selfrole_panel(message_id):
    conn = get_db()
    conn.execute("DELETE FROM selfrole_reactions WHERE message_id=?", (message_id,))
    conn.execute("DELETE FROM selfrole_panels  WHERE message_id=?", (message_id,))
    conn.commit()
    conn.close()

def _get_selfrole_panels(guild_id):
    conn = get_db()
    rows = conn.execute(
        "SELECT p.message_id, p.channel_id, p.title, r.emoji, r.role_id "
        "FROM selfrole_panels p JOIN selfrole_reactions r ON p.message_id=r.message_id "
        "WHERE p.guild_id=?", (guild_id,)
    ).fetchall()
    conn.close()
    panels = {}
    for r in rows:
        mid = r["message_id"]
        if mid not in panels:
            panels[mid] = {"channel_id": r["channel_id"], "title": r["title"], "entries": []}
        panels[mid]["entries"].append((r["emoji"], r["role_id"]))
    return panels

def parse_duration(text):
    units = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    m = re.match(r"^(\d+)([smhd])$", text.lower())
    if not m:
        return None
    return int(m.group(1)) * units[m.group(2)]

# --- INITIALIZE DATA ---
load_xp()
load_warnings()
load_econ()
load_level_channels()
load_welcome_channels()
load_welcome_embed_settings()
load_boost_channels()
load_ticket_settings()
load_afk()
load_invite_channels()
load_invite_counts()
load_apply_channels()
load_apply_questions()
load_apply_lang()
load_log_channels()
load_staff_submit_log_channels()
load_rules_settings()
load_staff_daily_last_msg()
load_tags()
load_rr()
load_selfrole()
load_staff_daily_channels()
load_islam_settings()

# --- BOT EVENTS ---

@bot.event
async def on_ready():
    print(f"We are ready to go in, {bot.user.name}")
    if not voice_xp_tick.is_running():
        voice_xp_tick.start()
    if not autosave.is_running():
        autosave.start()
    if not idle_check.is_running():
        idle_check.start()
    if not staff_daily_task.is_running():
        staff_daily_task.start()
    if not islam_thursday_task.is_running():
        islam_thursday_task.start()
    bot.add_view(TicketPanelView())
    bot.add_view(TicketControlView())
    bot.add_view(StaffAppControlView())
    bot.add_view(RulesPanelView())
    bot.add_view(ApplyView())
    bot.add_view(ASetApplyView())
    bot.add_view(StaffDoneView())
    bot.add_view(IslamSetupView())
    for mid, buttons in list(rr_data.items()):
        if buttons:
            bot.add_view(ReactionRoleView(mid, buttons))
    for guild in bot.guilds:
        for vc in guild.voice_channels:
            for member in vc.members:
                if not member.bot:
                    voice_sessions[(guild.id, member.id)] = time.time()
    # Cache all guild invites for invite tracking
    for guild in bot.guilds:
        try:
            invites = await guild.invites()
            invite_cache[guild.id] = {inv.code: inv.uses for inv in invites}
        except (discord.Forbidden, discord.HTTPException):
            invite_cache[guild.id] = {}

@bot.event
async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
    if payload.user_id == bot.user.id:
        return
    mid = payload.message_id
    if mid not in selfrole_map:
        return
    emoji_str = str(payload.emoji)
    role_id = selfrole_map[mid].get(emoji_str)
    if not role_id:
        return
    guild = bot.get_guild(payload.guild_id)
    if not guild:
        return
    member = guild.get_member(payload.user_id)
    role   = guild.get_role(role_id)
    if member and role:
        try:
            await member.add_roles(role, reason="Self-Role Reaction")
        except discord.Forbidden:
            pass

@bot.event
async def on_raw_reaction_remove(payload: discord.RawReactionActionEvent):
    if payload.user_id == bot.user.id:
        return
    mid = payload.message_id
    if mid not in selfrole_map:
        return
    emoji_str = str(payload.emoji)
    role_id = selfrole_map[mid].get(emoji_str)
    if not role_id:
        return
    guild = bot.get_guild(payload.guild_id)
    if not guild:
        return
    member = guild.get_member(payload.user_id)
    role   = guild.get_role(role_id)
    if member and role:
        try:
            await member.remove_roles(role, reason="Self-Role Reaction Removed")
        except discord.Forbidden:
            pass

@bot.event
async def on_invite_create(invite):
    gid = invite.guild.id
    if gid not in invite_cache:
        invite_cache[gid] = {}
    invite_cache[gid][invite.code] = invite.uses

@bot.event
async def on_invite_delete(invite):
    gid = invite.guild.id
    invite_cache.get(gid, {}).pop(invite.code, None)

@bot.event
async def on_member_join(member):
    gid = member.guild.id

    # --- INVITE TRACKING (must run first so (invite.user) is available for welcome embed) ---
    inviter   = None
    inv_total = 0
    try:
        new_invites  = await member.guild.invites()
        old_snapshot = invite_cache.get(gid, {})
        for inv in new_invites:
            if inv.uses > old_snapshot.get(inv.code, 0):
                inviter = inv.inviter
                d = _get_invite_counts(gid, inv.inviter.id)
                d["total"] += 1
                inv_total = d["total"]
                save_invite_counts()
                break
        invite_cache[gid] = {inv.code: inv.uses for inv in new_invites}
    except (discord.Forbidden, discord.HTTPException):
        pass

    # --- WELCOME EMBED IN CHANNEL ---
    cid = welcome_channels.get(str(gid))
    if cid:
        channel = member.guild.get_channel(int(cid))
        if channel:
            s     = get_welcome_embed_settings(gid)
            embed = _build_welcome_embed(s, member, inviter=inviter, inv_total=inv_total)
            try:
                await channel.send(embed=embed)
            except (discord.Forbidden, discord.HTTPException):
                pass

    icid = invite_channels.get(str(gid))
    if icid:
        ichannel = member.guild.get_channel(int(icid))
        if ichannel:
            inv_total = _get_invite_counts(gid, inviter.id)["total"] if inviter else 0
            embed = discord.Embed(
                color=0x57F287,
                title="📨 ئەندامێکی نوێ بەشداری کرد! | New Member Joined!",
                description=(
                    f"{member.mention} بەشداری سێرڤەر کرد.\n"
                    f"**{member.guild.name}** now has **{member.guild.member_count:,}** members.\n\n"
                    + (
                        f"🔗 بانگهێشتکراوە لەلایەن | Invited by: {inviter.mention}\n"
                        f"📊 کۆی بانگهێشتکردنەکان | Total invites: **{inv_total}**"
                        if inviter else
                        "🔗 سەرچاوەی بانگهێشتکردن نەدۆزرایەوە | Invite source unknown"
                    )
                ),
                timestamp=datetime.datetime.utcnow(),
            )
            embed.set_thumbnail(url=member.display_avatar.url)
            if inviter:
                embed.set_footer(
                    text=f"Inviter: {inviter.display_name}",
                    icon_url=inviter.display_avatar.url,
                )
            embed.add_field(name="👤 ئەندام | Member", value=f"{member} (`{member.id}`)", inline=True)
            embed.add_field(name="🎂 ئەکاونت دروستکراوە | Account Age",
                            value=f"<t:{int(member.created_at.timestamp())}:R>", inline=True)
            embed.add_field(name="📈 ژمارەی ئەندامان | Member #",
                            value=f"#{member.guild.member_count:,}", inline=True)
            try:
                await ichannel.send(embed=embed)
            except (discord.Forbidden, discord.HTTPException):
                pass



    # --- AUTO-ROLE ASSIGNMENT ---
    try:
        with get_db() as _ar_conn:
            _ar_row = _ar_conn.execute(
                'SELECT role_id FROM autorole_settings WHERE guild_id=?', (gid,)
            ).fetchone()
        if _ar_row:
            _ar_role = member.guild.get_role(_ar_row['role_id'])
            if _ar_role and _ar_role < member.guild.me.top_role:
                await member.add_roles(_ar_role, reason='Auto-role on join')
    except Exception:
        pass

@bot.event
async def on_message(message):
    if message.author == bot.user or message.author.bot:
        return

    # --- ANTI-LINK FILTER ---
    if message.guild and anti_link_guilds.get(str(message.guild.id)):
        has_link = bool(re.search(r'https?://|discord[.]gg/|www[.]', message.content, re.IGNORECASE))
        if has_link:
            has_exempt = any(
                r.permissions.manage_messages or r.permissions.administrator
                for r in getattr(message.author, 'roles', [])
            )
            if not has_exempt:
                try:
                    await message.delete()
                    await message.channel.send(
                        f"⛔ {message.author.mention} لینک ناشەرعییە لەم کەناڵەدا! | Links are not allowed here!",
                        delete_after=5
                    )
                except (discord.Forbidden, discord.HTTPException):
                    pass
                return

    if message.guild is not None:
        # --- COOLER AFK SYSTEM: RETURN FROM AFK ---
        key = (message.guild.id, message.author.id)
        if key in afk_users:
            is_afk_cmd = message.content.startswith(bot.command_prefix + "afk")
            is_any_cmd = message.content.startswith(bot.command_prefix)

            if not is_afk_cmd:
                data = afk_users.pop(key)
                save_afk()

                try:
                    if data.get("old_nick") is not None or (message.author.nick and message.author.nick.startswith("💤")):
                        await message.author.edit(nick=data.get("old_nick"))
                except (discord.Forbidden, discord.HTTPException):
                    pass

                try:
                    new_activities = [a for a in message.author.activities if not isinstance(a, discord.CustomActivity)]
                    await message.author.edit(activities=new_activities)
                except Exception:
                    pass

                if not is_any_cmd:
                    try:
                        away = humanize_seconds(time.time() - data.get("since", time.time()))
                        embed = discord.Embed(
                            title="👋  Welcome Back! | بەخێربووتەوە!",
                            color=discord.Color.from_rgb(87, 242, 135),
                        )
                        embed.set_author(name=message.author.display_name, icon_url=message.author.display_avatar.url)
                        embed.add_field(name="⏱️ You were away for | دوور بوویت بۆ ماوەی", value=f"**{away}**", inline=True)
                        if data.get("reason") and data["reason"] != "AFK":
                            embed.add_field(name="📝 Your reason was | هۆکارەکەت بوو", value=f"*{data['reason']}*", inline=True)
                        if data.get("image_url"):
                            embed.set_thumbnail(url=data["image_url"])
                        embed.set_footer(text="Glad to have you back! | خۆشحاڵین کە گەڕایتەوە!")
                        await message.channel.send(embed=embed)
                    except discord.Forbidden:
                        pass

        # --- COOLER AFK SYSTEM: PINGING AN AFK USER ---
        if message.mentions:
            mentioned_msgs = []
            raw_mentions = re.findall(r'<@!?(\d+)>', message.content)

            for u in message.mentions:
                k = (message.guild.id, u.id)
                if k in afk_users and u.id != message.author.id and str(u.id) in raw_mentions:
                    info = afk_users[k]
                    away = humanize_seconds(time.time() - info.get("since", time.time()))

                    _afk_since_ts = int(info.get("since", time.time()))
                    ping_embed = discord.Embed(
                        title=f"{u.display_name} نام بەکارهێنەرە AFK ـە",
                        description=f"{u.mention} لە دۆخی AFK دایە.",
                        color=0x2B2D31,
                        timestamp=datetime.datetime.utcnow(),
                    )
                    ping_embed.add_field(
                        name="هۆکار",
                        value=f"{info['reason']}",
                        inline=False
                    )
                    ping_embed.add_field(
                        name="بێش چاتد",
                        value=f"<t:{_afk_since_ts}:F>",
                        inline=True
                    )
                    ping_embed.add_field(
                        name="لە کاتیاوه",
                        value=f"<t:{_afk_since_ts}:R>",
                        inline=True
                    )
                    ping_embed.set_thumbnail(url=u.display_avatar.url)
                    mentioned_msgs.append(ping_embed)

            for embed in mentioned_msgs:
                try:
                    await message.channel.send(embed=embed)
                except discord.Forbidden:
                    pass

    # --- WORD FILTER ---
    if "shit" in message.content.lower():
        try:
            await message.delete()
            await message.channel.send(f"{message.author.mention} - don't use that word! | ئەو وشەیە مەبەکارهێنە!")
        except discord.Forbidden:
            pass
        return

    # --- MINI-GAMES INTERCEPTS ---
    if message.channel.id in number_games and message.content.strip().isdigit():
        game = number_games[message.channel.id]
        guess_val = int(message.content.strip())
        game["tries"] += 1
        if guess_val < game["number"]:
            await message.channel.send("📈 Higher! | بەرزتر!")
        elif guess_val > game["number"]:
            await message.channel.send("📉 Lower! | نزمتر!")
        else:
            await message.channel.send(
                f"🎉 {message.author.mention} got it in **{game['tries']}** tries! The number was **{game['number']}**.\n"
                f"🎉 {message.author.mention} بەدەستی هێنا لە **{game['tries']}** هەوڵدا! ژمارەکە **{game['number']}** بوو."
            )
            number_games.pop(message.channel.id, None)
        return

    if message.channel.id in lucky_games and message.content.strip().isdigit():
        game = lucky_games[message.channel.id]
        guess_val = int(message.content.strip())
        game["last_activity"] = time.time()
        game["has_guesses"] = True
        game["guesses"] = game.get("guesses", 0) + 1
        if guess_val < 1 or guess_val > 100:
            await message.channel.send("Please pick a number between 1-100 / تکایە ژمارەیەک لەنێوان ١-١٠٠ هەڵبژێرە.")
        elif guess_val == game["number"]:
            task = game.get("task")
            if task:
                task.cancel()
            guesses_taken = game["guesses"]
            guild_id = game.get("guild_id")
            lucky_games.pop(message.channel.id, None)
            if guild_id:
                conn = get_db()
                conn.execute(
                    "INSERT INTO lucky_leaderboard (guild_id, user_id, wins, total_guesses, best_guesses) "
                    "VALUES (?, ?, 1, ?, ?) "
                    "ON CONFLICT(guild_id, user_id) DO UPDATE SET "
                    "wins = wins + 1, "
                    "total_guesses = total_guesses + excluded.total_guesses, "
                    "best_guesses = CASE WHEN best_guesses = 0 OR excluded.best_guesses < best_guesses "
                    "THEN excluded.best_guesses ELSE best_guesses END",
                    (guild_id, message.author.id, guesses_taken, guesses_taken)
                )
                conn.commit()
                conn.close()
            win_embed = discord.Embed(
                title="🎉 Correct! / دروستە!",
                description=(
                    f"**English:** {message.author.mention} got it in **{guesses_taken}** guess{'es' if guesses_taken != 1 else ''}! "
                    f"The number was **{game['number']}**.\n\n"
                    f"**کوردی:** {message.author.mention} لە **{guesses_taken}** حەزردا بەدەستی هێنا! "
                    f"ژمارەکە **{game['number']}** بوو."
                ),
                color=discord.Color.green()
            )
            win_embed.set_footer(text="Type $luckylb to see the leaderboard | $luckylb بنووسە بۆ بینینی لیستی باشترینان")
            await message.channel.send(embed=win_embed)
        elif guess_val < game["number"]:
            await message.channel.send("📈 Higher! | بەرزتر!")
        else:
            await message.channel.send("📉 Lower! | نزمتر!")
        return

    if message.channel.id in tf_games and not message.content.startswith('!'):
        game = tf_games[message.channel.id]
        ans = message.content.strip().lower()
        accepted_true  = {"راست", "true", "t", "ڕاست"}
        accepted_false = {"چەوت", "false", "f", "چه‌وت"}
        user_pick = None
        if ans in accepted_true:
            user_pick = True
        elif ans in accepted_false:
            user_pick = False
        if user_pick is not None:
            task = game.get("task")
            if task:
                task.cancel()
            tf_games.pop(message.channel.id, None)
            is_correct = (user_pick == game["answer"])
            if is_correct:
                result_embed = discord.Embed(
                    title="🎉 وەڵامەکە راست بوو! / Correct!",
                    description=(
                        f"دەستخۆش {message.author.mention}! وەڵامی دروستت دا! 🏆\n"
                        f"Congrats {message.author.mention}! That was correct! 🏆\n\n"
                        f"✅ وەڵامی دروست: **{'راست ✅' if game['answer'] else 'چەوت ❌'}**\n"
                        f"✅ Correct answer: **{'TRUE ✅' if game['answer'] else 'FALSE ❌'}**"
                    ),
                    color=discord.Color.green()
                )
            else:
                result_embed = discord.Embed(
                    title="❌ وەڵامەکە هەڵە بوو! / Wrong!",
                    description=(
                        f"ببورە {message.author.mention}! وەڵامەکەت هەڵە بوو! 😔\n"
                        f"Sorry {message.author.mention}! That was wrong! 😔\n\n"
                        f"✅ وەڵامی دروست: **{'راست ✅' if game['answer'] else 'چەوت ❌'}**\n"
                        f"✅ Correct answer: **{'TRUE ✅' if game['answer'] else 'FALSE ❌'}**"
                    ),
                    color=discord.Color.red()
                )
            result_embed.add_field(
                name="📝 دوای جووابەکە / The Statement",
                value=f"*{game['statement_ku']}*\n*{game['statement_en']}*",
                inline=False
            )
            await message.channel.send(embed=result_embed)
        return

    if message.channel.id in active_quizzes and not message.content.startswith('!'):
        aq = active_quizzes[message.channel.id]
        user_ans = message.content.strip().lower()
        correct  = aq["answer"].lower()
        alts     = [a.lower() for a in aq.get("alternates", [])]
        if user_ans == correct or user_ans in alts:
            task = aq.get("task")
            if task:
                task.cancel()
            active_quizzes.pop(message.channel.id, None)
            win_embed = discord.Embed(
                title="🎉 وەڵامی دروست! / Correct Answer!",
                description=(
                    f"{message.author.mention} **وەڵامی دروستت دا! باشکاری! 🏆**\n"
                    f"{message.author.mention} **Correct answer! Well done! 🏆**\n\n"
                    f"✅ وەڵامەکە: **{aq['answer']}**\n"
                    f"✅ Answer: **{aq['answer']}**"
                ),
                color=discord.Color.green()
            )
            await message.channel.send(embed=win_embed)
        return

    if message.channel.id in anime_quizzes and not message.content.startswith('!'):
        quiz = anime_quizzes[message.channel.id]
        guess = message.content.strip().lower()
        answer = quiz["name"].lower()
        # Accept if guess contains the answer or vice versa (handles partial matches)
        if guess == answer or answer in guess or guess in answer:
            task = quiz.get("task")
            if task:
                task.cancel()
            anime_quizzes.pop(message.channel.id, None)
            win_embed = discord.Embed(
                title="🎉 وەڵامەکە راست بوو! / Correct Answer!",
                description=(
                    f"دەستخۆش {message.author.mention} 🎊\n"
                    f"ئەوە کارەکتەری **{quiz['name']}** ییە!\n\n"
                    f"**Congrats {message.author.mention}!**\n"
                    f"That's **{quiz['name']}**!\n\n"
                    f"💰 ٥ خاڵ جووچە سەر هەژمارەکەت لە داو سیستەمی خاڵەکان.\n"
                    f"💰 5 points added to your account in the points system."
                ),
                color=discord.Color.green()
            )
            win_embed.set_thumbnail(url=quiz["image_url"])
            await message.channel.send(embed=win_embed)
        return

    if message.channel.id in hangman_games and len(message.content.strip()) == 1 and message.content.strip().isalpha():
        game = hangman_games[message.channel.id]
        letter = message.content.strip().lower()
        if letter in game["guessed"] or letter in game["wrong"]:
            await message.channel.send(f"`{letter}` was already guessed. | `{letter}` پێشتر حەزری کرابوو.")
        elif letter in game["word"]:
            game["guessed"].add(letter)
            if all(c in game["guessed"] for c in game["word"]):
                await message.channel.send(
                    f"🎉 {message.author.mention} solved it! The word was **{game['word']}**.\n"
                    f"🎉 {message.author.mention} چارەسەری کرد! وشەکە **{game['word']}** بوو."
                )
                hangman_games.pop(message.channel.id, None)
            else:
                await message.channel.send(render_hangman(game))
        else:
            game["wrong"].add(letter)
            if len(game["wrong"]) >= 6:
                await message.channel.send(
                    f"💀 Game over! The word was **{game['word']}**.\n{HANGMAN_STAGES[-1]}\n"
                    f"💀 یاری تەواو بوو! وشەکە **{game['word']}** بوو."
                )
                hangman_games.pop(message.channel.id, None)
            else:
                await message.channel.send(render_hangman(game))
        return

    # --- GREENTEA GAME AUTO-GUESS ---
    if message.channel.id in greentea_games and not message.content.startswith('!'):
        content = message.content.strip().lower()
        if content.isalpha():
            session = greentea_games[message.channel.id]
            cid = message.channel.id
            if len(content) > 1:
                if content == session["word"]:
                    session["revealed"] = list(session["word"])
                    uid = message.author.id
                    pts = 5 + session["lives"] * 2
                    session["scores"][uid] = session["scores"].get(uid, 0) + pts
                    del greentea_games[cid]
                    if session["auto_end_task"]:
                        session["auto_end_task"].cancel()
                    await message.channel.send(embed=_gt_build_end_embed(session, won=True))
                else:
                    session["lives"] -= 1
                    session["wrong_letters"].add(f"[{content[:6]}]")
                    if session["lives"] <= 0:
                        del greentea_games[cid]
                        if session["auto_end_task"]:
                            session["auto_end_task"].cancel()
                        await message.channel.send(embed=_gt_build_end_embed(session, won=False))
                    else:
                        e = discord.Embed(
                            title=f"{_GT_WARN}  Wrong Word!  |  وشەی هەڵە!",
                            description=f"**EN:** `{content}` is not the word. -1 life.\n**KU:** `{content}` وشەکە نییە.",
                            color=discord.Color.red()
                        )
                        e.add_field(name=f"{_GT_LETTER} Current", value="```\n" + " ".join(session["revealed"]).upper() + "\n```")
                        await message.channel.send(embed=e)
                return
            letter = content
            if letter in session["guessed_letters"] or letter in session["wrong_letters"]:
                await message.channel.send(f"{_GT_WARN} Already guessed `{letter.upper()}`!", delete_after=4)
                return
            session["guessed_letters"].add(letter)
            session["last_guess_time"] = time.time()
            word = session["word"]
            if letter in word:
                positions = [i for i, ch in enumerate(word) if ch == letter]
                for i in positions:
                    session["revealed"][i] = letter
                uid = message.author.id
                pts = len(positions) * 10
                session["scores"][uid] = session["scores"].get(uid, 0) + pts
                session["guessers"].add(uid)
                if session["auto_end_task"]:
                    session["auto_end_task"].cancel()
                delay = 180 if session["mode"] == "normal" else (90 if session["mode"] == "hard" else 30)
                session["auto_end_task"] = asyncio.create_task(_gt_auto_end_game(cid, delay))
                if "_" not in session["revealed"]:
                    session["scores"][uid] = session["scores"].get(uid, 0) + 20
                    del greentea_games[cid]
                    session["auto_end_task"].cancel()
                    await message.channel.send(embed=_gt_build_end_embed(session, won=True))
                else:
                    e = discord.Embed(
                        title=f"{_GT_WIN} Letter Found! — `{letter.upper()}`  |  پیتەکە دۆزرایەوە!",
                        color=discord.Color.gold()
                    )
                    letter_word = "letter" if len(positions) == 1 else "letters"
                    e.title = f"{_GT_WIN} You got **{len(positions)} {letter_word}** right! — `{letter.upper()}`"
                    e.description = f"🍵 پیتی `{letter.upper()}` **{len(positions)}** جار دۆزرایەوە!"
                    e.add_field(name=f"{_GT_LETTER} Revealed  |  ئاشکراکراو", value="```\n" + " ".join(session["revealed"]).upper() + "\n```", inline=False)
                    e.add_field(name=f"{_GT_ZAP} Points  |  خاڵ", value=f"+{pts} pts  —  {_GT_STAR * min(pts // 10, 5)}", inline=True)
                    await message.channel.send(embed=e)
            else:
                session["wrong_letters"].add(letter)
                session["lives"] -= 1
                if session["lives"] <= 0:
                    del greentea_games[cid]
                    if session["auto_end_task"]:
                        session["auto_end_task"].cancel()
                    await message.channel.send(embed=_gt_build_end_embed(session, won=False))
                else:
                    e = discord.Embed(
                        title=f"{_GT_WARN}  Wrong Letter!  |  پیتی هەڵە!",
                        description=f"**EN:** `{letter.upper()}` not in word. -1 life. `{session['lives']}` left.\n**KU:** `{letter.upper()}` نییە. ژیانی ماوە: `{session['lives']}`",
                        color=discord.Color.dark_red()
                    )
                    e.add_field(name=f"{_GT_LETTER} Current", value="```\n" + " ".join(session["revealed"]).upper() + "\n```")
                    hearts_full = "🟩" * session["lives"]
                    hearts_empty = "🟥" * (session["max_lives"] - session["lives"])
                    e.add_field(name="❤️ Lives", value=hearts_full + hearts_empty, inline=False)
                    await message.channel.send(embed=e)
            return

    # --- PASSIVE XP ---
    if message.guild is not None and not message.content.startswith(bot.command_prefix):
        key = (message.guild.id, message.author.id)
        now = time.time()
        last = message_cooldowns.get(key, 0)
        if now - last >= MESSAGE_XP_COOLDOWN:
            gained = random.randint(MESSAGE_XP_MIN, MESSAGE_XP_MAX)
            entry = get_user_entry(message.guild.id, message.author.id)
            before_total = total_xp(entry)
            before_level = level_from_xp(before_total)
            add_xp(message.guild.id, message.author.id, gained, "message_xp")
            after_level = level_from_xp(total_xp(entry))
            message_cooldowns[key] = now
            if after_level > before_level:
                await announce_level_up(message.author, message.channel, after_level, "message")

    # --- NO-PREFIX REKLAM TRIGGER ---
    if message.guild is not None and message.content.strip().lower() == "reklam":
        _rk_key = (message.guild.id, message.author.id)
        _rk_last = reklam_cooldowns.get(_rk_key, 0)
        if time.time() - _rk_last < 30:
            _rk_left = int(30 - (time.time() - _rk_last))
            await message.reply(
                f"⏳ {message.author.mention} تکایە چاوەڕێ بە! | Please wait **{_rk_left}s** before requesting again.",
                mention_author=False,
                delete_after=8,
            )
            return
        reklam_cooldowns[_rk_key] = time.time()
        cfg = get_reklam_settings(message.guild.id)
        if cfg:
            ch = message.guild.get_channel(cfg["channel_id"])
            role = message.guild.get_role(cfg["role_id"])
            if ch:
                ping = role.mention if role else ""
                custom_text = cfg.get("text", "").strip()

                # Bottom text: use custom if set, otherwise the default
                if custom_text:
                    bottom = custom_text.replace("{user}", message.author.mention)
                else:
                    bottom = (
                        "تکایە بچنە کەناڵەکەی و وەڵامی بدەنەوە.\n"
                        "Please go to their channel and help them."
                    )

                notify = discord.Embed(
                    color=0xF59E0B,
                    title="📣 داوای ریکلامی نوێ | New Reklam Request",
                    description=(
                        f"**کەسی داواکار | Requester:** {message.author.mention}\n"
                        f"**کەناڵ | Channel:** {message.channel.mention}\n\n"
                        f"{bottom}\n\n"
                        f"**کات | Time:** <t:{int(message.created_at.timestamp())}:R>"
                    ),
                    timestamp=datetime.datetime.utcnow(),
                )
                notify.set_thumbnail(url=message.author.display_avatar.url)
                notify.set_footer(text=message.guild.name)
                try:
                    await ch.send(content=ping if ping else None, embed=notify)
                except (discord.Forbidden, discord.HTTPException):
                    pass
        return

    # --- NO-PREFIX TAG TRIGGER ---
    # Triggers on:  <tagname>          (just the name alone)
    #           or: tag <tagname>      (legacy prefix form)
    if message.guild is not None:
        _raw_msg = message.content.strip()
        _raw_lower = _raw_msg.lower()
        # Resolve the tag name: strip "tag " prefix if present, else use the
        # whole message as the tag name (so typing "tag2" fires tag "tag2").
        if _raw_lower.startswith("tag "):
            _tname = _raw_msg[4:].strip().lower()
        else:
            _tname = _raw_lower
        _tentry = tags_data.get(str(message.guild.id), {}).get(_tname)
        if _tentry:
            try:
                await message.delete()
            except (discord.Forbidden, discord.HTTPException, discord.NotFound):
                pass
            try:
                await message.channel.send(_tentry["response"])
            except (discord.Forbidden, discord.HTTPException):
                pass
            return

    # --- NO-PREFIX LINK TRIGGER ---
    if message.guild is not None and message.content.strip().lower() == "link":
        with get_db() as _lk_conn:
            _lk_row = _lk_conn.execute(
                "SELECT label, url FROM link_settings WHERE guild_id=?", (message.guild.id,)
            ).fetchone()
        if _lk_row:
            _lk_url = _lk_row['url']
            _lk_content = f"<#{_lk_url}>" if _lk_url.isdigit() else _lk_url
            try:
                await message.channel.send(_lk_content)
            except (discord.Forbidden, discord.HTTPException):
                pass
        return

    # --- PROCESS PREFIX COMMANDS (!command) ---
    await bot.process_commands(message)

@bot.event
async def on_voice_state_update(member, before, after):
    if member.bot:
        return
    key = (member.guild.id, member.id)
    if before.channel is None and after.channel is not None:
        voice_sessions[key] = time.time()
    elif before.channel is not None and after.channel is None:
        voice_sessions.pop(key, None)

# ═══════════════════════ SERVER LOG EVENTS ═══════════════════════

@bot.event
async def on_member_remove(member):
    gid = str(member.guild.id)
    if not log_channels.get(gid):
        return
    e = discord.Embed(
        color=0xED4245,
        title="🚪 ئەندام چووەوە | Member Left",
        timestamp=datetime.datetime.utcnow(),
    )
    e.set_thumbnail(url=member.display_avatar.url)
    e.add_field(name="👤 ئەندام | Member", value=f"{member} (`{member.id}`)", inline=True)
    e.add_field(name="📅 بەشداریکردن | Joined", value=f"<t:{int(member.joined_at.timestamp())}:R>" if member.joined_at else "Unknown", inline=True)
    e.add_field(name="👥 ژمارەی ئەندامان | Members", value=f"{member.guild.member_count:,}", inline=True)
    roles = [r.mention for r in member.roles if r.name != "@everyone"]
    if roles:
        e.add_field(name="🎭 رۆڵەکان | Roles", value=" ".join(roles[:10]), inline=False)
    e.set_footer(text=f"ID: {member.id}")
    await _send_log(member.guild, e)

@bot.event
async def on_message_delete(message):
    if message.author.bot or not message.guild:
        return
    gid = str(message.guild.id)
    if not log_channels.get(gid):
        return
    e = discord.Embed(
        color=0xFEE75C,
        title="🗑️ پەیام سڕایەوە | Message Deleted",
        timestamp=datetime.datetime.utcnow(),
    )
    e.set_author(name=message.author.display_name, icon_url=message.author.display_avatar.url)
    e.add_field(name="👤 نووسەر | Author", value=f"{message.author.mention} (`{message.author.id}`)", inline=True)
    e.add_field(name="📌 چانێل | Channel", value=message.channel.mention, inline=True)
    content = message.content or "*[Embed / Attachment]*"
    if len(content) > 1000:
        content = content[:997] + "..."
    e.add_field(name="📝 پەیام | Content", value=content, inline=False)
    e.set_footer(text=f"Message ID: {message.id}")
    await _send_log(message.guild, e)

@bot.event
async def on_message_edit(before, after):
    if before.author.bot or not before.guild:
        return
    if before.content == after.content:
        return
    gid = str(before.guild.id)
    if not log_channels.get(gid):
        return
    e = discord.Embed(
        color=0x5865F2,
        title="✏️ پەیام دەستکاریکرا | Message Edited",
        timestamp=datetime.datetime.utcnow(),
        url=after.jump_url,
    )
    e.set_author(name=before.author.display_name, icon_url=before.author.display_avatar.url)
    e.add_field(name="👤 نووسەر | Author", value=f"{before.author.mention}", inline=True)
    e.add_field(name="📌 چانێل | Channel", value=before.channel.mention, inline=True)
    old_c = before.content[:500] + "..." if len(before.content) > 500 else before.content or "—"
    new_c = after.content[:500]  + "..." if len(after.content)  > 500 else after.content  or "—"
    e.add_field(name="🔴 پێشتر | Before", value=old_c, inline=False)
    e.add_field(name="🟢 دواتر | After",  value=new_c, inline=False)
    e.set_footer(text=f"Message ID: {before.id}")
    await _send_log(before.guild, e)

@bot.event
async def on_member_ban(guild, user):
    if not log_channels.get(str(guild.id)):
        return
    e = discord.Embed(
        color=0xED4245,
        title="🔨 ئەندام بانکرا | Member Banned",
        timestamp=datetime.datetime.utcnow(),
    )
    e.set_thumbnail(url=user.display_avatar.url)
    e.add_field(name="👤 بەکارهێنەر | User", value=f"{user} (`{user.id}`)", inline=True)
    try:
        entry = await guild.audit_logs(action=discord.AuditLogAction.ban, limit=1).__anext__()
        if entry.target.id == user.id:
            e.add_field(name="👮 کردووی | Banned by", value=entry.user.mention, inline=True)
            e.add_field(name="📋 هۆکار | Reason", value=entry.reason or "No reason", inline=True)
    except Exception:
        pass
    e.set_footer(text=f"User ID: {user.id}")
    await _send_log(guild, e)

@bot.event
async def on_member_unban(guild, user):
    if not log_channels.get(str(guild.id)):
        return
    e = discord.Embed(
        color=0x57F287,
        title="✅ بانی ئەندام لابرا | Member Unbanned",
        timestamp=datetime.datetime.utcnow(),
    )
    e.set_thumbnail(url=user.display_avatar.url)
    e.add_field(name="👤 بەکارهێنەر | User", value=f"{user} (`{user.id}`)", inline=True)
    try:
        entry = await guild.audit_logs(action=discord.AuditLogAction.unban, limit=1).__anext__()
        if entry.target.id == user.id:
            e.add_field(name="👮 کردووی | Unbanned by", value=entry.user.mention, inline=True)
    except Exception:
        pass
    e.set_footer(text=f"User ID: {user.id}")
    await _send_log(guild, e)

@bot.event
async def on_member_update(before, after):
    gid = str(after.guild.id)

    # ── Boost detection ──────────────────────────────────
    was_boosting = before.premium_since is not None
    now_boosting = after.premium_since  is not None
    if not was_boosting and now_boosting:
        cid = boost_channels.get(gid)
        if cid:
            ch = after.guild.get_channel(int(cid))
            if ch:
                embed = discord.Embed(
                    color=0xFF73FA,
                    title="🚀 سووپاس بۆ بووستەکەت! | Thanks for Boosting!",
                    description=(
                        f"## 💎 {after.mention}\n"
                        f"**{after.display_name}** سێرڤەرەکەمانی بووستی کردووە! 🎉\n"
                        f"**{after.display_name}** just boosted our server! 🎉\n\n"
                        f"ئێستا ئێمە **{after.guild.premium_subscription_count}** بووستمان هەیە "
                        f"و لەسەر ئاستی **Level {after.guild.premium_tier}** ین! ✨\n"
                        f"We now have **{after.guild.premium_subscription_count}** boosts "
                        f"and are at **Level {after.guild.premium_tier}**! ✨"
                    ),
                    timestamp=datetime.datetime.utcnow(),
                )
                embed.set_thumbnail(url=after.display_avatar.url)
                if after.guild.icon:
                    embed.set_author(
                        name=after.guild.name,
                        icon_url=after.guild.icon.url,
                    )
                embed.set_footer(
                    text=f"💜 {after.guild.name} appreciates your support!",
                    icon_url=after.guild.icon.url if after.guild.icon else None,
                )
                try:
                    await ch.send(embed=embed)
                except (discord.Forbidden, discord.HTTPException):
                    pass

    if not log_channels.get(gid):
        return
    # Nickname change
    if before.nick != after.nick:
        e = discord.Embed(
            color=0xEB459E,
            title="📝 ناوی نمایشی گۆڕدرا | Nickname Changed",
            timestamp=datetime.datetime.utcnow(),
        )
        e.set_author(name=after.display_name, icon_url=after.display_avatar.url)
        e.add_field(name="👤 ئەندام | Member", value=after.mention, inline=True)
        e.add_field(name="🔴 پێشتر | Before", value=before.nick or "*None*", inline=True)
        e.add_field(name="🟢 دواتر | After",  value=after.nick  or "*None*", inline=True)
        e.set_footer(text=f"ID: {after.id}")
        await _send_log(after.guild, e)
    # Role change
    added   = [r for r in after.roles  if r not in before.roles]
    removed = [r for r in before.roles if r not in after.roles]
    if added or removed:
        e = discord.Embed(
            color=0x57F287 if added else 0xED4245,
            title="🎭 رۆڵ گۆڕدرا | Roles Updated",
            timestamp=datetime.datetime.utcnow(),
        )
        e.set_author(name=after.display_name, icon_url=after.display_avatar.url)
        e.add_field(name="👤 ئەندام | Member", value=after.mention, inline=False)
        if added:
            e.add_field(name="➕ زیادکراو | Added", value=" ".join(r.mention for r in added), inline=True)
        if removed:
            e.add_field(name="➖ لابراو | Removed", value=" ".join(r.mention for r in removed), inline=True)
        e.set_footer(text=f"ID: {after.id}")
        await _send_log(after.guild, e)

@bot.event
async def on_guild_channel_create(channel):
    gid = str(channel.guild.id)
    if not log_channels.get(gid):
        return
    e = discord.Embed(
        color=0x57F287,
        title="📁 چانێلی نوێ دروستکرا | Channel Created",
        timestamp=datetime.datetime.utcnow(),
    )
    e.add_field(name="📌 ناو | Name", value=channel.mention, inline=True)
    e.add_field(name="🔖 جۆر | Type", value=str(channel.type).capitalize(), inline=True)
    e.set_footer(text=f"Channel ID: {channel.id}")
    await _send_log(channel.guild, e)

@bot.event
async def on_guild_channel_delete(channel):
    gid = str(channel.guild.id)
    if not log_channels.get(gid):
        return
    e = discord.Embed(
        color=0xED4245,
        title="🗑️ چانێل سڕایەوە | Channel Deleted",
        timestamp=datetime.datetime.utcnow(),
    )
    e.add_field(name="📌 ناو | Name", value=f"#{channel.name}", inline=True)
    e.add_field(name="🔖 جۆر | Type", value=str(channel.type).capitalize(), inline=True)
    e.set_footer(text=f"Channel ID: {channel.id}")
    await _send_log(channel.guild, e)

# --- BACKGROUND TASKS ---

@tasks.loop(minutes=1)
async def voice_xp_tick():
    now = time.time()
    for guild in bot.guilds:
        for vc in guild.voice_channels:
            human_members = [m for m in vc.members if not m.bot]
            if len(human_members) < 2:
                continue
            for member in human_members:
                state = member.voice
                if state is None:
                    continue
                if state.self_mute or state.self_deaf or state.mute or state.deaf:
                    continue
                key = (guild.id, member.id)
                start = voice_sessions.get(key, now)
                elapsed = now - start
                if elapsed >= 60:
                    minutes = int(elapsed // 60)
                    entry = get_user_entry(guild.id, member.id)
                    before_lvl = level_from_xp(total_xp(entry))
                    add_xp(guild.id, member.id, minutes * VOICE_XP_PER_MINUTE, "voice_xp")
                    after_lvl = level_from_xp(total_xp(entry))
                    voice_sessions[key] = start + minutes * 60
                    if after_lvl > before_lvl:
                        await announce_level_up(member, vc, after_lvl, "voice")

@tasks.loop(minutes=2)
async def autosave():
    save_xp()
    save_warnings()
    save_econ()
    save_level_channels()
    save_welcome_channels()
    save_ticket_settings()
    save_open_tickets()
    save_afk()

# --- STAFF DAILY TASK ---

async def _send_staff_daily(guild, channel, pings: str):
    """Send staff daily ping, deleting the previous one for this guild first."""
    gid = str(guild.id)
    old_mid = staff_daily_last_msg.get(gid)
    if old_mid:
        try:
            old_msg = await channel.fetch_message(int(old_mid))
            await old_msg.delete()
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            pass
        staff_daily_last_msg.pop(gid, None)

    embed = discord.Embed(
        color=0xF59E0B,
        title="📢 دەیلی ستاف",
        description=(
            "خۆشەویستان دەیلیەکانتان بکەن چات و ڤۆیسەگشتیەکان پڕ بکەن لە قەسی جوان\n"
            "دەستی هەمولایەک خۆش بێت"
        ),
    )
    embed.set_footer(text=f"{guild.name} · ستاف تیم — کاتژمێر ٩ ئێوارە")
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    try:
        msg = await channel.send(
            content=pings,
            embed=embed,
            allowed_mentions=discord.AllowedMentions(roles=True),
        )
        staff_daily_last_msg[gid] = msg.id
        save_staff_daily_last_msg()
    except (discord.Forbidden, discord.HTTPException):
        pass

@tasks.loop(time=datetime.time(hour=21, minute=0, second=0, tzinfo=datetime.timezone.utc))
async def staff_daily_task():
    for guild in bot.guilds:
        gid = str(guild.id)
        cid = staff_daily_channels.get(gid)
        if not cid:
            continue
        channel = guild.get_channel(int(cid))
        if not channel:
            continue
        role_ids = staff_daily_roles_map.get(gid, [])
        pings = " ".join(f"<@&{rid}>" for rid in role_ids) if role_ids else ""
        if not pings:
            continue
        await _send_staff_daily(guild, channel, pings)

# --- ISLAM / FRIDAY REMINDER TASK ---

async def _send_islam_ping(guild, channel, ping: str):
    """Send the Islam/Friday reminder ping, deleting previous one first."""
    gid = str(guild.id)
    old_mid = islam_last_msg_map.get(gid)
    if old_mid:
        try:
            old_msg = await channel.fetch_message(int(old_mid))
            await old_msg.delete()
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            pass
        islam_last_msg_map.pop(gid, None)

    cfg = islam_settings_map.get(gid, {})
    text_en = cfg.get("text_en", "").strip()
    text_ku = cfg.get("text_ku", "").strip()

    if text_ku and text_en:
        description = f"{text_ku}\n\n──────────────────────\n\n{text_en}"
    elif text_ku:
        description = text_ku
    elif text_en:
        description = text_en
    else:
        description = (
            "🕌 **خوای گەورە رۆژی جومعە مبارەک بکات!**\n"
            "نوێژی جومعەتان لە بیر نەچێت — ئەمرۆ شەوی پێنجشەممەیە.\n\n"
            "🕌 **Jumu'ah Mubarak!**\n"
            "Don't forget Friday prayers — today is Thursday night."
        )

    embed = discord.Embed(
        color=0x2ECC71,
        title="🕌 جومعە مبارەک | Jumu'ah Mubarak",
        description=description,
    )
    embed.set_footer(text=f"{guild.name} · شەوی پێنجشەممە — Thursday Night")
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    try:
        msg = await channel.send(
            content=ping,
            embed=embed,
            allowed_mentions=discord.AllowedMentions(roles=True),
        )
        save_islam_last_msg(guild.id, msg.id)
    except (discord.Forbidden, discord.HTTPException):
        pass


# Iraq time = UTC+3 → 9 PM Iraq = 18:00 UTC. Runs every Thursday (weekday=3).
@tasks.loop(time=datetime.time(hour=18, minute=0, second=0, tzinfo=datetime.timezone.utc))
async def islam_thursday_task():
    # Only fire on Thursday (weekday 3 = Thursday in Python)
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    if now_utc.weekday() != 3:
        return
    for guild in bot.guilds:
        gid = str(guild.id)
        cfg = islam_settings_map.get(gid, {})
        cid = cfg.get("channel_id")
        rid = cfg.get("role_id")
        if not cid or not rid:
            continue
        channel = guild.get_channel(int(cid))
        if not channel:
            continue
        ping = f"<@&{rid}>"
        await _send_islam_ping(guild, channel, ping)


# --- BASIC COMMANDS ---

@bot.command()
async def hello(ctx):
    await ctx.send(f"Hello {ctx.author.mention}! | سڵاو {ctx.author.mention}!")

@bot.command()
async def assign(ctx):
    role = discord.utils.get(ctx.guild.roles, name=secret_role)
    if role:
        await ctx.author.add_roles(role)
        await ctx.send(f"{ctx.author.mention} is now assigned to {secret_role} | ئێستا {ctx.author.mention} بەرپرسی {secret_role} یە")
    else:
        await ctx.send("Role doesn't exist | ئەم رۆڵە بوونی نییە")

@bot.command()
async def remove(ctx):
    role = discord.utils.get(ctx.guild.roles, name=secret_role)
    if role:
        await ctx.author.remove_roles(role)
        await ctx.send(f"{ctx.author.mention} has had the {secret_role} removed | رۆڵی {secret_role} لە {ctx.author.mention} لاوە")
    else:
        await ctx.send("Role doesn't exist | ئەم رۆڵە بوونی نییە")

@bot.command()
async def dm(ctx, *, msg):
    await ctx.author.send(f"You said: {msg} | تۆ گوتت: {msg}")

@bot.command()
async def reply(ctx):
    await ctx.reply("This is a reply to your message! | ئەمە وەڵامێکە بۆ پەیامەکەت!")

@bot.command()
async def poll(ctx, *, question):
    embed = discord.Embed(title="New Poll | دەنگدانی نوێ", description=question)
    poll_message = await ctx.send(embed=embed)
    await poll_message.add_reaction("👍")
    await poll_message.add_reaction("👎")

@bot.command()
async def serverinfo(ctx):
    guild = ctx.guild
    if guild is None:
        await ctx.send("This command can only be used in a server. | ئەم فەرمانە تەنها لە سێرڤەر دەکرێت بەکارهێنرێت.")
        return

    text_ch = len(guild.text_channels)
    voice_ch = len(guild.voice_channels)
    bots = sum(1 for m in guild.members if m.bot)
    humans = (guild.member_count or 0) - bots
    online = sum(1 for m in guild.members if m.status != discord.Status.offline and not m.bot)
    boost_level = guild.premium_tier
    boost_count = guild.premium_subscription_count or 0

    embed = discord.Embed(
        title=f"🏰 {guild.name}",
        description=f"**ID:** `{guild.id}`",
        color=discord.Color.from_rgb(88, 101, 242),
        timestamp=datetime.datetime.utcnow(),
    )
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    if guild.banner:
        embed.set_image(url=guild.banner.with_format("png").url)
    embed.add_field(name="👑 Owner | خاوەن", value=f"<@{guild.owner_id}>", inline=True)
    embed.add_field(name="📅 Created | دروستکراوە", value=f"<t:{int(guild.created_at.timestamp())}:D>", inline=True)
    embed.add_field(name="🌍 Locale | زمان", value=str(guild.preferred_locale), inline=True)
    embed.add_field(name="👥 Members | ئەندامان", value=f"👤 {humans:,} humans\n🤖 {bots} bots", inline=True)
    embed.add_field(name="🟢 Online | ئۆنلاین", value=f"`{online:,}`", inline=True)
    embed.add_field(name="🔐 Verification | پشکنین", value=str(guild.verification_level).title(), inline=True)
    embed.add_field(name="💬 Channels | کەناڵەکان", value=f"📝 {text_ch} text\n🔊 {voice_ch} voice\n📁 {len(guild.categories)} categories", inline=True)
    embed.add_field(name="🎭 Roles | رۆڵەکان", value=f"`{len(guild.roles):,}`", inline=True)
    embed.add_field(name="💎 Boosts | بووستەکان", value=f"Level {boost_level} · {boost_count} boosts", inline=True)
    embed.set_footer(text=f"Requested by {ctx.author.display_name}")
    await ctx.send(embed=embed)

@bot.command()
async def userinfo(ctx, member: discord.Member = None):
    member = member or ctx.author
    roles = [r.mention for r in reversed(member.roles) if r.name != "@everyone"]
    top_role = member.top_role if member.top_role.name != "@everyone" else None
    color = top_role.color if top_role and top_role.color.value != 0 else discord.Color.from_rgb(88, 101, 242)
    status_emojis = {
        discord.Status.online: "🟢", discord.Status.idle: "🟡",
        discord.Status.dnd: "🔴", discord.Status.offline: "⚫",
    }
    status_icon = status_emojis.get(member.status, "⚫")
    all_members = sorted(ctx.guild.members, key=lambda m: m.joined_at or datetime.datetime.utcnow())
    join_pos = next((i + 1 for i, m in enumerate(all_members) if m.id == member.id), "?")
    embed = discord.Embed(
        title=f"{status_icon} {member.display_name}",
        description=f"{'🤖 Bot Account | بۆت' if member.bot else ''}\n**Tag:** `{member}`\n**ID:** `{member.id}`",
        color=color,
        timestamp=datetime.datetime.utcnow(),
    )
    if member.display_avatar:
        embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="📅 Joined Server | پەیوەندی بە سێرڤەر", value=f"<t:{int(member.joined_at.timestamp())}:D>" if member.joined_at else "Unknown", inline=True)
    embed.add_field(name="📆 Account Created | ئەکاونت دروستکراوە", value=f"<t:{int(member.created_at.timestamp())}:D>", inline=True)
    embed.add_field(name="📊 Join Position | جێگای پەیوەستبوون", value=f"`#{join_pos}`", inline=True)
    if top_role:
        embed.add_field(name="⭐ Top Role | باڵاترین رۆڵ", value=top_role.mention, inline=True)
    embed.add_field(name="🎮 Status | دۆخ", value=str(member.status).title(), inline=True)
    embed.add_field(name=f"🎭 Roles | رۆڵەکان ({len(roles)})", value=" ".join(roles[:10]) + ("…" if len(roles) > 10 else "") if roles else "None | هیچ", inline=False)
    embed.set_footer(text=f"Requested by {ctx.author.display_name}")
    await ctx.send(embed=embed)

@bot.command()
@commands.has_permissions(manage_messages=True)
async def clear(ctx, amount: int):
    if amount < 1 or amount > 100:
        await ctx.send("Please choose a number between 1 and 100. | تکایە ژمارەیەک لە نێوان ١ و ١٠٠ هەڵبژێرە.")
        return
    deleted = await ctx.channel.purge(limit=amount + 1)
    confirm = await ctx.send(f"Deleted {len(deleted) - 1} message(s). | {len(deleted) - 1} پەیام سڕایەوە.")
    await confirm.delete(delay=3)

@clear.error
async def clear_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("You need the Manage Messages permission to use this. | مووچەی بەڕێوەبردنی پەیامەکان پێویستە.")
    elif isinstance(error, commands.BadArgument) or isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Usage: $clear <number between 1 and 100> | بەکارهێنان: $clear <ژمارە لە نێوان ١ و ١٠٠>")

# --- LEVELING COMMANDS ---

@bot.command()
async def rank(ctx, member: discord.Member = None):
    if ctx.guild is None:
        await ctx.send("This command can only be used in a server. | ئەم فەرمانە تەنها لە سێرڤەر دەکرێت بەکارهێنرێت.")
        return
    member = member or ctx.author
    entry = get_user_entry(ctx.guild.id, member.id)
    msg_xp = entry.get("message_xp", 0)
    voice_xp_val = entry.get("voice_xp", 0)
    total = msg_xp + voice_xp_val
    lvl = level_from_xp(total)
    cur_floor = xp_for_level(lvl)
    next_floor = xp_for_level(lvl + 1)
    progress = total - cur_floor
    needed = next_floor - cur_floor
    pct = (progress / needed * 100) if needed else 0
    bar = make_progress_bar(progress, needed, length=20)

    guild_data = xp_data.get(str(ctx.guild.id), {})
    sorted_users = sorted(
        guild_data.items(),
        key=lambda kv: kv[1].get("message_xp", 0) + kv[1].get("voice_xp", 0),
        reverse=True,
    )
    rank_pos = next((i + 1 for i, (uid, _) in enumerate(sorted_users) if uid == str(member.id)), len(sorted_users) + 1)

    icon = level_icon(lvl)
    color = discord.Color.from_hsv((min(lvl, 50) / 50) * 0.83, 0.90, 1.0)
    embed = discord.Embed(color=color, timestamp=datetime.datetime.utcnow())
    embed.set_author(
        name=f"{member.display_name} — Rank Card | کارتی رتبە",
        icon_url=member.display_avatar.url if member.display_avatar else None
    )
    if member.display_avatar:
        embed.set_thumbnail(url=member.display_avatar.url)
    embed.description = (
        f"## {icon} Level | ئاست  **{lvl}**  ·  🏅 Rank | رتبە  **#{rank_pos}**\n"
        f"```\n{bar}  {pct:.1f}%\n```\n"
        f"**{progress:,}** / **{needed:,}** XP  →  Level | ئاستی **{lvl + 1}**"
    )
    embed.add_field(name="💬 Message XP | پەیام", value=f"```{msg_xp:,}```", inline=True)
    embed.add_field(name="🎙️ Voice XP | دەنگ", value=f"```{voice_xp_val:,}```", inline=True)
    embed.add_field(name="✨ Total XP | کۆی گشتی", value=f"```{total:,}```", inline=True)
    embed.set_footer(text="Keep chatting & chilling in voice! | بەردەوام بە لە پەیام و دەنگدا!")
    await ctx.send(embed=embed)

@bot.command(name="toplevel", aliases=["levels", "topleveler", "topup"])
async def toplevel(ctx):
    if ctx.guild is None:
        await ctx.send("This command can only be used in a server. | ئەم فەرمانە تەنها لە سێرڤەر دەکرێت بەکارهێنرێت.")
        return
    guild_data = xp_data.get(str(ctx.guild.id), {})
    rows = []
    for uid, entry in guild_data.items():
        total = entry.get("message_xp", 0) + entry.get("voice_xp", 0)
        if total <= 0:
            continue
        rows.append((uid, total, level_from_xp(total)))
    rows.sort(key=lambda r: (r[2], r[1]), reverse=True)
    rows = rows[:10]
    if not rows:
        await ctx.send("No XP has been earned in this server yet. | هێشتا هیچ XP لەم سێرڤەرە کەسب نەکراوە.")
        return
    medals = ["🥇", "🥈", "🥉"]
    lines = []
    for i, (uid, total, lvl) in enumerate(rows):
        m = ctx.guild.get_member(int(uid))
        name = m.display_name if m else f"User {uid}"
        cur_floor = xp_for_level(lvl)
        next_floor = xp_for_level(lvl + 1)
        bar = make_progress_bar(total - cur_floor, next_floor - cur_floor, length=12)
        prefix = medals[i] if i < 3 else f"`#{i+1}`"
        icon = level_icon(lvl)
        lines.append(f"{prefix} **{name}** — {icon} Lvl **{lvl}** · `{total:,}` XP\n> `{bar}`")
    embed = discord.Embed(
        title="🏅 Top Level Climbers | باڵاترین ئاستگرتووان",
        description="\n\n".join(lines),
        color=discord.Color.gold(),
        timestamp=datetime.datetime.utcnow(),
    )
    embed.set_footer(text=f"Top 10 of {ctx.guild.name} | بەرزترین ١٠ی {ctx.guild.name}")
    await ctx.send(embed=embed)

@bot.command(name="setlevelchannel", aliases=["levelchannel"])
@commands.has_permissions(manage_guild=True)
async def setlevelchannel(ctx, channel: discord.TextChannel = None):
    if ctx.guild is None:
        await ctx.send("Server only. | تەنها لە سێرڤەر.")
        return
    target = channel or ctx.channel
    level_channels[str(ctx.guild.id)] = target.id
    save_level_channels()
    await ctx.send(f"✅ Level-up announcements will now be sent in {target.mention}. | ئاگاداریەکانی بەرزبوونی ئاست دێنرێن بۆ {target.mention}.")

@setlevelchannel.error
async def setlevelchannel_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ مووچەی Manage Server پێویستە. | You need Manage Server permission.")
    elif isinstance(error, commands.ChannelNotFound):
        await ctx.send("❌ کەناڵ نەدۆزرایەوە. | Channel not found.")


@bot.command(name="removelevelchannel", aliases=["unsetlevelchannel"])
@commands.has_permissions(manage_guild=True)
async def removelevelchannel(ctx):
    if ctx.guild is None:
        await ctx.send("Server only. | تەنها لە سێرڤەر.")
        return
    if str(ctx.guild.id) in level_channels:
        del level_channels[str(ctx.guild.id)]
        save_level_channels()
        await ctx.send("✅ Level-up announcements will fall back to the channel where the level happened. | ئاگاداریەکانی بەرزبوونی ئاست دەگەڕێنەوە بۆ کەناڵی ئەوجا.")
    else:
        await ctx.send("No level channel was set. | هیچ کەناڵی ئاست دانەنرابوو.")

@removelevelchannel.error
async def removelevelchannel_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ مووچەی Manage Server پێویستە. | You need Manage Server permission.")

# ─────────────────────────────────────────────────────────────────────────────
# WELCOME EMBED INTERACTIVE SETUP (modals + view)
# ─────────────────────────────────────────────────────────────────────────────

def _build_welcome_embed(s, member, inviter=None, inv_total=0, test=False):
    """Build the welcome embed from settings dict + member context."""
    title       = apply_welcome_placeholders(s.get("title",        _WES_DEFAULTS["title"]),        member, inviter, inv_total, channel_id=s.get("channel_id",""))
    description = apply_welcome_placeholders(s.get("description",  _WES_DEFAULTS["description"]),  member, inviter, inv_total, channel_id=s.get("channel_id",""))
    raw_color   = s.get("color", _WES_DEFAULTS["color"])
    try:
        color = discord.Color(int(raw_color))
    except Exception:
        color = discord.Color(0xFFD700)

    embed = discord.Embed(
        title=title,
        description=description,
        color=color,
        timestamp=datetime.datetime.utcnow(),
    )


    # Member number field
    embed.add_field(name="🕐 ژمارەی ئەندامان | Member #", value=f"#{member.guild.member_count:,}", inline=True)

    # Invite field
    invite_text = s.get("invite_text", _WES_DEFAULTS["invite_text"])
    if invite_text.strip():
        embed.add_field(
            name="🔗 بانگهێشتکراوە | Invited",
            value=apply_welcome_placeholders(invite_text, member, inviter, inv_total),
            inline=True,
        )

    # Thumbnail
    thumb = s.get("thumbnail_url", "avatar")
    if thumb == "avatar" or not thumb.strip():
        embed.set_thumbnail(url=member.display_avatar.url)
    else:
        embed.set_thumbnail(url=thumb)

    # Footer
    footer_txt = ("🧪 TEST | " if test else "") + member.guild.name
    embed.set_footer(
        text=footer_txt,
        icon_url=member.guild.icon.url if member.guild.icon else None,
    )

    # Banner image (bottom)
    img_url = s.get("image_url", "").strip()
    if img_url:
        embed.set_image(url=img_url)

    return embed


class WelcomeEditTextModal(discord.ui.Modal, title="✏️ Edit Text"):
    """Modal: edit title, description, and color of the welcome embed."""

    embed_title = discord.ui.TextInput(
        label="Title  (use (user) (server))",
        placeholder="☀️ بەخێرهاتی بۆ (server)!",
        style=discord.TextStyle.short,
        max_length=256,
        required=False,
    )
    embed_desc = discord.ui.TextInput(
        label="Description  (use (user) (server) ...)",
        placeholder="👋 Hey (user), welcome to (server)! 🎉",
        style=discord.TextStyle.paragraph,
        max_length=4000,
        required=False,
    )
    embed_color = discord.ui.TextInput(
        label="Color (hex, e.g. FFD700)",
        placeholder="FFD700",
        style=discord.TextStyle.short,
        max_length=8,
        required=False,
    )

    def __init__(self, guild_id):
        super().__init__()
        self.guild_id = guild_id
        s = get_welcome_embed_settings(guild_id)
        self.embed_title.default = s.get("title", _WES_DEFAULTS["title"])
        self.embed_desc.default  = s.get("description", _WES_DEFAULTS["description"])
        self.embed_color.default = hex(s.get("color", 0xFFD700))[2:].upper()

    async def on_submit(self, interaction: discord.Interaction):
        try:
            raw = self.embed_color.value.strip().lstrip("#")
            color_int = int(raw, 16) if raw else _WES_DEFAULTS["color"]
        except ValueError:
            color_int = _WES_DEFAULTS["color"]
        try:
            save_welcome_embed_setting(
                self.guild_id,
                title       = self.embed_title.value.strip() or _WES_DEFAULTS["title"],
                description = self.embed_desc.value.strip()  or _WES_DEFAULTS["description"],
                color       = color_int,
            )
            await interaction.response.send_message(
                "✅ **Text updated!** Run `!testwelcome` to preview.", ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(
                f"❌ Error saving: `{e}`", ephemeral=True
            )

    async def on_error(self, interaction: discord.Interaction, error: Exception):
        try:
            await interaction.response.send_message(f"❌ Unexpected error: `{error}`", ephemeral=True)
        except Exception:
            pass



class WelcomeEditInviteModal(discord.ui.Modal, title="👥 Edit Invite & Channel Info"):
    """Modal: customize the invite text and channel tag."""

    invite_field = discord.ui.TextInput(
        label="Invite Field Text  (use (invite.user) (invite.count))",
        placeholder="🔗 Invited by: (invite.user) | Total: (invite.count)",
        style=discord.TextStyle.short,
        max_length=512,
        required=False,
    )
    channel_id_field = discord.ui.TextInput(
        label="Channel ID — paste the channel ID (shows as tag)",
        placeholder="e.g.  1234567890  — use (channelid) in your welcome text to tag it",
        style=discord.TextStyle.short,
        max_length=30,
        required=False,
    )

    def __init__(self, guild_id):
        super().__init__()
        self.guild_id = guild_id
        s = get_welcome_embed_settings(guild_id)
        self.invite_field.default      = s.get("invite_text", _WES_DEFAULTS["invite_text"])
        self.channel_id_field.default  = s.get("channel_id", "")

    async def on_submit(self, interaction: discord.Interaction):
        try:
            ch_val = self.channel_id_field.value.strip().lstrip("<#>").rstrip(">").strip()
            if ch_val and not ch_val.isdigit():
                return await interaction.response.send_message(
                    "❌ Channel ID دەبەیت تەنھا ژمارە بێت. | Channel ID must be digits only.", ephemeral=True
                )
            save_welcome_embed_setting(
                self.guild_id,
                invite_text = self.invite_field.value.strip(),
                channel_id  = ch_val,
            )
            ch_preview = f"<#{ch_val}>" if ch_val else "not set"
            await interaction.response.send_message(
                f"✅ **Updated!**\n🔗 Invite text saved.\n📌 Channel ID: {ch_preview}\n\n"
                f"Use `(channelid)` anywhere in your welcome title or description to tag it.\n"
                f"Run `!testwelcome` to preview.",
                ephemeral=True,
            )
        except Exception as e:
            await interaction.response.send_message(f"❌ Error: `{e}`", ephemeral=True)

    async def on_error(self, interaction: discord.Interaction, error: Exception):
        try:
            await interaction.response.send_message(f"❌ Unexpected error: `{error}`", ephemeral=True)
        except Exception:
            pass

class WelcomeEditImageModal(discord.ui.Modal, title="🖼️ Edit Image"):
    """Modal: set banner image URL and thumbnail URL."""

    banner_url = discord.ui.TextInput(
        label="Banner Image URL (bottom of embed)",
        placeholder="https://i.imgur.com/yourimage.png",
        style=discord.TextStyle.short,
        max_length=500,
        required=False,
    )
    thumb_url = discord.ui.TextInput(
        label='Thumbnail URL (or type "avatar")',
        placeholder="avatar  — leave blank for member avatar",
        style=discord.TextStyle.short,
        max_length=500,
        required=False,
    )

    def __init__(self, guild_id):
        super().__init__()
        self.guild_id = guild_id
        s = get_welcome_embed_settings(guild_id)
        self.banner_url.default = s.get("image_url",     "")
        self.thumb_url.default  = s.get("thumbnail_url", "avatar")

    async def on_submit(self, interaction: discord.Interaction):
        thumb = self.thumb_url.value.strip() or "avatar"
        save_welcome_embed_setting(
            self.guild_id,
            image_url     = self.banner_url.value.strip(),
            thumbnail_url = thumb,
        )
        await interaction.response.send_message(
            "✅ **Images updated!** Run `!testwelcome` to preview.", ephemeral=True
        )


class WelcomeEmbedSetupView(discord.ui.View):
    """3-button panel for customising the welcome embed (ephemeral panel, no persistence needed)."""

    def __init__(self, guild_id):
        super().__init__(timeout=300)
        self.guild_id = guild_id

    @discord.ui.button(label="✏️ Edit Text (title / description / color)", style=discord.ButtonStyle.primary, row=0)
    async def btn_text(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(WelcomeEditTextModal(self.guild_id))

    @discord.ui.button(label="👥 Edit Invite & Account Info", style=discord.ButtonStyle.secondary, row=1)
    async def btn_invite(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(WelcomeEditInviteModal(self.guild_id))

    @discord.ui.button(label="🖼️ Edit Image (banner / thumbnail)", style=discord.ButtonStyle.secondary, row=2)
    async def btn_image(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(WelcomeEditImageModal(self.guild_id))


@bot.command(name="setwelcomeembed", aliases=["welcomechannel", "setwelcome"])
@commands.has_permissions(manage_guild=True)
async def setwelcomeembed(ctx, channel: discord.TextChannel = None):
    """Set the welcome channel and open the interactive embed customiser."""
    if ctx.guild is None:
        return await ctx.send("Server only. | تەنها لە سێرڤەر.")

    target = channel or ctx.channel
    welcome_channels[str(ctx.guild.id)] = target.id
    save_welcome_channels()

    s = get_welcome_embed_settings(ctx.guild.id)

    info_embed = discord.Embed(
        color=0xFFD700,
        title="🎨 Welcome Embed Setup",
        description=(
            f"✅ Welcome channel set to {target.mention}\n\n"
            "Use the buttons below to customise your welcome embed.\n"
            "Run `!testwelcome` any time to preview it.\n\n"
            "**Placeholders you can use:**\n"
            "`(user)` → tags the new member\n"
            "`(user.name)` → member's display name\n"
            "`(server)` → server name\n"
            "`(member.count)` → total member count\n"
            "`(invite.user)` → who invited them\n"
            "`(invite.count)` → inviter's total invites\n"
            "`(account.age)` → how old their account is\n"
            "`(channelid)` → tags the channel whose ID you set via Invite & Channel Info button"
        ),
    )
    info_embed.set_footer(
        text=f"{ctx.guild.name} · Set by {ctx.author.display_name}",
        icon_url=ctx.guild.icon.url if ctx.guild.icon else None,
    )
    await ctx.send(embed=info_embed, view=WelcomeEmbedSetupView(ctx.guild.id))

@setwelcomeembed.error
async def setwelcomeembed_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ مووچەی Manage Server پێویستە. | You need Manage Server permission.")
    elif isinstance(error, commands.ChannelNotFound):
        await ctx.send("❌ کەناڵ نەدۆزرایەوە. | Channel not found.")

@bot.command(name="removewelcomeembed", aliases=["unsetwelcome"])
@commands.has_permissions(manage_guild=True)
async def removewelcomeembed(ctx):
    """Remove the welcome embed channel setting."""
    if ctx.guild is None:
        await ctx.send("Server only. | تەنها لە سێرڤەر.")
        return
    if str(ctx.guild.id) in welcome_channels:
        del welcome_channels[str(ctx.guild.id)]
        save_welcome_channels()
        await ctx.send("✅ Welcome channel removed. | کەناڵی بەخێربێیت لابرا.")
    else:
        await ctx.send("No welcome channel was set. | هیچ کەناڵی بەخێربێیت دانەنرابوو.")


@removewelcomeembed.error
async def removewelcomeembed_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ مووچەی Manage Server پێویستە. | You need Manage Server permission.")

@bot.command(name="setwelcomechannel", aliases=["welcomesetchannel", "setchannelwelcome"])
@commands.has_permissions(manage_guild=True)
async def setwelcomechannel_cmd(ctx, channel: discord.TextChannel = None):
    """Set the (channel) tag used inside the welcome embed text."""
    if ctx.guild is None:
        return await ctx.send("Server only. | تەنها لە سێرڤەر.")
    if channel is None:
        return await ctx.send(
            "❌ تکایە کەناڵێک دیاری بکە. | Please specify a channel.\n"
            "**Usage:** `!setwelcomechannel #rules`"
        )
    save_welcome_embed_setting(ctx.guild.id, channel_id=str(channel.id))
    embed = discord.Embed(
        color=0x57F287,
        title="✅ کەناڵی بەخێرهاتن دانرا | Welcome Channel Tag Set!",
        description=(
            f"📌 کەناڵ دانرا بۆ {channel.mention}\n\n"
            f"📌 Channel tag set to {channel.mention}\n\n"
            f"ئێستا `(channel)` بەکاربێنە لە ناونیشان یان وەسفی بەخێرهاتندا بۆ نیشاندانی ئەم کەناڵە.\n"
            f"Now use `(channel)` anywhere in your welcome title or description to tag this channel.\n\n"
            f"**Example:** `بقارموو سەڕتاکم باشە بکەوە (channel) | Read the rules in (channel)`\n\n"
            f"Run `!testwelcome` to preview your embed."
        ),
    )
    embed.set_footer(text=f"Set by {ctx.author.display_name} · {ctx.guild.name}")
    await ctx.send(embed=embed)

@setwelcomechannel_cmd.error
async def setwelcomechannel_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ مووچەی Manage Server پێویستە. | You need Manage Server permission.")
    elif isinstance(error, commands.ChannelNotFound):
        await ctx.send("❌ کەناڵ نەدۆزرایەوە. | Channel not found.")


@bot.command(name="welcomeembedsetup", aliases=["wsetup", "welcomesetup"])
@commands.has_permissions(manage_guild=True)
async def welcomeembedsetup_cmd(ctx):
    """Interactive panel to customise this server's welcome embed."""
    if ctx.guild is None:
        return await ctx.send("Server only. | تەنها لە سێرڤەر.")

    s = get_welcome_embed_settings(ctx.guild.id)

    panel = discord.Embed(
        color=discord.Color.from_rgb(88, 101, 242),
        title="🎨 Welcome Embed Setup",
        description=(
            "Click a button below to edit your welcome embed.\n"
            "Use `!testwelcome` any time to preview the result.\n\n"
            "**📝 Placeholders for text:**\n"
            "`(user)` — tags the new member\n"
            "`(user.name)` — member's display name\n"
            "`(server)` — server name\n"
            "`(member.count)` — total members\n"
            "`(invite.user)` — who invited them\n"
            "`(invite.count)` — inviter's invite count\n"
            "`(account.age)` — age of their account\n"
            "`(channelid)` — tags the channel ID you saved (set via Invite & Channel Info button)\n\n"
            "**Current settings:**\n"
            f"🔤 Title: `{s.get('title','')[:60]}`\n"
            f"🖼️ Banner: `{s.get('image_url','') or 'not set'}`\n"
            f"📌 Channel tag: {'<#' + s.get('channel_id','') + '>' if s.get('channel_id') else '`not set`'}"
        ),
    )
    panel.set_footer(
        text=f"{ctx.guild.name} · each server has its own settings",
        icon_url=ctx.guild.icon.url if ctx.guild.icon else None,
    )

    await ctx.send(embed=panel, view=WelcomeEmbedSetupView(ctx.guild.id))

@welcomeembedsetup_cmd.error
async def welcomeembedsetup_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ مووچەی Manage Server پێویستە. | You need Manage Server permission.")


@bot.command(name="setboostembed", aliases=["boostchannel", "setboost"])
@commands.has_permissions(manage_guild=True)
async def setboostembed_cmd(ctx, channel: discord.TextChannel = None):
    """Set the channel where boost celebration embeds are posted."""
    if ctx.guild is None:
        return await ctx.send("Server only. | تەنها لە سێرڤەر.")
    target = channel or ctx.channel
    boost_channels[str(ctx.guild.id)] = target.id
    save_boost_channel(ctx.guild.id, target.id)
    embed = discord.Embed(
        color=0xFF73FA,
        title="✅ کەناڵی بووست دانراو! | Boost Channel Set!",
        description=(
            f"کاتێک کەسێک سێرڤەرەکەت بووست بکات، ئێمە ئاگادارکردنەوەیەکی تایبەت دەنێرین بۆ {target.mention}.\n\n"
            f"When someone boosts your server, a special celebration embed will be sent to {target.mention}.\n\n"
            f"**تاقیکردنەوە / Test:** خۆت بووست بکە یان بەتاڵ بکەیتەوە.\n"
            f"**Test:** Boost or un-boost yourself to test."
        ),
    )
    embed.set_footer(
        text=ctx.guild.name,
        icon_url=ctx.guild.icon.url if ctx.guild.icon else None,
    )
    await ctx.send(embed=embed)

@setboostembed_cmd.error
async def setboostembed_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ مووچەی Manage Server پێویستە. | You need Manage Server permission.")


# ─────────────────────────────────────────────────────────────────────────────
# TEST COMMANDS  (!testwelcome  !testboost  !testinvite)
# ─────────────────────────────────────────────────────────────────────────────

@bot.command(name="testwelcome", aliases=["welcometest", "twelcome"])
@commands.has_permissions(manage_guild=True)
async def testwelcome_cmd(ctx):
    """Send a test welcome embed to the configured welcome channel."""
    if ctx.guild is None:
        return await ctx.send("Server only. | تەنها لە سێرڤەر.")

    gid = str(ctx.guild.id)
    cid = welcome_channels.get(gid)
    target = ctx.guild.get_channel(int(cid)) if cid else ctx.channel
    if target is None:
        target = ctx.channel

    member = ctx.author
    s      = get_welcome_embed_settings(ctx.guild.id)
    embed  = _build_welcome_embed(s, member, inviter=None, inv_total=0, test=True)

    try:
        await target.send(embed=embed)
    except (discord.Forbidden, discord.HTTPException) as e:
        return await ctx.send(f"❌ نەمتوانی بنێرمە {target.mention}: `{e}`")

    if target.id != ctx.channel.id:
        await ctx.send(f"✅ تاقیکردنەوەی بەخێرهاتن نێردرا بۆ {target.mention} | Test welcome sent to {target.mention}", delete_after=5)

@testwelcome_cmd.error
async def testwelcome_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ مووچەی Manage Server پێویستە. | You need Manage Server permission.")


@bot.command(name="testboost", aliases=["boosttest", "tboost"])
@commands.has_permissions(manage_guild=True)
async def testboost_cmd(ctx):
    """Send a test boost embed to the configured boost channel."""
    if ctx.guild is None:
        return await ctx.send("Server only. | تەنها لە سێرڤەر.")

    gid = str(ctx.guild.id)
    cid = boost_channels.get(gid)
    target = ctx.guild.get_channel(int(cid)) if cid else ctx.channel
    if target is None:
        target = ctx.channel

    member = ctx.author
    embed = discord.Embed(
        color=0xFF73FA,
        title="🚀 سووپاس بۆ بووستەکەت! | Thanks for Boosting!",
        description=(
            f"## 💎 {member.mention}\n"
            f"**{member.display_name}** سێرڤەرەکەمانی بووستی کردووە! 🎉\n"
            f"**{member.display_name}** just boosted our server! 🎉\n\n"
            f"ئێستا ئێمە **{ctx.guild.premium_subscription_count}** بووستمان هەیە "
            f"و لەسەر ئاستی **Level {ctx.guild.premium_tier}** ین! ✨\n"
            f"We now have **{ctx.guild.premium_subscription_count}** boosts "
            f"and are at **Level {ctx.guild.premium_tier}**! ✨"
        ),
        timestamp=datetime.datetime.utcnow(),
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    if ctx.guild.icon:
        embed.set_author(name=ctx.guild.name, icon_url=ctx.guild.icon.url)
    embed.set_footer(
        text=f"🧪 TEST | 💜 {ctx.guild.name} appreciates your support!",
        icon_url=ctx.guild.icon.url if ctx.guild.icon else None,
    )

    try:
        await target.send(embed=embed)
    except (discord.Forbidden, discord.HTTPException) as e:
        return await ctx.send(f"❌ نەمتوانی بنێرمە {target.mention}: `{e}`")

    if target.id != ctx.channel.id:
        await ctx.send(f"✅ تاقیکردنەوەی بووست نێردرا بۆ {target.mention} | Test boost sent to {target.mention}", delete_after=5)

@testboost_cmd.error
async def testboost_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ مووچەی Manage Server پێویستە. | You need Manage Server permission.")


@bot.command(name="testinvite", aliases=["invitetest", "tinvite"])
@commands.has_permissions(manage_guild=True)
async def testinvite_cmd(ctx):
    """Send a test invite embed to the configured invite channel."""
    if ctx.guild is None:
        return await ctx.send("Server only. | تەنها لە سێرڤەر.")

    gid = str(ctx.guild.id)
    icid = invite_channels.get(gid)
    target = ctx.guild.get_channel(int(icid)) if icid else ctx.channel
    if target is None:
        target = ctx.channel

    member = ctx.author
    inviter = ctx.author
    inv_total = _get_invite_counts(ctx.guild.id, inviter.id).get("total", 0)

    embed = discord.Embed(
        color=0x57F287,
        title="📨 ئەندامێکی نوێ بەشداری کرد! | New Member Joined!",
        description=(
            f"{member.mention} بەشداری سێرڤەر کرد.\n"
            f"**{ctx.guild.name}** now has **{ctx.guild.member_count:,}** members.\n\n"
            f"🔗 بانگهێشتکراوە لەلایەن | Invited by: {inviter.mention}\n"
            f"📊 کۆی بانگهێشتکردنەکان | Total invites: **{inv_total}**"
        ),
        timestamp=datetime.datetime.utcnow(),
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.set_footer(text=f"🧪 TEST | Inviter: {inviter.display_name}", icon_url=inviter.display_avatar.url)
    embed.add_field(name="👤 ئەندام | Member", value=f"{member} (`{member.id}`)", inline=True)
    embed.add_field(name="🎂 ئەکاونت دروستکراوە | Account Age", value=f"<t:{int(member.created_at.timestamp())}:R>", inline=True)
    embed.add_field(name="📈 ژمارەی ئەندامان | Member #", value=f"#{ctx.guild.member_count:,}", inline=True)

    try:
        await target.send(embed=embed)
    except (discord.Forbidden, discord.HTTPException) as e:
        return await ctx.send(f"❌ نەمتوانی بنێرمە {target.mention}: `{e}`")

    if target.id != ctx.channel.id:
        await ctx.send(f"✅ تاقیکردنەوەی بانگهێشت نێردرا بۆ {target.mention} | Test invite sent to {target.mention}", delete_after=5)

@testinvite_cmd.error
async def testinvite_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ مووچەی Manage Server پێویستە. | You need Manage Server permission.")


# ═══════════════════════ PERK SYSTEM ═══════════════════════

class PerkEditTextModal(discord.ui.Modal, title="✏️ Edit Perk Text"):
    """Modal: write custom perk embed description from scratch."""

    perk_description = discord.ui.TextInput(
        label="Perk Embed Text  (use (role1) and (role2))",
        placeholder=(
            "Write your perk text here.\n"
            "(role1) → 1-Boost role mention\n"
            "(role2) → 2-Boost role mention\n\n"
            "Example:\n"
            "✨ **1 BOOST**\n➜ (role1)\n\n💎 **2 BOOSTS**\n➜ (role2)"
        ),
        style=discord.TextStyle.paragraph,
        max_length=4000,
        required=False,
    )

    def __init__(self, guild_id):
        super().__init__()
        self.guild_id = guild_id
        # Always start blank so user can write from scratch
        self.perk_description.default = ""

    async def on_submit(self, interaction: discord.Interaction):
        save_perk_description(self.guild_id, self.perk_description.value.strip())
        await interaction.response.send_message(
            "✅ **تێکستی پێرک پاشەکەوت کرا! | Perk text saved!**\n\n"
            "📌 `(role1)` → ئەو رۆڵەی 1 بووستە | 1-Boost role\n"
            "📌 `(role2)` → ئەو رۆڵەی 2 بووستە | 2-Boost role\n\n"
            "Run `!perk` to preview your embed.",
            ephemeral=True,
        )


class PerkSetupView(discord.ui.View):
    def __init__(self, ctx):
        super().__init__(timeout=120)
        self.ctx = ctx
        self.one_boost_role = None
        self.two_boost_role = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("❌ تەنها ئەو کەسە دەتوانێت بەکاری بێنێت کە فەرمانەکەی داوا کرد. | Only the command invoker can use this.", ephemeral=True)
            return False
        return True

    @discord.ui.select(
        cls=discord.ui.RoleSelect,
        placeholder="✨ 1 بووست — رۆڵ هەڵبژێرە | Select 1-Boost Role",
        min_values=1,
        max_values=1,
        row=0,
    )
    async def select_one_boost(self, interaction: discord.Interaction, select: discord.ui.RoleSelect):
        self.one_boost_role = select.values[0]
        await interaction.response.send_message(
            f"✅ رۆڵی **1 بووست** دانرا: {self.one_boost_role.mention} | 1-Boost role set: {self.one_boost_role.mention}",
            ephemeral=True,
        )

    @discord.ui.select(
        cls=discord.ui.RoleSelect,
        placeholder="💎 2 بووست — رۆڵ هەڵبژێرە | Select 2-Boost Role",
        min_values=1,
        max_values=1,
        row=1,
    )
    async def select_two_boost(self, interaction: discord.Interaction, select: discord.ui.RoleSelect):
        self.two_boost_role = select.values[0]
        await interaction.response.send_message(
            f"✅ رۆڵی **2 بووست** دانرا: {self.two_boost_role.mention} | 2-Boost role set: {self.two_boost_role.mention}",
            ephemeral=True,
        )

    @discord.ui.button(label="✏️ Edit Text | دەستکاری تێکست", style=discord.ButtonStyle.primary, row=2)
    async def btn_edit_text(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(PerkEditTextModal(interaction.guild.id))

    @discord.ui.button(label="✅ تەواوکردن | Confirm", style=discord.ButtonStyle.success, row=3)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.one_boost_role or not self.two_boost_role:
            await interaction.response.send_message(
                "❌ تکایە هەر دوو رۆڵەکە هەڵبژێرە پێش تەواوکردن. | Please select both roles before confirming.",
                ephemeral=True,
            )
            return
        save_perk_settings(interaction.guild.id, self.one_boost_role.id, self.two_boost_role.id)
        for child in self.children:
            child.disabled = True
        embed = discord.Embed(
            color=0xFF73FA,
            title="✅ دانرانی پێرک تەواو بوو | Perk Setup Complete",
            description=(
                f"✨ **1 بووست:** {self.one_boost_role.mention}\n"
                f"💎 **2 بووست:** {self.two_boost_role.mention}\n\n"
                f"بەکاربێنە `!perk` بۆ نیشاندانی ئمبیدی پێرکەکان.\n"
                f"Use `!perk` to display the perks embed."
            ),
        )
        embed.set_footer(text=interaction.guild.name)
        await interaction.response.edit_message(embed=embed, view=self)
        self.stop()

    @discord.ui.button(label="❌ پاشگەزبوونەوە | Cancel", style=discord.ButtonStyle.danger, row=3)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(
            content="❌ دانرانی پێرک هەڵوەشاندرایەوە. | Perk setup cancelled.",
            embed=None,
            view=self,
        )
        self.stop()

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True


@bot.command(name="setupperk", aliases=["perksetup"])
@commands.has_permissions(manage_guild=True)
async def setupperk_cmd(ctx):
    """Interactive setup: choose roles for 1-boost and 2-boost perks."""
    if ctx.guild is None:
        return await ctx.send("Server only. | تەنها لە سێرڤەر.")

    cfg = get_perk_settings(ctx.guild.id)
    current = ""
    if cfg:
        r1 = ctx.guild.get_role(cfg["one_boost_role_id"])
        r2 = ctx.guild.get_role(cfg["two_boost_role_id"])
        current = (
            f"\n\n**دانرایەی ئێستا | Current:**\n"
            f"✨ 1 Boost → {r1.mention if r1 else '`deleted`'}\n"
            f"💎 2 Boosts → {r2.mention if r2 else '`deleted`'}"
        )

    embed = discord.Embed(
        color=0xFF73FA,
        title="⚙️ دانرانی پێرک | Perk Setup",
        description=(
            "**١** — رۆڵی **1 بووست** هەڵبژێرە.\n"
            "**٢** — رۆڵی **2 بووست** هەڵبژێرە.\n"
            "**٣** — **تەواوکردن** دابگرە.\n\n"
            "**1** — Select the **1-Boost** role.\n"
            "**2** — Select the **2-Boost** role.\n"
            "**3** — Click **Confirm**." + current
        ),
    )
    embed.set_footer(text=ctx.guild.name)
    view = PerkSetupView(ctx)
    await ctx.send(embed=embed, view=view)

@setupperk_cmd.error
async def setupperk_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ مووچەی Manage Server پێویستە. | You need Manage Server permission.")


@bot.command(name="perk", aliases=["perks", "boosterperks"])
async def perk_cmd(ctx):
    """Display the server's booster perks embed."""
    if ctx.guild is None:
        return await ctx.send("Server only. | تەنها لە سێرڤەر.")

    cfg = get_perk_settings(ctx.guild.id)

    if cfg:
        r1 = ctx.guild.get_role(cfg["one_boost_role_id"])
        r2 = ctx.guild.get_role(cfg["two_boost_role_id"])
        one_boost_mention = r1.mention if r1 else "`role deleted`"
        two_boost_mention = r2.mention if r2 else "`role deleted`"
        custom_desc = cfg.get("description", "").strip()
    else:
        one_boost_mention = "`not set — use !setupperk`"
        two_boost_mention = "`not set — use !setupperk`"
        custom_desc = ""

    name = ctx.guild.name

    # Use custom description if set, replacing (role1)/(role2) with real mentions
    if custom_desc:
        description = (
            f"```\n╔══════════════════════╗\n"
            f"   🚀 {name.upper()} BOOSTER PERKS\n"
            f"╚══════════════════════╝```\n"
            + custom_desc
            .replace("(role1)", one_boost_mention)
            .replace("(role2)", two_boost_mention)
            .replace("(role)", one_boost_mention)
        )
    else:
        description = (
            f"```\n╔══════════════════════╗\n"
            f"   🚀 {name.upper()} BOOSTER PERKS\n"
            f"╚══════════════════════╝```\n"
            f"✨ **1 BOOST**\n"
            f"➜ {one_boost_mention}\n\n"
            f"💎 **2 BOOSTS**\n"
            f"➜ {two_boost_mention}\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"🌟 **SPECIAL ROLES**\n\n"
            f"🏷️ Custom Name\n"
            f"🖼️ Custom Icon\n"
            f"🎨 Custom Color\n\n"
            f"➜ Cost: **2 Boosts**\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"❤️ Thank you for supporting **{name}**"
        )

    try:
        embed = discord.Embed(color=0xFF73FA, description=description)
        if ctx.guild.icon:
            embed.set_thumbnail(url=ctx.guild.icon.url)
        embed.set_footer(text=f"{name} Booster Perks")
        await ctx.send(embed=embed)
    except Exception as e:
        await ctx.send(f"❌ Error building perk embed: `{e}`")

@perk_cmd.error
async def perk_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ مووچەی Manage Server پێویستە. | You need Manage Server permission.")
    else:
        await ctx.send(f"❌ Error: `{error}`")


# ═══════════════════════ SETPERK COMMAND ═══════════════════════

class SetPerkTextModal(discord.ui.Modal, title="✏️ Edit Perk Text"):
    """Blank modal — write perk text from scratch using (role1) and (role2)."""

    perk_text = discord.ui.TextInput(
        label="Perk Text  (use (role1) and (role2))",
        placeholder=(
            "Write your full perk embed text here.\n\n"
            "(role1) → tags the 1-Boost role\n"
            "(role2) → tags the 2-Boost role\n\n"
            "Example:\n"
            "✨ **1 BOOST**\n➜ (role1)\n\n"
            "💎 **2 BOOSTS**\n➜ (role2)\n\n"
            "❤️ Thank you for boosting!"
        ),
        style=discord.TextStyle.paragraph,
        max_length=4000,
        required=False,
    )

    def __init__(self, guild_id):
        super().__init__()
        self.guild_id = guild_id
        self.perk_text.default = ""  # always blank

    async def on_submit(self, interaction: discord.Interaction):
        try:
            save_perk_description(self.guild_id, self.perk_text.value.strip())
            await interaction.response.send_message(
                "✅ **تێکستی پێرک پاشەکەوت کرا! | Perk text saved!**\n\n"
                "📌 `(role1)` → 1-Boost role\n"
                "📌 `(role2)` → 2-Boost role\n\n"
                "Run `!perk` to preview.",
                ephemeral=True,
            )
        except Exception as e:
            await interaction.response.send_message(f"❌ Error saving: `{e}`", ephemeral=True)

    async def on_error(self, interaction: discord.Interaction, error: Exception):
        try:
            await interaction.response.send_message(f"❌ Unexpected error: `{error}`", ephemeral=True)
        except Exception:
            pass


class _PerkRolePickView(discord.ui.View):
    """Ephemeral view with a single RoleSelect — opened when a role button is clicked."""

    def __init__(self, slot: int, guild_id: int):
        super().__init__(timeout=60)
        self.slot = slot         # 1 or 2
        self.guild_id = guild_id

    @discord.ui.select(
        cls=discord.ui.RoleSelect,
        placeholder="رۆڵ هەڵبژێرە | Select a role",
        min_values=1,
        max_values=1,
        row=0,
    )
    async def pick_role(self, interaction: discord.Interaction, select: discord.ui.RoleSelect):
        role = select.values[0]
        if self.slot == 1:
            save_perk_role1(self.guild_id, role.id)
            label = "1 بووست | 1-Boost"
        else:
            save_perk_role2(self.guild_id, role.id)
            label = "2 بووست | 2-Boost"
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(
            content=f"✅ **{label}** role set: {role.mention}\n`(role{self.slot})` will now tag this role in your perk text.",
            view=self,
        )
        self.stop()


class SetPerkView(discord.ui.View):
    """3-button panel: role1 button, role2 button, edit text button."""

    def __init__(self, ctx):
        super().__init__(timeout=300)
        self.ctx = ctx

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message(
                "❌ Only the command invoker can use this. | تەنها ئەو کەسە دەتوانێت بەکاری بێنێت.",
                ephemeral=True,
            )
            return False
        return True

    @discord.ui.button(label="✨ 1-Boost Role | رۆڵی 1 بووست", style=discord.ButtonStyle.secondary, row=0)
    async def btn_role1(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            "✨ **رۆڵی 1 بووست هەڵبژێرە | Select the 1-Boost role:**",
            view=_PerkRolePickView(slot=1, guild_id=interaction.guild.id),
            ephemeral=True,
        )

    @discord.ui.button(label="💎 2-Boost Role | رۆڵی 2 بووست", style=discord.ButtonStyle.secondary, row=0)
    async def btn_role2(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            "💎 **رۆڵی 2 بووست هەڵبژێرە | Select the 2-Boost role:**",
            view=_PerkRolePickView(slot=2, guild_id=interaction.guild.id),
            ephemeral=True,
        )

    @discord.ui.button(label="✏️ Edit Text | دەستکاری تێکست", style=discord.ButtonStyle.primary, row=1)
    async def btn_edit_text(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(SetPerkTextModal(interaction.guild.id))


@bot.command(name="setperk")
@commands.has_permissions(manage_guild=True)
async def setperk_cmd(ctx):
    """Perk setup: pick both roles + write custom embed text."""
    if ctx.guild is None:
        return await ctx.send("Server only. | تەنها لە سێرڤەر.")

    cfg = get_perk_settings(ctx.guild.id)
    r1_text, r2_text = "`not set`", "`not set`"
    if cfg:
        r1 = ctx.guild.get_role(cfg["one_boost_role_id"]) if cfg.get("one_boost_role_id") else None
        r2 = ctx.guild.get_role(cfg["two_boost_role_id"]) if cfg.get("two_boost_role_id") else None
        if r1: r1_text = r1.mention
        if r2: r2_text = r2.mention

    embed = discord.Embed(
        color=0xFF73FA,
        title="⚙️ دانرانی پێرک | Perk Setup",
        description=(
            "**١** — کلیک لە **1-Boost Role** بکە رۆڵ هەڵبژێرە.\n"
            "**٢** — کلیک لە **2-Boost Role** بکە رۆڵ هەڵبژێرە.\n"
            "**٣** — **Edit Text** بکە بۆ نووسینی تێکستی خۆت.\n\n"
            "**1** — Click **1-Boost Role** to pick the role.\n"
            "**2** — Click **2-Boost Role** to pick the role.\n"
            "**3** — Click **Edit Text** to write the perk embed text.\n\n"
            "📌 **Placeholders:**\n"
            "`(role1)` → tags 1-Boost role\n"
            "`(role2)` → tags 2-Boost role\n\n"
            f"**Current | ئێستا:**\n"
            f"✨ 1 Boost → {r1_text}\n"
            f"💎 2 Boosts → {r2_text}"
        ),
    )
    embed.set_footer(text=ctx.guild.name, icon_url=ctx.guild.icon.url if ctx.guild.icon else None)
    await ctx.send(embed=embed, view=SetPerkView(ctx))

@setperk_cmd.error
async def setperk_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ مووچەی Manage Server پێویستە. | You need Manage Server permission.")


# ═══════════════════════ INVITE TRACKER ═══════════════════════

@bot.command(name="setinviteembed", aliases=["serinviteembed", "invitechannel", "setinvite"])
@commands.has_permissions(manage_guild=True)
async def setinviteembed(ctx, channel: discord.TextChannel = None):
    """Set the channel where invite-join embeds are posted."""
    if ctx.guild is None:
        return await ctx.send("Server only. | تەنها لە سێرڤەر.")
    target = channel or ctx.channel
    invite_channels[str(ctx.guild.id)] = target.id
    save_invite_channels()
    current_text = get_invite_custom_text(ctx.guild.id)
    embed = discord.Embed(
        color=0x5865F2,
        title="✅ کەناڵی بانگهێشتکردن دانراو | Invite Channel Set",
        description=(
            "سیستەمی بانگهێشتکردن بە سەرکەوتوویی دامەزراند.\n"
            "The invite announcement system has been configured."
        ),
        timestamp=datetime.datetime.utcnow(),
    )
    embed.add_field(
        name="📢 کەناڵ | Channel",
        value=target.mention,
        inline=True,
    )
    embed.add_field(
        name="⚡ بارودۆخ | Status",
        value="🟢 چالاک | Active",
        inline=True,
    )
    embed.add_field(name="\u200b", value="\u200b", inline=True)
    if current_text:
        embed.add_field(
            name="✏️ دەقی ئێستا | Current Custom Text",
            value=f"```{current_text[:300]}```",
            inline=False,
        )
    else:
        embed.add_field(
            name="✏️ دەقی ئێستا | Custom Text",
            value=(
                "دەقی تایبەت دانەنراوە — دەقی بنەڕەتی بەکاردێت.\n"
                "No custom text set — default invite embed will be used.\n"
                "*(دەگمەی ✏️ Edit Text بەکاربێنە | Click ✏️ Edit Text below to customize)*"
            ),
            inline=False,
        )
    embed.add_field(
        name="📋 فەرمانەکانی تر | Other Commands",
        value="`!invites [@member]` · `!invitetop` · `!removeinviteembed`",
        inline=False,
    )
    embed.add_field(
        name="⚠️ تێبینی | Note",
        value="دڵنیابەرەوە بۆتەکە مووچەی **Manage Server** هەیە.\nMake sure the bot has **Manage Server** permission to read invites.",
        inline=False,
    )
    embed.set_thumbnail(url=ctx.guild.icon.url if ctx.guild.icon else ctx.author.display_avatar.url)
    embed.set_footer(
        text=f"⚙️ Set up by {ctx.author.display_name} · {ctx.guild.name}",
        icon_url=ctx.author.display_avatar.url,
    )
    await ctx.send(embed=embed, view=InviteSetupView(ctx.guild.id))

@bot.command(name="removeinviteembed", aliases=["unsetinvite", "removeinvite"])
@commands.has_permissions(manage_guild=True)
async def removeinviteembed(ctx):
    """Remove the invite embed channel."""
    if ctx.guild is None:
        return await ctx.send("Server only. | تەنها لە سێرڤەر.")
    gid = str(ctx.guild.id)
    if gid in invite_channels:
        del invite_channels[gid]
        save_invite_channels()
        await ctx.send("✅ کەناڵی بانگهێشتکردن لابرا. | Invite channel removed.")
    else:
        await ctx.send("هیچ کەناڵی بانگهێشتکردن دانەنرابوو. | No invite channel was set.")

@bot.command(name="invites", aliases=["myinvites", "checkinvites"])
async def invites_cmd(ctx, member: discord.Member = None):
    """Check how many members a user has invited."""
    if ctx.guild is None:
        return await ctx.send("Server only. | تەنها لە سێرڤەر.")
    target = member or ctx.author
    d = _get_invite_counts(ctx.guild.id, target.id)
    total = d["total"]
    left  = d["left"]
    real  = max(0, total - left)
    embed = discord.Embed(
        color=0x5865F2,
        title=f"📨 بانگهێشتکردنەکانی {target.display_name} | Invites",
    )
    embed.set_thumbnail(url=target.display_avatar.url)
    embed.add_field(name="✅ کۆی گشتی | Total Invited",  value=f"**{total}**", inline=True)
    embed.add_field(name="🚪 چووەتەوە | Left Server",    value=f"**{left}**",  inline=True)
    embed.add_field(name="📊 بانگهێشتی مێردار | Real",   value=f"**{real}**",  inline=True)
    embed.set_footer(text=f"Requested by {ctx.author.display_name}")
    await ctx.send(embed=embed)

@bot.command(name="invitetop", aliases=["invitelb", "inviteleaderboard", "topinviters"])
async def invitetop_cmd(ctx):
    """Show the top 10 inviters in this server."""
    if ctx.guild is None:
        return await ctx.send("Server only. | تەنها لە سێرڤەر.")
    gid = str(ctx.guild.id)
    guild_data = invite_counts.get(gid, {})
    if not guild_data:
        return await ctx.send("هیچ داتایەکی بانگهێشتکردن بەردەست نییە. | No invite data yet.")
    sorted_users = sorted(guild_data.items(), key=lambda kv: kv[1].get("total", 0), reverse=True)[:10]
    embed = discord.Embed(
        color=0xFFD700,
        title="🏆 باڵاترین بانگهێشتکەرەکان | Top Inviters",
        description=f"سێرڤەر: **{ctx.guild.name}**",
    )
    lines = []
    medals = ["🥇", "🥈", "🥉"] + ["🔹"] * 7
    for i, (uid, d) in enumerate(sorted_users):
        total = d.get("total", 0)
        left  = d.get("left", 0)
        real  = max(0, total - left)
        member = ctx.guild.get_member(int(uid))
        name   = member.display_name if member else f"Unknown ({uid})"
        lines.append(f"{medals[i]} **{name}** — {real} real (`{total}` total, `{left}` left)")
    embed.add_field(name="پێشەنگان | Rankings", value="\n".join(lines) or "—", inline=False)
    embed.set_footer(text=f"Requested by {ctx.author.display_name}")
    await ctx.send(embed=embed)

# ═══════════════════════ APPLY SYSTEM ═══════════════════════

class ApplyModal(discord.ui.Modal):
    """Dynamically built apply modal using per-guild saved questions."""

    def __init__(self, guild_id: int):
        super().__init__(title="📋 داواکاریی ستاف | Staff Application")
        self._guild_id = guild_id
        # Use guild questions; fall back to defaults if none saved or list is empty.
        questions = apply_questions_map.get(str(guild_id)) or _DEFAULT_APPLY_QUESTIONS
        for q in questions[:5]:
            label = (q or "Question")[:45].strip() or "Question"
            self.add_item(discord.ui.TextInput(
                label=label,
                placeholder="وەڵامی خۆ بنووسە... | Write your answer here...",
                style=discord.TextStyle.paragraph,
                max_length=500,
                required=False,
            ))

    async def on_submit(self, interaction: discord.Interaction):
        guild = interaction.guild
        gid = str(guild.id) if guild else None
        apply_ch = None
        if gid and gid in apply_channels:
            apply_ch = guild.get_channel(apply_channels[gid])
        embed = discord.Embed(
            color=0x5865F2,
            title="📋 داواکاریی ستافی نوێ | New Staff Application",
            timestamp=datetime.datetime.utcnow(),
        )
        embed.set_author(
            name=f"{interaction.user.display_name} ({interaction.user})",
            icon_url=interaction.user.display_avatar.url,
        )
        questions = apply_questions_map.get(str(self._guild_id), _DEFAULT_APPLY_QUESTIONS)
        for i, item in enumerate(self.children):
            q_label = questions[i] if i < len(questions) else f"Question {i+1}"
            embed.add_field(
                name=f"{i+1}️⃣ {q_label[:80]}",
                value=item.value or "—",
                inline=False,
            )
        embed.set_footer(
            text=f"User ID: {interaction.user.id} · {guild.name if guild else ''}",
            icon_url=guild.icon.url if guild and guild.icon else None,
        )
        if apply_ch:
            try:
                await apply_ch.send(embed=embed)
                await interaction.response.send_message(
                    "✅ داواکارییەکەت نێردرا! | Your application was submitted successfully! 🎉",
                    ephemeral=True,
                )
            except (discord.Forbidden, discord.HTTPException):
                await interaction.response.send_message(
                    "❌ نەتوانرا داواکارییەکەت بنێردرێت. | Could not send your application.",
                    ephemeral=True,
                )
        else:
            await interaction.response.send_message(
                "❌ هیچ کەناڵی داواکاریی دانەنراوە. | No apply channel has been set.",
                ephemeral=True,
            )

    async def on_error(self, interaction: discord.Interaction, error: Exception):
        try:
            await interaction.response.send_message(
                "❌ هەڵەیەک ڕوویدا. | An error occurred.",
                ephemeral=True,
            )
        except Exception:
            pass


class ApplyView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="📋 تقدیم داواکاری | Submit Application",
        style=discord.ButtonStyle.blurple,
        custom_id="apply_submit_btn",
    )
    async def apply_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.response.send_modal(ApplyModal(interaction.guild_id))
        except Exception as exc:
            try:
                await interaction.response.send_message(
                    f"❌ هەڵەیەک ڕوویدا. | An error occurred: `{exc}`", ephemeral=True
                )
            except Exception:
                pass


@bot.command(name="apply", aliases=["داواکاری", "application"])
async def apply_cmd(ctx):
    """Open the staff application form."""
    if ctx.guild is None:
        return await ctx.send("Server only. | تەنها لە سێرڤەر.")

    gid = str(ctx.guild.id)
    apply_ch = None
    if gid in apply_channels:
        apply_ch = ctx.guild.get_channel(apply_channels[gid])

    embed = discord.Embed(
        color=0x5865F2,
        title="📋 داواکاریی ستاف | Staff Application",
        description=(
            "سڵاو! 👋 ئەگەر دەتەوێت ستاف بیت تکایە پرسیارەکان بخوێنەوە و وەڵامیان بدەرەوە.\n"
            "Hey there! 👋 If you want to be staff, please read and answer the questions below.\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "**1-** دەتوانی کەسێکی باش بیت لەگەڵ کەسانی تر؟\n"
            "**1-** Can you be a good person with others?\n\n"
            "**2-** دەتوانی ئەکتیڤ بیت لە ڤۆیس و چات؟\n"
            "**2-** Can you be active in voice and chat?\n\n"
            "**3-** دەتوانی 3 ریکلامی رۆژانە بکەیت؟\n"
            "**3-** Can you do 3 reklams daily?\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "⬇️ دەگمەی **داواکاری** دابگرە بۆ ئەوەی فۆرمەکە پڕ بکەیتەوە.\n"
            "⬇️ Click **Apply** below to fill out the form."
        ),
    )
    embed.set_footer(text=f"{ctx.guild.name} · Staff Team")
    if ctx.guild.icon:
        embed.set_thumbnail(url=ctx.guild.icon.url)

    view = ApplyView()
    await ctx.send(embed=embed, view=view)


@bot.command(name="setapplychannel", aliases=["applychannel", "setapply"])
@commands.has_permissions(manage_guild=True)
async def setapplychannel(ctx, channel: discord.TextChannel = None):
    """Set the channel where applications are sent."""
    if ctx.guild is None:
        return await ctx.send("Server only. | تەنها لە سێرڤەر.")
    target = channel or ctx.channel
    apply_channels[str(ctx.guild.id)] = target.id
    save_apply_channels()
    e = discord.Embed(
        color=0x57F287,
        title="✅ کەناڵی داواکاری دانراو! | Apply Channel Set!",
        description=(
            f"داواکارییەکان دەنێردرێن بۆ {target.mention}.\n"
            f"Applications will be sent to {target.mention}.\n\n"
            f"**داواکارییەکان:** `!apply`"
        ),
    )
    e.set_footer(text=f"Set by {ctx.author.display_name}")
    await ctx.send(embed=e)


@setapplychannel.error
async def setapplychannel_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ مووچەی Manage Server پێویستە. | You need Manage Server permission.")
    elif isinstance(error, commands.ChannelNotFound):
        await ctx.send("❌ کەناڵ نەدۆزرایەوە. | Channel not found.")

@bot.command(name="removeapplychannel", aliases=["unsetapply"])
@commands.has_permissions(manage_guild=True)
async def removeapplychannel(ctx):
    """Remove the apply channel."""
    if ctx.guild is None:
        return await ctx.send("Server only. | تەنها لە سێرڤەر.")
    gid = str(ctx.guild.id)
    if gid in apply_channels:
        del apply_channels[gid]
        save_apply_channels()
        await ctx.send("✅ کەناڵی داواکاری لابرا. | Apply channel removed.")
    else:
        await ctx.send("هیچ کەناڵی داواکاری دانەنرابوو. | No apply channel was set.")

@removeapplychannel.error
async def removeapplychannel_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ مووچەی Manage Server پێویستە. | You need Manage Server permission.")


# ══════════════════ ASETAPPLY — ADMIN APPLY PANEL SETUP ══════════════════


class ASetApplyEditModal(discord.ui.Modal, title="\u270f\ufe0f \u062f\u06d5\u0633\u062a\u06a9\u0627\u0631\u06cc\u06a9\u0631\u062f\u0646\u06cc \u067e\u0631\u0633\u06cc\u0627\u0631\u06d5\u06a9\u0627\u0646 | Edit Apply Questions"):
    q1 = discord.ui.TextInput(label="\u067e\u0631\u0633\u06cc\u0627\u0631 1 | Question 1 \u2605", style=discord.TextStyle.short, max_length=100, required=True)
    q2 = discord.ui.TextInput(label="\u067e\u0631\u0633\u06cc\u0627\u0631 2 | Question 2",  style=discord.TextStyle.short, max_length=100, required=False)
    q3 = discord.ui.TextInput(label="\u067e\u0631\u0633\u06cc\u0627\u0631 3 | Question 3",  style=discord.TextStyle.short, max_length=100, required=False)
    q4 = discord.ui.TextInput(label="\u067e\u0631\u0633\u06cc\u0627\u0631 4 | Question 4",  style=discord.TextStyle.short, max_length=100, required=False)
    q5 = discord.ui.TextInput(label="\u067e\u0631\u0633\u06cc\u0627\u0631 5 | Question 5",  style=discord.TextStyle.short, max_length=100, required=False)

    def __init__(self, guild_id: int, current: list):
        super().__init__()
        self.guild_id = guild_id
        for i, field in enumerate([self.q1, self.q2, self.q3, self.q4, self.q5]):
            if i < len(current):
                field.default = current[i]

    async def on_submit(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message(
                "\u274c \u062a\u06d5\u0646\u0647\u0627 \u06d5\u062f\u0645\u06cc\u0646 \u062f\u06d5\u062a\u0648\u0627\u0646\u06ce\u062a. | Administrators only.",
                ephemeral=True,
            )
        questions = [f.value.strip() for f in [self.q1, self.q2, self.q3, self.q4, self.q5] if f.value.strip()]
        if not questions:
            return await interaction.response.send_message(
                "\u274c \u0628\u06d5\u0694\u06cc\u0633\u062a \u06cc\u06d5\u06a9 \u067e\u0631\u0633\u06cc\u0627\u0631 \u0628\u0646\u0648\u0648\u0633\u06ce\u062a. | At least one question is required.",
                ephemeral=True,
            )
        save_apply_questions(self.guild_id, questions)
        lines = "\n".join(f"{i+1}. {q}" for i, q in enumerate(questions))
        await interaction.response.send_message(
            f"\u2705 **{len(questions)}** \u067e\u0631\u0633\u06cc\u0627\u0631 \u062e\u06d5\u0632\u0646 \u06a9\u0631\u0627 | question(s) saved:\n{lines}",
            ephemeral=True,
        )

    async def on_error(self, interaction: discord.Interaction, error: Exception):
        try:
            await interaction.response.send_message(
                "\u274c \u0647\u06d5\u06b5\u06d5\u06cc\u06d5\u06a9 \u0695\u0648\u0648\u06cc\u062f\u0627. | An error occurred.", ephemeral=True
            )
        except Exception:
            pass


class ASetApplyLangView(discord.ui.View):
    def __init__(self, guild_id: int):
        super().__init__(timeout=60)
        self.guild_id = guild_id

    async def _pick(self, interaction: discord.Interaction, lang: str, label: str):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("\u274c Administrators only.", ephemeral=True)
        save_apply_lang(self.guild_id, lang)
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(content=f"\u2705 {label}", view=self)
        self.stop()

    @discord.ui.button(label="\U0001f1ee\U0001f1f6 \u06a9\u0648\u0631\u062f\u06cc \u062a\u06d5\u0646\u0647\u0627 | Kurdish only", style=discord.ButtonStyle.secondary, row=0)
    async def ku_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._pick(interaction, "ku", "\u0632\u0645\u0627\u0646\u06cc \u06a9\u0648\u0631\u062f\u06cc \u062f\u0627\u0646\u0631\u0627 | Language set to Kurdish.")

    @discord.ui.button(label="\U0001f1ec\U0001f1e7 English only", style=discord.ButtonStyle.secondary, row=0)
    async def en_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._pick(interaction, "en", "Language set to English.")

    @discord.ui.button(label="\U0001f30d \u0647\u06d5\u0631 \u062f\u0648\u0648 | Both", style=discord.ButtonStyle.primary, row=0)
    async def both_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._pick(interaction, "both", "\u0647\u06d5\u0631 \u062f\u0648\u0648 \u0632\u0645\u0627\u0646 \u062f\u0627\u0646\u0631\u0627 | Language set to Both.")


class ASetApplyView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    async def _admin_check(self, interaction: discord.Interaction) -> bool:
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "\u274c \u062a\u06d5\u0646\u0647\u0627 \u06d5\u062f\u0645\u06cc\u0646 \u062f\u06d5\u062a\u0648\u0627\u0646\u06ce\u062a \u06d5\u0645\u06d5\u06cc \u067e\u0627\u0646\u06d5\u0644\u06d5 \u0628\u06d5\u06a9\u0627\u0631 \u0628\u06cc\u0646\u06ce\u062a. | Administrators only.",
                ephemeral=True,
            )
            return False
        return True

    @discord.ui.button(
        label="\u270f\ufe0f \u062f\u06d5\u0633\u062a\u06a9\u0627\u0631\u06cc\u06a9\u0631\u062f\u0646\u06cc \u062f\u06d5\u0642 | Edit Text",
        style=discord.ButtonStyle.primary,
        custom_id="asetapply:edit_text",
        row=0,
    )
    async def edit_text_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._admin_check(interaction):
            return
        current = apply_questions_map.get(str(interaction.guild_id), _DEFAULT_APPLY_QUESTIONS)
        await interaction.response.send_modal(ASetApplyEditModal(interaction.guild_id, current))

    @discord.ui.button(
        label="\U0001f30d \u0632\u0645\u0627\u0646 | Language",
        style=discord.ButtonStyle.secondary,
        custom_id="asetapply:lang",
        row=0,
    )
    async def lang_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._admin_check(interaction):
            return
        cur = apply_lang_map.get(str(interaction.guild_id), "both")
        lang_labels = {"ku": "\U0001f1ee\U0001f1f6 Kurdish only", "en": "\U0001f1ec\U0001f1e7 English only", "both": "\U0001f30d Both"}
        await interaction.response.send_message(
            f"\u0632\u0645\u0627\u0646\u06cc \u06d5\u06cc\u0633\u062a\u0627 | Current: **{lang_labels.get(cur, cur)}**\n\u0632\u0645\u0627\u0646\u06cc \u062f\u0627\u0648\u0627\u06a9\u0627\u0631\u06cc\u06a9\u06d5 \u062f\u06cc\u0627\u0631\u06cc \u0628\u06a9\u06d5 | Choose the apply panel language:",
            view=ASetApplyLangView(interaction.guild_id),
            ephemeral=True,
        )

    @discord.ui.button(
        label="\U0001f4ca \u062f\u06c6\u062e | Status",
        style=discord.ButtonStyle.secondary,
        custom_id="asetapply:status",
        row=1,
    )
    async def status_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._admin_check(interaction):
            return
        gid = str(interaction.guild_id)
        questions = apply_questions_map.get(gid, _DEFAULT_APPLY_QUESTIONS)
        lang = apply_lang_map.get(gid, "both")
        cid = apply_channels.get(gid)
        lang_labels = {"ku": "\U0001f1ee\U0001f1f6 Kurdish only", "en": "\U0001f1ec\U0001f1e7 English only", "both": "\U0001f30d Both"}
        embed = discord.Embed(
            color=0x5865F2,
            title="\U0001f4cb \u062f\u06c6\u062e\u06cc \u062f\u0627\u0645\u06d5\u0632\u0631\u0627\u0646\u062f\u0646\u06cc \u062f\u0627\u0648\u0627\u06a9\u0627\u0631\u06cc | Apply Setup Status",
            timestamp=datetime.datetime.utcnow(),
        )
        embed.add_field(name="\U0001f4e2 \u06a9\u06d5\u0646\u0627\u06b5 | Channel", value=f"<#{cid}>" if cid else "\u274c Not set (`!setapplychannel`)", inline=True)
        embed.add_field(name="\U0001f30d \u0632\u0645\u0627\u0646 | Language", value=lang_labels.get(lang, lang), inline=True)
        q_list = "\n".join(f"`{i+1}.` {q}" for i, q in enumerate(questions)) or "_(default)_"
        embed.add_field(name=f"\u2753 \u067e\u0631\u0633\u06cc\u0627\u0631\u06d5\u06a9\u0627\u0646 ({len(questions)}) | Questions", value=q_list, inline=False)
        embed.set_footer(text=interaction.guild.name)
        await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.command(name="asetapply", aliases=["applyadmin", "applysetup"])
@commands.has_permissions(administrator=True)
async def asetapply_cmd(ctx):
    if ctx.guild is None:
        return await ctx.send("Server only. | \u062a\u06d5\u0646\u0647\u0627 \u0644\u06d5 \u0633\u06ce\u0631\u06a4\u06d5\u0631.")
    try:
        await ctx.message.delete()
    except (discord.Forbidden, discord.HTTPException):
        pass
    gid = str(ctx.guild.id)
    questions = apply_questions_map.get(gid, _DEFAULT_APPLY_QUESTIONS)
    lang = apply_lang_map.get(gid, "both")
    cid = apply_channels.get(gid)
    lang_labels = {"ku": "\U0001f1ee\U0001f1f6 Kurdish only", "en": "\U0001f1ec\U0001f1e7 English only", "both": "\U0001f30d Both"}
    _ch_val = f"<#{cid}>" if cid else "\u274c Not set \u2014 use `!setapplychannel`"
    embed = discord.Embed(
        color=0x5865F2,
        title="\U0001f4cb \u062f\u0627\u0645\u06d5\u0632\u0631\u0627\u0646\u062f\u0646\u06cc \u062f\u0627\u0648\u0627\u06a9\u0627\u0631\u06cc | Apply Setup Panel",
        description=(
            "\u0661\ufe0f\u20e3 **\u062f\u06d5\u0633\u062a\u06a9\u0627\u0631\u06cc\u06a9\u0631\u062f\u0646\u06cc \u062f\u06d5\u0642 | Edit Text** \u2014 \u067e\u0631\u0633\u06cc\u0627\u0631\u06d5\u06a9\u0627\u0646 \u062f\u0627\u0648\u0627\u06a9\u0627\u0631\u06cc\u06a9\u06d5 \u062f\u06d5\u0633\u062a\u06a9\u0627\u0631\u06cc \u0628\u06a9\u06d5. \u062a\u0627 5 \u067e\u0631\u0633\u06cc\u0627\u0631.\n"
            "1\ufe0f\u20e3 **Edit Text** \u2014 set the questions users answer in the form (up to 5).\n\n"
            "\u0662\ufe0f\u20e3 **\u0632\u0645\u0627\u0646 | Language** \u2014 \u0632\u0645\u0627\u0646\u06cc \u067e\u0627\u0646\u06d5\u0644\u06d5\u06a9\u06d5 \u062f\u06cc\u0627\u0631\u06cc \u0628\u06a9\u06d5.\n"
            "2\ufe0f\u20e3 **Language** \u2014 choose Kurdish, English, or Both for the panel.\n\n"
            f"\U0001f4e2 \u06a9\u06d5\u0646\u0627\u06b5 | Channel: {_ch_val}\n"
            f"\U0001f30d \u0632\u0645\u0627\u0646 | Language: **{lang_labels.get(lang, lang)}**\n"
            f"\u2753 \u067e\u0631\u0633\u06cc\u0627\u0631\u06d5\u06a9\u0627\u0646 | Questions: **{len(questions)}**"
        ),
        timestamp=datetime.datetime.utcnow(),
    )
    if ctx.guild.icon:
        embed.set_thumbnail(url=ctx.guild.icon.url)
    embed.set_footer(text=f"{ctx.guild.name} \u00b7 Admins only")
    await ctx.send(embed=embed, view=ASetApplyView())


@asetapply_cmd.error
async def asetapply_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("\u274c \u062a\u06d5\u0646\u0647\u0627 \u06d5\u062f\u0645\u06cc\u0646 \u062f\u06d5\u062a\u0648\u0627\u0646\u06ce\u062a \u06d5\u0645\u06d5\u06cc \u0641\u06d5\u0631\u0645\u0627\u0646\u06d5 \u0628\u06d5\u06a9\u0627\u0631 \u0628\u06cc\u0646\u06ce\u062a. | Only administrators can use this command.")


# ═══════════════════════ LOG COMMANDS ═══════════════════════

@bot.command(name="setlog", aliases=["setlogchannel", "logchannel"])
@commands.has_permissions(manage_guild=True)
async def setlog(ctx, channel: discord.TextChannel = None):
    """Set the server log channel."""
    if ctx.guild is None:
        return await ctx.send("Server only. | تەنها لە سێرڤەر.")
    target = channel or ctx.channel
    log_channels[str(ctx.guild.id)] = target.id
    save_log_channels()
    e = discord.Embed(
        color=0x57F287,
        title="✅ کەناڵی لۆگ دانراو! | Log Channel Set!",
        description=(
            f"هەموو چالاکییەکانی سێرڤەر تۆمار دەکرێن بۆ {target.mention}.\n"
            f"All server activity will now be logged to {target.mention}."
        ),
    )
    e.add_field(
        name="📋 چی تۆمار دەکرێت | What gets logged",
        value=(
            "✅ بەشداریکردن/چوونەوە | Join/Leave\n"
            "🗑️ سڕینەوەی پەیام | Message Delete\n"
            "✏️ دەستکاریکردنی پەیام | Message Edit\n"
            "🔨 بانکردن/لابردنی بان | Ban/Unban\n"
            "📝 گۆڕینی ناوی نمایشی | Nickname Change\n"
            "🎭 گۆڕینی رۆڵ | Role Update\n"
            "📁 دروستکردن/سڕینەوەی چانێل | Channel Create/Delete"
        ),
        inline=False,
    )
    e.set_footer(text=f"Set by {ctx.author.display_name}")
    await ctx.send(embed=e)

@setlog.error
async def setlog_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ مووچەی Manage Server پێویستە. | You need Manage Server permission.")
    elif isinstance(error, commands.ChannelNotFound):
        await ctx.send("❌ کەناڵ نەدۆزرایەوە. | Channel not found.")

@bot.command(name="removelog", aliases=["unsetlog", "disablelog"])
@commands.has_permissions(manage_guild=True)
async def removelog(ctx):
    """Remove the log channel."""
    if ctx.guild is None:
        return await ctx.send("Server only. | تەنها لە سێرڤەر.")
    gid = str(ctx.guild.id)
    if gid in log_channels:
        del log_channels[gid]
        save_log_channels()
        await ctx.send("✅ کەناڵی لۆگ لابرا. | Log channel removed.")
    else:
        await ctx.send("هیچ کەناڵی لۆگ دانەنرابوو. | No log channel was set.")

@removelog.error
async def removelog_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ مووچەی Manage Server پێویستە. | You need Manage Server permission.")

@bot.command(name="logs", aliases=["logstatus", "loginfo"])
async def logs_cmd(ctx):
    """Show current log channel status."""
    if ctx.guild is None:
        return await ctx.send("Server only. | تەنها لە سێرڤەر.")
    gid = str(ctx.guild.id)
    cid = log_channels.get(gid)
    ch = ctx.guild.get_channel(int(cid)) if cid else None
    e = discord.Embed(
        color=0x5865F2,
        title="📋 دۆخی سیستەمی لۆگ | Log System Status",
    )
    if ch:
        e.add_field(name="📌 کەناڵی لۆگ | Log Channel", value=ch.mention, inline=True)
        e.add_field(name="🟢 دۆخ | Status", value="چالاک | Active", inline=True)
        e.add_field(
            name="📊 چی تۆمار دەکرێت | Logged Events",
            value=(
                "✅ Join/Leave · 🗑️ Message Delete\n"
                "✏️ Message Edit · 🔨 Ban/Unban\n"
                "📝 Nickname · 🎭 Roles · 📁 Channels"
            ),
            inline=False,
        )
    else:
        e.add_field(name="🔴 دۆخ | Status", value="ناچالاک | Inactive", inline=True)
        e.add_field(name="💡 چۆن چالاک بکەیت | How to enable",
                    value="`!setlog #channel`", inline=True)
    e.set_footer(text=ctx.guild.name)
    await ctx.send(embed=e)

# ═══════════════════════ REACTION ROLES ═══════════════════════


# ─── EMOJI REACTION SELF-ROLE COMMANDS ───────────────────────────────────────

@bot.command(name="setselfrole", aliases=["selfroleset", "srset"])
@commands.has_permissions(manage_roles=True)
async def setselfrole(ctx, channel: discord.TextChannel = None, *, args: str = None):
    target_ch = channel or ctx.channel
    if not args:
        e = discord.Embed(color=0x5865F2, title="📋 $setselfrole — چۆنیەتی بەکارهێنان / How to use")
        e.description = (
            "**فۆرمات / Format:**\n"
            "`!setselfrole [#channel] <title> | emoji @role | emoji @role | ...`\n\n"
            "**نموونە / Example:**\n"
            "`!setselfrole #roles دەستبژاردنی رۆڵ | 🎮 @Gamer | 🎵 @Music | 🎨 @Art`\n\n"
            "ئەندامان ری‌ئاکت دەکەن بۆ وەرگرتن یان لادانی رۆڵ.\n"
            "Members react below to get or remove a role.\n\n"
            "• تا **20** رۆڵ / Up to **20** roles per panel\n"
            "• [#channel] ئارەزووییە / optional — defaults to this channel"
        )
        return await ctx.send(embed=e)

    parts = [p.strip() for p in args.split("|")]
    if len(parts) < 2:
        return await ctx.send(
            "❌ دەبێت لانیکەم یەک ری‌ئاکت زیاد بکەیت بە `|` جیاکردنەوە.\n"
            "❌ Add at least one emoji-role pair separated by `|`.\n"
            "Example: `!setselfrole #roles Title | 🎮 @Gamer`",
            delete_after=15
        )

    title_text = parts[0]
    entries = []
    errors  = []

    for entry in parts[1:]:
        tokens = entry.strip().split()
        if len(tokens) < 2:
            errors.append(f"⚠️ `{entry}` — دەبێت emoji + @role هەبێت")
            continue
        emoji_raw = tokens[0]
        role_obj  = None
        for tok in tokens[1:]:
            if tok.startswith("<@&") or tok.startswith("<@"):
                rid = int("".join(filter(str.isdigit, tok)))
                role_obj = ctx.guild.get_role(rid)
                break
        if not role_obj:
            role_name = " ".join(t for t in tokens[1:] if not t.startswith("<@")).strip()
            role_obj  = discord.utils.get(ctx.guild.roles, name=role_name)
        if not role_obj:
            errors.append(f"⚠️ رۆڵەکە نەدۆزرایەوە: `{entry}`")
            continue
        if any(e == emoji_raw for e, _ in entries):
            errors.append(f"⚠️ ئەم ری‌ئاکتە پێشتر زیادکراوە: `{emoji_raw}`")
            continue
        entries.append((emoji_raw, role_obj))

    if not entries:
        return await ctx.send(
            "❌ هیچ رۆڵێکی دروست نەدۆزرایەوە. / No valid roles found.",
            delete_after=12
        )

    entries = entries[:20]

    desc_lines = [
        "ری‌ئاکت بکە بۆ وەرگرتن یان لادانی رۆڵ! 👇",
        "React below to get or remove a role! 👇",
        "",
    ]
    for emoji_raw, role_obj in entries:
        desc_lines.append(f"{emoji_raw} → {role_obj.mention}")

    panel_embed = discord.Embed(
        color=0x5865F2,
        title=f"🎭 {title_text}",
        description="\n".join(desc_lines),
    )
    panel_embed.set_footer(text=f"{ctx.guild.name} • Self-Role Panel | پانێڵی دەستبژاردنی رۆڵ")

    msg = await target_ch.send(embed=panel_embed)

    for emoji_raw, _ in entries:
        try:
            await msg.add_reaction(emoji_raw)
        except (discord.HTTPException, discord.InvalidArgument):
            errors.append(f"⚠️ ری‌ئاکت زیادنەکرا (ئیمۆجی نادروست؟): `{emoji_raw}`")

    _save_selfrole_panel(ctx.guild.id, msg.id, target_ch.id, title_text)
    selfrole_map[msg.id] = {}
    for emoji_raw, role_obj in entries:
        _save_selfrole_entry(ctx.guild.id, msg.id, emoji_raw, role_obj.id)
        selfrole_map[msg.id][emoji_raw] = role_obj.id

    confirm = discord.Embed(
        color=0x57F287,
        title="✅ پانێڵی رۆڵ دروستکرا! / Self-Role Panel Created!",
    )
    confirm.description = (
        f"پانێلەکەت نێردرا بۆ {target_ch.mention} 🎉\n"
        f"Panel sent to {target_ch.mention} 🎉\n\n"
        f"**{len(entries)}** رۆڵ زیادکرا / roles added\n\n"
        f"[🔗 Jump to panel]({msg.jump_url})"
    )
    if errors:
        confirm.add_field(name="⚠️ ئاگاداریەکان / Warnings", value="\n".join(errors), inline=False)
    await ctx.send(embed=confirm, delete_after=30)


@setselfrole.error
async def setselfrole_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ مووچەی Manage Roles پێویستە. | You need Manage Roles permission.")
    elif isinstance(error, commands.ChannelNotFound):
        await ctx.send("❌ کەناڵ نەدۆزرایەوە. | Channel not found.")

@bot.command(name="reactionroles", aliases=["selfroles", "rrlist"])
async def reactionroles(ctx):
    panels = _get_selfrole_panels(ctx.guild.id)
    if not panels:
        return await ctx.send(
            "❌ هیچ پانێڵی دەستبژاردنی رۆڵێک دامەزراو نییە.\n"
            "❌ No self-role panels set up in this server.\n"
            "Admins can use `!setselfrole` to create one.",
            delete_after=15
        )

    embed = discord.Embed(
        color=0x5865F2,
        title=f"🎭 پانێڵەکانی دەستبژاردنی رۆڵ / Self-Role Panels ({len(panels)})",
    )
    embed.description = (
        "ری‌ئاکت بکە لەسەر ئیمۆجیەکانی پانێلەکان بۆ وەرگرتنی رۆڵ!\n"
        "React on the panel messages below to get your roles!"
    )

    for mid, info in list(panels.items())[:10]:
        ch = ctx.guild.get_channel(info["channel_id"])
        role_lines = []
        for emoji, rid in info["entries"][:8]:
            role = ctx.guild.get_role(rid)
            role_lines.append(f"{emoji} {role.mention if role else f'<@&{rid}>'}")
        if len(info["entries"]) > 8:
            role_lines.append(f"+{len(info['entries'])-8} more...")
        link = f"https://discord.com/channels/{ctx.guild.id}/{info['channel_id']}/{mid}"
        embed.add_field(
            name=f"🔹 {info['title']}",
            value=(
                f"📍 {ch.mention if ch else 'unknown channel'}\n"
                + "\n".join(role_lines)
                + f"\n[🔗 Jump to panel]({link})"
            ),
            inline=False,
        )

    embed.set_footer(text=f"{ctx.guild.name} • {len(panels)} active panel(s)")
    await ctx.send(embed=embed)


@bot.command(name="removeselfrole", aliases=["delselfrole", "srdelete"])
@commands.has_permissions(manage_roles=True)
async def removeselfrole(ctx, message_id: int = None):
    if not message_id:
        return await ctx.send(
            "❌ تکایە message ID ی پانێلەکە بنووسە. / Provide the panel message ID.\n"
            "`!removeselfrole <message_id>`",
            delete_after=10
        )
    if message_id not in selfrole_map:
        return await ctx.send(
            "❌ پانێلێک بەو ناسنامەیە نەدۆزرایەوە. / No panel found with that ID.",
            delete_after=10
        )
    _delete_selfrole_panel(message_id)
    selfrole_map.pop(message_id, None)
    await ctx.send(
        f"✅ پانێڵی رۆڵ بە ناسنامەی `{message_id}` سڕایەوە.\n"
        f"✅ Self-role panel `{message_id}` deleted.",
        delete_after=15
    )



@removeselfrole.error
async def removeselfrole_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ مووچەی Manage Roles پێویستە. | You need Manage Roles permission.")

# ════════════════════════════════════════════════════════
#   NEW REACTION ROLE SYSTEM  (!reactionrole + !setupreaction)
# ════════════════════════════════════════════════════════

class SetupReactionRoleSelect(discord.ui.RoleSelect):
    def __init__(self):
        super().__init__(
            placeholder="هەڵبژێرە رۆڵەکانی دەتەوێت | Choose the roles you want...",
            min_values=1,
            max_values=10,
        )

    async def callback(self, interaction: discord.Interaction):
        self.view.selected_roles = list(self.values)
        role_list = ", ".join(f"**{r.name}**" for r in self.values)
        await interaction.response.edit_message(
            embed=discord.Embed(
                color=0x5865F2,
                title="🎭 دامەزراندنی رۆڵی ئەکتیڤ | Reaction Role Setup",
                description=(
                    f"\u2705 **{len(self.values)}** \u0631\u06c6\u06b5 \u0647\u06d5\u06b5\u0628\u0698\u06ce\u0631\u062f\u0631\u0627 | roles selected:\n"
                    + role_list
                    + "\n\n\u062f\u0648\u06af\u0645\u06d5\u06cc **Confirm** \u0628\u06a9\u06d5 \u0628\u06c6 \u062f\u0631\u0648\u0633\u062a\u06a9\u0631\u062f\u0646\u06cc \u067e\u0627\u0646\u06ce\u0644.\n"
                    "Click **Confirm** to create the panel."
                ),
            ),
            view=self.view,
        )


class SetupReactionView(discord.ui.View):
    def __init__(self, ctx, channel, title):
        super().__init__(timeout=120)
        self.ctx = ctx
        self.channel = channel
        self.title = title
        self.selected_roles = []
        self.add_item(SetupReactionRoleSelect())

    @discord.ui.button(label="\u2705 Confirm & Create", style=discord.ButtonStyle.success, row=1)
    async def confirm_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message(
                "\u274c \u0626\u06d5\u0645 \u0633\u062a\u06d5\u067e\u06d5\u06a9\u06d5 \u0628\u06c6 \u062a\u06c6 \u0646\u06cc\u06cc\u06d5. | This setup is not yours.",
                ephemeral=True,
            )
        if not self.selected_roles:
            return await interaction.response.send_message(
                "\u274c \u062a\u06a9\u0627\u06cc\u06d5 \u06cc\u06d5\u06a9 \u0631\u06c6\u06b5 \u0647\u06d5\u06b5\u0628\u0698\u06ce\u0631\u06d5. | Please select at least one role first.",
                ephemeral=True,
            )
        emojis = ["\u0031\ufe0f\u20e3","\u0032\ufe0f\u20e3","\u0033\ufe0f\u20e3","\u0034\ufe0f\u20e3","\u0035\ufe0f\u20e3",
                  "\u0036\ufe0f\u20e3","\u0037\ufe0f\u20e3","\u0038\ufe0f\u20e3","\u0039\ufe0f\u20e3","\U0001f51f"]
        desc_lines = [
            "\u0631\u06cc\u0626\u0627\u06a9\u062a \u0628\u06a9\u06d5 \u0628\u06c6 \u0648\u06d5\u0631\u06af\u0631\u062a\u0646/\u0644\u0627\u062f\u0627\u0646\u06cc \u0631\u06c6\u06b5! \U0001f447",
            "Click a button to get or remove a role! \U0001f447",
            "",
        ]
        for i, role in enumerate(self.selected_roles):
            desc_lines.append(f"{emojis[i]} \u2192 {role.mention}")
        panel_embed = discord.Embed(
            color=0x5865F2,
            title=f"\U0001f3ad {self.title}",
            description="\n".join(desc_lines),
        )
        panel_embed.set_footer(text=f"{self.ctx.guild.name} \u2022 Reaction Roles | \u0631\u06c6\u06b5\u06cc \u0626\u06d5\u06a9\u062a\u06cc\u06a4")
        if self.ctx.guild.icon:
            panel_embed.set_thumbnail(url=self.ctx.guild.icon.url)
        buttons = [(role.id, emojis[i], role.name) for i, role in enumerate(self.selected_roles)]
        msg = await self.channel.send(embed=panel_embed)
        real_view = ReactionRoleView(msg.id, buttons)
        bot.add_view(real_view)
        await msg.edit(view=real_view)
        rr_data[msg.id] = buttons
        _save_rr_panel(self.ctx.guild.id, self.channel.id, msg.id, self.title, "")
        for role_id, emoji, label in buttons:
            _save_rr_button(msg.id, role_id, emoji, label)
        done_embed = discord.Embed(
            color=0x57F287,
            title="\u2705 \u067e\u0627\u0646\u06ce\u0644\u06cc \u0631\u06c6\u06b5\u06cc \u0626\u06d5\u06a9\u062a\u06cc\u06a4 \u062f\u0631\u0648\u0633\u062a\u06a9\u0631\u0627! | Reaction Role Panel Created!",
            description=(
                f"\u067e\u0627\u0646\u06ce\u0644\u06d5\u06a9\u06d5\u062a \u0646\u06ce\u0631\u062f\u0631\u0627 \u0628\u06c6 {self.channel.mention} \U0001f389\n"
                f"Panel sent to {self.channel.mention} \U0001f389\n\n"
                f"**{len(self.selected_roles)}** \u0631\u06c6\u06b5 \u0632\u06cc\u0627\u062f\u06a9\u0631\u0627 | roles added\n\n"
                f"[\U0001f517 Jump to panel]({msg.jump_url})"
            ),
        )
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(embed=done_embed, view=self)
        self.stop()

    @discord.ui.button(label="\u274c Cancel", style=discord.ButtonStyle.danger, row=1)
    async def cancel_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message(
                "\u274c \u0626\u06d5\u0645 \u0633\u062a\u06d5\u067e\u06d5\u06a9\u06d5 \u0628\u06c6 \u062a\u06c6 \u0646\u06cc\u06cc\u06d5. | This setup is not yours.",
                ephemeral=True,
            )
        await interaction.response.edit_message(
            embed=discord.Embed(
                color=0xED4245,
                title="\u274c \u0647\u06d5\u06b5\u0648\u06d5\u0634\u0627\u0646\u062f\u06d5\u0648\u06d5 | Cancelled",
                description=(
                    "\u062f\u0627\u0645\u06d5\u0632\u0631\u0627\u0646\u062f\u0646\u06cc \u0631\u06c6\u06b5\u06cc \u0626\u06d5\u06a9\u062a\u06cc\u06a4 \u0647\u06d5\u06b5\u0648\u06d5\u0634\u0627\u06cc\u06d5\u0648\u06d5.\n"
                    "Reaction role setup was cancelled."
                ),
            ),
            view=None,
        )
        self.stop()


@bot.command(name="setupreaction", aliases=["reactionsetup", "rsetup"])
@commands.has_permissions(manage_roles=True)
async def setupreaction_cmd(ctx, channel: discord.TextChannel = None, *, title: str = "\U0001f3ad Reaction Roles"):
    if ctx.guild is None:
        return await ctx.send("Server only. | \u062a\u06d5\u0646\u0647\u0627 \u0644\u06d5 \u0633\u06ce\u0631\u06a4\u06d5\u0631.")
    target = channel or ctx.channel
    view = SetupReactionView(ctx, target, title)
    embed = discord.Embed(
        color=0x5865F2,
        title="\U0001f3ad \u062f\u0627\u0645\u06d5\u0632\u0631\u0627\u0646\u062f\u0646\u06cc \u0631\u06c6\u06b5\u06cc \u0626\u06d5\u06a9\u062a\u06cc\u06a4 | Reaction Role Setup",
        description=(
            f"**\u06a9\u06d5\u0646\u0627\u06b5 | Channel:** {target.mention}\n"
            f"**\u0646\u0627\u0648\u0646\u06cc\u0634\u0627\u0646 | Title:** {title}\n\n"
            "\u2b07\ufe0f \u0644\u06d5 \u0645\u06ce\u0646\u06cc\u0648\u06cc \u062e\u0648\u0627\u0631\u06d5\u0648\u06d5 \u0631\u06c6\u06b5\u06d5\u06a9\u0627\u0646\u06cc \u062f\u06d5\u062a\u06d5\u0648\u06ce\u062a \u0647\u06d5\u06b5\u0628\u0698\u06ce\u0631\u06d5\u060c \u062f\u0648\u0627\u062a\u0631 **Confirm** \u06a9\u0644\u06cc\u06a9 \u0628\u06a9\u06d5.\n"
            "\u2b07\ufe0f Pick the roles from the dropdown below, then click **Confirm**."
        ),
    )
    if ctx.guild.icon:
        embed.set_thumbnail(url=ctx.guild.icon.url)
    embed.set_footer(text=f"Setup by {ctx.author.display_name} \u2022 expires in 2 min")
    await ctx.send(embed=embed, view=view)

@setupreaction_cmd.error
async def setupreaction_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ مووچەی Manage Roles پێویستە. | You need Manage Roles permission.")
    elif isinstance(error, commands.ChannelNotFound):
        await ctx.send("❌ کەناڵەکە نەدۆزرایەوە. | Channel not found.")


@bot.command(name="reactionselect", aliases=["selectrole", "roleselect"])
@commands.has_permissions(manage_roles=True)
async def reactionselect_cmd(ctx, channel: discord.TextChannel = None, *, title: str = "🎭 Select Your Role"):
    """Interactive reaction role setup — pick roles from a dropdown, then confirm."""
    if ctx.guild is None:
        return await ctx.send("Server only. | تەنها لە سێرڤەر.")
    target = channel or ctx.channel
    view = SetupReactionView(ctx, target, title)
    embed = discord.Embed(
        color=0x5865F2,
        title="🎭 Select Your Role | هەڵبژاردنی رۆڵ",
        description=(
            f"**Channel:** {target.mention}\n"
            f"**Panel Title:** {title}\n\n"
            "⬇️ **Pick the roles** you want from the dropdown below.\n"
            "You can select up to **10 roles** at once.\n"
            "Then click ✅ **Confirm & Create** to publish the panel.\n\n"
            "⬇️ **هەڵبژێرە رۆڵەکان** لە مێنیوی خوارەوە.\n"
            "دواتر ✅ **Confirm** کلیک بکە بۆ دروستکردنی پانێل."
        ),
    )
    if ctx.guild.icon:
        embed.set_thumbnail(url=ctx.guild.icon.url)
    embed.set_footer(text=f"Setup by {ctx.author.display_name} • expires in 2 min")
    await ctx.send(embed=embed, view=view)

@reactionselect_cmd.error
async def reactionselect_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ مووچەی Manage Roles پێویستە. | You need Manage Roles permission.")


@bot.command(name="reactionrole", aliases=["rrpanel", "makereaction"])
@commands.has_permissions(manage_roles=True)
async def reactionrole_cmd(ctx, channel: discord.TextChannel = None, *, args: str = None):
    if ctx.guild is None:
        return await ctx.send("Server only. | \u062a\u06d5\u0646\u0647\u0627 \u0644\u06d5 \u0633\u06ce\u0631\u06a4\u06d5\u0631.")
    if not args:
        embed = discord.Embed(
            color=0x5865F2,
            title="\U0001f3ad !reactionrole \u2014 \u0686\u06c6\u0646\u06cc\u06d5\u062a\u06cc \u0628\u06d5\u06a9\u0627\u0631\u0647\u06ce\u0646\u0627\u0646 | How to Use",
            description=(
                "**\u0641\u06c6\u0631\u0645\u0627\u062a / Format:**\n"
                "`!reactionrole [#channel] <Title> | @role1 | @role2 | @role3`\n\n"
                "**\u0646\u0645\u0648\u0648\u0646\u06d5 / Example:**\n"
                "`!reactionrole #roles \u062f\u06d5\u0633\u062a\u0628\u0698\u0627\u0631\u062f\u0646\u06cc \u0631\u06c6\u06b5 | @Gamer | @Music | @Art`\n\n"
                "\u06cc\u0627\u0646 \u062f\u0627\u0645\u06d5\u0632\u0631\u0627\u0648\u06d5\u06cc \u062a\u0627\u0642\u06cc\u06a9\u0631\u062f\u0646\u06d5\u0648\u06d5\u06cc \u0626\u06cc\u0646\u062a\u06d5\u0631\u0627\u06a9\u062a\u06cc\u06a4:\n"
                "Or use the interactive picker:\n"
                "`!setupreaction [#channel] [title]`"
            ),
        )
        return await ctx.send(embed=embed)
    target = channel or ctx.channel
    parts = [p.strip() for p in args.split("|")]
    if len(parts) < 2:
        return await ctx.send(
            "\u274c \u062f\u06d5\u0628\u06ce\u062a \u0644\u0627\u0646\u06cc\u06a9\u06d5\u0645 \u06cc\u06d5\u06a9 \u0631\u06c6\u06b5 \u0632\u06cc\u0627\u062f \u0628\u06a9\u06d5\u06cc\u062a. / Need at least one role.\n"
            "Example: `!reactionrole #roles Title | @Gamer | @Music`",
            delete_after=15,
        )
    title_text = parts[0].strip()
    emojis = ["\u0031\ufe0f\u20e3","\u0032\ufe0f\u20e3","\u0033\ufe0f\u20e3","\u0034\ufe0f\u20e3","\u0035\ufe0f\u20e3",
              "\u0036\ufe0f\u20e3","\u0037\ufe0f\u20e3","\u0038\ufe0f\u20e3","\u0039\ufe0f\u20e3","\U0001f51f"]
    roles_found = []
    errors = []
    for part in parts[1:11]:
        part_stripped = part.strip()
        role_obj = None
        rid_m = re.search(r'<@&(\d+)>', part_stripped)
        if rid_m:
            role_obj = ctx.guild.get_role(int(rid_m.group(1)))
        if not role_obj:
            role_obj = discord.utils.get(ctx.guild.roles, name=part_stripped.lstrip('@'))
        if not role_obj:
            errors.append(f"\u26a0\ufe0f \u0631\u06c6\u06b5 \u0646\u06d5\u062f\u06c6\u0632\u0631\u0627\u06cc\u06d5\u0648\u06d5: `{part_stripped}`")
            continue
        if any(r.id == role_obj.id for r in roles_found):
            continue
        roles_found.append(role_obj)
    if not roles_found:
        return await ctx.send(
            "\u274c \u0647\u06cc\u0686 \u0631\u06c6\u06b5\u06ce\u06a9\u06cc \u062f\u0631\u0648\u0633\u062a \u0646\u06d5\u062f\u06c6\u0632\u0631\u0627\u06cc\u06d5\u0648\u06d5. / No valid roles found.",
            delete_after=12,
        )
    desc_lines = [
        "\u062f\u0648\u06af\u0645\u06d5\u06cc\u06d5\u06a9 \u06a9\u0644\u06cc\u06a9 \u0628\u06a9\u06d5 \u0628\u06c6 \u0648\u06d5\u0631\u06af\u0631\u062a\u0646/\u0644\u0627\u062f\u0627\u0646\u06cc \u0631\u06c6\u06b5! \U0001f447",
        "Click a button to get or remove a role! \U0001f447",
        "",
    ]
    for i, role in enumerate(roles_found):
        desc_lines.append(f"{emojis[i]} \u2192 {role.mention}")
    panel_embed = discord.Embed(
        color=0x5865F2,
        title=f"\U0001f3ad {title_text}",
        description="\n".join(desc_lines),
    )
    panel_embed.set_footer(text=f"{ctx.guild.name} \u2022 Reaction Roles | \u0631\u06c6\u06b5\u06cc \u0626\u06d5\u06a9\u062a\u06cc\u06a4")
    if ctx.guild.icon:
        panel_embed.set_thumbnail(url=ctx.guild.icon.url)
    buttons = [(role.id, emojis[i], role.name) for i, role in enumerate(roles_found)]
    msg = await target.send(embed=panel_embed)
    real_view = ReactionRoleView(msg.id, buttons)
    bot.add_view(real_view)
    await msg.edit(view=real_view)
    rr_data[msg.id] = buttons
    _save_rr_panel(ctx.guild.id, target.id, msg.id, title_text, "")
    for role_id, emoji, label in buttons:
        _save_rr_button(msg.id, role_id, emoji, label)
    confirm = discord.Embed(
        color=0x57F287,
        title="\u2705 \u067e\u0627\u0646\u06ce\u0644\u06cc \u0631\u06c6\u06b5\u06cc \u0626\u06d5\u06a9\u062a\u06cc\u06a4 \u062f\u0631\u0648\u0633\u062a\u06a9\u0631\u0627! | Panel Created!",
        description=(
            f"\u067e\u0627\u0646\u06ce\u0644\u06d5\u06a9\u06d5\u062a \u0646\u06ce\u0631\u062f\u0631\u0627 \u0628\u06c6 {target.mention} \U0001f389\n"
            f"Panel sent to {target.mention} \U0001f389\n\n"
            f"**{len(roles_found)}** \u0631\u06c6\u06b5 \u0632\u06cc\u0627\u062f\u06a9\u0631\u0627 | roles added\n\n"
            f"[\U0001f517 Jump to panel]({msg.jump_url})"
        ),
    )
    if errors:
        confirm.add_field(name="\u26a0\ufe0f \u0626\u0627\u06af\u0627\u062f\u0627\u0631\u06cc\u06d5\u06a9\u0627\u0646 | Warnings", value="\n".join(errors), inline=False)
    await ctx.send(embed=confirm, delete_after=30)

@reactionrole_cmd.error
async def reactionrole_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("\u274c \u0645\u0648\u0648\u0686\u06d5\u06cc Manage Roles \u067e\u06ce\u0648\u06cc\u0633\u062a\u06d5. | You need Manage Roles permission.")


_RR_BUTTON_STYLES = [
    discord.ButtonStyle.blurple,
    discord.ButtonStyle.green,
    discord.ButtonStyle.red,
    discord.ButtonStyle.grey,
    discord.ButtonStyle.blurple,
    discord.ButtonStyle.green,
    discord.ButtonStyle.red,
    discord.ButtonStyle.grey,
    discord.ButtonStyle.blurple,
    discord.ButtonStyle.green,
]

class ReactionRoleButton(discord.ui.Button):
    def __init__(self, role_id: int, emoji: str, label: str, message_id: int, index: int = 0):
        super().__init__(
            style=_RR_BUTTON_STYLES[index % len(_RR_BUTTON_STYLES)],
            label=label or None,
            emoji=emoji or None,
            custom_id=f"rr_{message_id}_{role_id}",
        )
        self.role_id = role_id

    async def callback(self, interaction: discord.Interaction):
        role = interaction.guild.get_role(self.role_id)
        if role is None:
            return await interaction.response.send_message(
                "❌ رۆڵەکە نەدۆزرایەوە. | Role not found.", ephemeral=True
            )
        try:
            if role in interaction.user.roles:
                await interaction.user.remove_roles(role, reason="Reaction Role")
                await interaction.response.send_message(
                    f"✅ رۆڵی **{role.name}** لە تۆ لابرا. | Role **{role.name}** removed.",
                    ephemeral=True,
                )
            else:
                await interaction.user.add_roles(role, reason="Reaction Role")
                await interaction.response.send_message(
                    f"🎭 رۆڵی **{role.name}** بە تۆ درا. | Role **{role.name}** added.",
                    ephemeral=True,
                )
        except discord.Forbidden:
            msg = "❌ بۆتەکە مووچەی دانی رۆڵی نییە. | Bot lacks permission to assign this role."
            if interaction.response.is_done():
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)


class ReactionRoleView(discord.ui.View):
    def __init__(self, message_id: int, buttons: list):
        super().__init__(timeout=None)
        for i, (role_id, emoji, label) in enumerate(buttons):
            self.add_item(ReactionRoleButton(role_id, emoji, label, message_id, index=i))


@bot.command(aliases=["leaderboard", "lb"])
async def top(ctx, category: str = "total"):
    if ctx.guild is None:
        await ctx.send("This command can only be used in a server. | ئەم فەرمانە تەنها لە سێرڤەر دەکرێت بەکارهێنرێت.")
        return

    category = category.lower()
    if category not in ("total", "message", "messages", "text", "voice"):
        await ctx.send("Usage: `!top [total|message|voice]` | بەکارهێنان: `!top [total|message|voice]`")
        return

    if category in ("message", "messages", "text"):
        key_fn = lambda kv: kv[1].get("message_xp", 0)
        title = "💬 Top Players — Message XP | باڵاترین یاریزانان - XP پەیام"
        color = discord.Color.blue()
    elif category == "voice":
        key_fn = lambda kv: kv[1].get("voice_xp", 0)
        title = "🎙️ Top Players — Voice XP | باڵاترین یاریزانان - XP دەنگ"
        color = discord.Color.purple()
    else:
        key_fn = lambda kv: kv[1].get("message_xp", 0) + kv[1].get("voice_xp", 0)
        title = "🏆 Top Players — Total XP | باڵاترین یاریزانان - کۆی گشتی XP"
        color = discord.Color.gold()

    guild_data = xp_data.get(str(ctx.guild.id), {})
    sorted_users = sorted(guild_data.items(), key=key_fn, reverse=True)
    sorted_users = [u for u in sorted_users if key_fn(u) > 0][:10]

    if not sorted_users:
        await ctx.send("No XP has been earned in this server yet. | هێشتا هیچ XP لەم سێرڤەرە کەسب نەکراوە.")
        return

    medals = ["🥇", "🥈", "🥉"]
    lines = []
    for i, (uid, entry) in enumerate(sorted_users):
        member = ctx.guild.get_member(int(uid))
        name = member.display_name if member else f"User {uid}"
        msg_xp = entry.get("message_xp", 0)
        voice_xp_val = entry.get("voice_xp", 0)
        total = msg_xp + voice_xp_val
        lvl = level_from_xp(total)
        prefix = medals[i] if i < 3 else f"`#{i + 1}`"
        icon = level_icon(lvl)
        lines.append(
            f"{prefix} **{name}** — {icon} Lvl **{lvl}** · `{total:,}` XP\n"
            f"> 💬 `{msg_xp:,}` · 🎙️ `{voice_xp_val:,}`"
        )
    embed = discord.Embed(
        title=title,
        description="\n\n".join(lines),
        color=color,
        timestamp=datetime.datetime.utcnow(),
    )
    embed.set_footer(text=f"!top total | message | voice  •  {ctx.guild.name}")
    await ctx.send(embed=embed)

# --- MODERATION COMMANDS ---

@bot.command()
async def ping(ctx):
    latency_ms = round(bot.latency * 1000)
    if latency_ms < 100:
        color, bar = 0x57f287, "🟩🟩🟩🟩🟩"
    elif latency_ms < 200:
        color, bar = 0xfee75c, "🟨🟨🟨⬛⬛"
    else:
        color, bar = 0xed4245, "🟥🟥⬛⬛⬛"
    embed = discord.Embed(
        title="🏓 Pong!",
        description=(
            "### ⚡ Bot Latency | خێرایی بۆت\n"
            f"`{latency_ms}ms` {bar}"
        ),
        color=color,
    )
    embed.set_footer(text="discord.py • WebSocket latency | خێرایی WebSocket")
    await ctx.send(embed=embed)

@bot.command(aliases=["av", "pfp", "icon"])
async def avatar(ctx, member: discord.Member = None):
    member = member or ctx.author
    embed = discord.Embed(
        title=f"{member.display_name}'s Avatar | ئاڤاتاری {member.display_name}",
        color=discord.Color.blurple(),
    )
    embed.set_image(url=member.display_avatar.url)
    embed.set_footer(text=f"ID: {member.id}")
    await ctx.send(embed=embed)


async def _animequiz_runner(channel, char_name, image_url, msg):
    """Count down 15s updating footer only — name stays hidden until guessed."""
    try:
        for secs_left in range(15, 0, -1):
            if channel.id not in anime_quizzes:
                return
            countdown_embed = discord.Embed(
                title="🤔 کێ ئەم کارەکتەرە دەناسیتەوە؟ / Who is this character?",
                description=(
                    "خێراترین کەس داوی کارەکتەرمکە بنووسێت!\n"
                    "Be the first to type the character's name in chat!"
                ),
                color=discord.Color.from_rgb(114, 137, 218)
            )
            countdown_embed.set_image(url=image_url)
            countdown_embed.set_footer(
                text=f"⏳ {secs_left} چرکەت لەبەردەستە... / {secs_left} seconds remaining..."
            )
            try:
                await msg.edit(embed=countdown_embed)
            except Exception:
                pass
            await asyncio.sleep(1)

        quiz = anime_quizzes.pop(channel.id, None)
        if quiz:
            timeout_embed = discord.Embed(
                title="⏰ ماوەکەت تەواو بوو! / Time's Up!",
                description=(
                    f"کەس وەڵامی دروست نەدا! 😔\n"
                    f"ناوی ڕاستەقینەی کارەکتەرەکە: **{char_name}** بوو!\n\n"
                    f"Nobody got it right! 😔\n"
                    f"The character was **{char_name}**!"
                ),
                color=discord.Color.red()
            )
            timeout_embed.set_image(url=image_url)
            timeout_embed.set_footer(text="Type $animequiz to play again! / $animequiz بنووسە بۆ دووبارە یاریکردن!")
            try:
                await msg.edit(embed=timeout_embed)
            except Exception:
                await channel.send(embed=timeout_embed)
    except asyncio.CancelledError:
        pass

QUIZ_QUESTIONS = [
    {
        "question": "🇮🇶 پایتەختی عێراق چییە؟\n🇬🇧 What is the capital of Iraq?",
        "answer": "بەغداد",
        "alternates": ["baghdad", "بغداد"],
    },
    {
        "question": "🇮🇶 چەند ئەنگووشتی یەک دەست هەیە؟\n🇬🇧 How many fingers are on one hand?",
        "answer": "٥",
        "alternates": ["5", "پێنج", "five"],
    },
    {
        "question": "🇮🇶 خێرایی ڕووناکی چەندە (km/s)?\n🇬🇧 What is the speed of light (km/s)?",
        "answer": "300000",
        "alternates": ["٣٠٠٠٠٠", "300,000"],
    },
    {
        "question": "🇮🇶 گەورەترین ئەوقیانووسی جیهان چییە؟\n🇬🇧 What is the largest ocean in the world?",
        "answer": "ئۆقیانووسی ئاسیا",
        "alternates": ["pacific", "پاسیفیک", "ئاسیا"],
    },
    {
        "question": "🇮🇶 ١٢ × ١٢ چەندە؟\n🇬🇧 What is 12 × 12?",
        "answer": "144",
        "alternates": ["١٤٤"],
    },
    {
        "question": "🇮🇶 زمانی رەسمی کوردستان چییە؟\n🇬🇧 What is the official language of Kurdistan?",
        "answer": "کوردی",
        "alternates": ["kurdish", "kurdî"],
    },
    {
        "question": "🇮🇶 خۆر ستێرەیە یان گەیارەیە؟\n🇬🇧 Is the Sun a star or a planet?",
        "answer": "ستێرە",
        "alternates": ["star", "ستاره"],
    },
    {
        "question": "🇮🇶 چەند مانگی ساڵەکە هەیە؟\n🇬🇧 How many months are in a year?",
        "answer": "١٢",
        "alternates": ["12", "دوازده", "twelve"],
    },
    {
        "question": "🇮🇶 گەورەترین وڵاتی جیهان کامەیە؟\n🇬🇧 What is the largest country in the world?",
        "answer": "ڕووسیا",
        "alternates": ["russia", "روسیا"],
    },
    {
        "question": "🇮🇶 ئاوی کوێ ئاوی ژیانی زۆرترین ئاژەڵی دەریاییە؟\n🇬🇧 What is the largest animal in the ocean?",
        "answer": "نەهەنگی شین",
        "alternates": ["blue whale", "whale", "نهنگ"],
    },
]

async def _quiz_timeout(channel, q):
    """Auto-reveal answer after 2 minutes if nobody answers."""
    try:
        await asyncio.sleep(120)
        quiz = active_quizzes.pop(channel.id, None)
        if quiz:
            timeout_embed = discord.Embed(
                title="⌛ کات تەواو بوو! / Time's Up!",
                description=(
                    f"کەس وەڵامی دروست نەدا! 😔\n"
                    f"وەڵامی دروستەکە: **{q['answer']}**\n\n"
                    f"Nobody answered correctly! 😔\n"
                    f"The correct answer was: **{q['answer']}**"
                ),
                color=discord.Color.red()
            )
            await channel.send(embed=timeout_embed)
    except asyncio.CancelledError:
        pass

TF_STATEMENTS = [
    {
        "statement_ku": "دیواری گەورەی چین لە سەر مانگاوە بە چاوی ئاسایی دەبینرێت.",
        "statement_en": "The Great Wall of China can be seen from the moon with the naked eye.",
        "answer": False,
    },
    {
        "statement_ku": "ئاژەڵی هەیکەلی دەریایی (Seahorse) نێرەکەی دەژیێ نەک مێکەی.",
        "statement_en": "Male seahorses carry and give birth to babies, not females.",
        "answer": True,
    },
    {
        "statement_ku": "خۆر گەورەتر لە زەویە بە مامناوەند نزیک ١٠٩ جار.",
        "statement_en": "The Sun is about 109 times wider than Earth.",
        "answer": True,
    },
    {
        "statement_ku": "مرۆڤەکان تەنها ١٠٪ لە مێشکەکەیان بەکاردێنن.",
        "statement_en": "Humans only use 10% of their brains.",
        "answer": False,
    },
    {
        "statement_ku": "ئۆکتۆپوس سێ دل هەیە.",
        "statement_en": "An octopus has three hearts.",
        "answer": True,
    },
    {
        "statement_ku": "ئاو بەخۆی خۆی ئاگر دەگرێت.",
        "statement_en": "Water can catch fire on its own.",
        "answer": False,
    },
    {
        "statement_ku": "مانگا هێزی گرانجەذبەی خۆی هەیە.",
        "statement_en": "The Moon has its own gravitational pull.",
        "answer": True,
    },
    {
        "statement_ku": "فیل تەنها ئاژەڵێکە کە نەتوانیت باز بدات.",
        "statement_en": "Elephants are the only animals that cannot jump.",
        "answer": True,
    },
    {
        "statement_ku": "باڵندەکانی پینگوێن بازدەدەن.",
        "statement_en": "Penguins can fly.",
        "answer": False,
    },
    {
        "statement_ku": "خوێن لە مرۆڤدا شینە نەک سوور.",
        "statement_en": "Human blood is blue inside the body.",
        "answer": False,
    },
    {
        "statement_ku": "لازمانی کەلەچووی (Fingerprints) ناو دوو کەسدا یەکسان نییە.",
        "statement_en": "No two people have the same fingerprints.",
        "answer": True,
    },
    {
        "statement_ku": "ئاوی دەریا شیرین دەچێت.",
        "statement_en": "Ocean water is drinkable without treatment.",
        "answer": False,
    },
    {
        "statement_ku": "دۆشکەی کورمانجی (Bats) کۆرن.",
        "statement_en": "Bats are blind.",
        "answer": False,
    },
    {
        "statement_ku": "زەوی ستێرەیەکی بچووکە.",
        "statement_en": "Earth is a small star.",
        "answer": False,
    },
    {
        "statement_ku": "ئاژەڵی مار گوێی دەرەکی نییە.",
        "statement_en": "Snakes have no external ears.",
        "answer": True,
    },
]

async def _tf_timeout(channel, game):
    """Reveal answer after 60 seconds if nobody answers."""
    try:
        for secs_left in range(60, 0, -5):
            if channel.id not in tf_games:
                return
            try:
                countdown_embed = discord.Embed(
                    title="❓ راست یان چەوت؟ / True or False?",
                    description=(
                        f"کلژاکەم زانیاریەی خوارەوە ڕاستە یان چەوت؟\n"
                        f"Is the following statement true or false?\n\n"
                        f"🔊 **{game['statement_ku']}**\n"
                        f"🔊 **{game['statement_en']}**\n\n"
                        f"تەنها بنووسە: **راست** یان **چەوت**\n"
                        f"Just type: **True** or **False**"
                    ),
                    color=discord.Color.from_rgb(114, 137, 218)
                )
                countdown_embed.set_footer(
                    text=f"⏳ {secs_left} چرکەت لەبەردەستە... / {secs_left} seconds remaining..."
                )
                await game["msg"].edit(embed=countdown_embed)
            except Exception:
                pass
            await asyncio.sleep(5)

        tf_games.pop(channel.id, None)
        correct_label = "راست ✅" if game["answer"] else "چەوت ❌"
        correct_en     = "TRUE ✅"  if game["answer"] else "FALSE ❌"
        timeout_embed = discord.Embed(
            title="⏰ کات تەواو بوو! / Time's Up!",
            description=(
                f"کەس وەڵامی دروست نەدا! 😔\n"
                f"Nobody answered! 😔\n\n"
                f"✅ وەڵامی دروست: **{correct_label}**\n"
                f"✅ Correct answer: **{correct_en}**\n\n"
                f"📝 **{game['statement_ku']}**\n"
                f"📝 **{game['statement_en']}**"
            ),
            color=discord.Color.red()
        )
        timeout_embed.set_footer(text="Type $tf to play again! / $tf بنووسە بۆ دووبارە یاریکردن!")
        try:
            await game["msg"].edit(embed=timeout_embed)
        except Exception:
            await channel.send(embed=timeout_embed)
    except asyncio.CancelledError:
        pass

@bot.command(name="tf", aliases=["truefalse", "truorfalse"])
async def tf(ctx):
    if ctx.channel.id in tf_games:
        await ctx.send(
            "⚠️ یاری راست/چەوت بەردەوامە! وەڵامت بنووسە یان چاوەڕێ بکە.\n"
            "⚠️ A True/False game is already running! Answer or wait for it to end.",
            delete_after=8
        )
        return

    game_data = random.choice(TF_STATEMENTS)
    embed = discord.Embed(
        title="❓ راست یان چەوت؟ / True or False?",
        description=(
            f"کلژاکەم زانیاریەی خوارەوە ڕاستە یان چەوت؟\n"
            f"Is the following statement true or false?\n\n"
            f"🔊 **{game_data['statement_ku']}**\n"
            f"🔊 **{game_data['statement_en']}**\n\n"
            f"تەنها بنووسە: **راست** یان **چەوت**\n"
            f"Just type: **True** or **False**"
        ),
        color=discord.Color.from_rgb(114, 137, 218)
    )
    embed.set_footer(text="⏳ ٦٠ چرکەت لەبەردەستە... / 60 seconds remaining...")
    msg = await ctx.send(embed=embed)
    game_data = {**game_data, "msg": msg}
    task = asyncio.get_event_loop().create_task(_tf_timeout(ctx.channel, game_data))
    game_data["task"] = task
    tf_games[ctx.channel.id] = game_data

@bot.command(name="animequiz", aliases=["aq", "aquiz", "animeguess"])
async def animequiz(ctx):
    if ctx.channel.id in anime_quizzes:
        await ctx.send(
            "🎌 یاری ئەنیمەکویز بەردەوامە ئێرە! وەڵامت بنووسە یان چاوەڕێی کۆتایی پێهێنانی خۆکار بکە.\n"
            "🎌 An anime quiz is already running here! Type your answer or wait for it to end.",
            delete_after=8
        )
        return

    loading_embed = discord.Embed(
        title="🎌 ئەنیمەکویز / Anime Quiz",
        description="⏳ کارەکتەرەکە بارکردن... / Loading character...",
        color=discord.Color.blurple()
    )
    msg = await ctx.send(embed=loading_embed)

    char_name = None
    image_url = None
    try:
        async with aiohttp.ClientSession() as session:
            for _ in range(5):
                async with session.get(
                    "https://api.jikan.moe/v4/random/characters",
                    timeout=aiohttp.ClientTimeout(total=8)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        c    = data.get("data", {})
                        name = c.get("name", "")
                        imgs = c.get("images", {})
                        img  = (imgs.get("jpg",  {}).get("image_url") or
                                imgs.get("webp", {}).get("image_url") or "")
                        if name and img:
                            char_name = name
                            image_url = img
                            break
                await asyncio.sleep(0.4)
    except Exception:
        pass

    if not char_name or not image_url:
        err_embed = discord.Embed(
            title="❌ هەڵە / Error",
            description=(
                "نەتوانرا کارەکتەرێک بارکرێت، تکایە دوبارە هەوڵبدەرەوە.\n"
                "Could not load a character, please try again."
            ),
            color=discord.Color.red()
        )
        await msg.edit(embed=err_embed)
        return

    task = asyncio.get_event_loop().create_task(
        _animequiz_runner(ctx.channel, char_name, image_url, msg)
    )
    anime_quizzes[ctx.channel.id] = {
        "name": char_name,
        "image_url": image_url,
        "task": task,
        "msg": msg,
    }

@bot.command()
async def botinfo(ctx):
    total_members = sum(g.member_count or 0 for g in bot.guilds)
    uptime_str = fmt_uptime(int(time.time() - bot_start_time))
    embed = discord.Embed(
        title=f"⚙️ {bot.user.name}",
        description=(
            "A bilingual Kurdish | English Discord bot with XP, economy, games & more!\n"
            "بۆتی دوو زمانی کوردی | ئینگلیزی بۆ Discord بە XP، ئابووری، یاریەکان و زیاتر!"
        ),
        color=discord.Color.from_rgb(88, 101, 242),
        timestamp=datetime.datetime.utcnow(),
    )
    if bot.user.display_avatar:
        embed.set_thumbnail(url=bot.user.display_avatar.url)
    embed.add_field(name="🌐 Servers | سێرڤەرەکان", value=f"`{len(bot.guilds):,}`", inline=True)
    embed.add_field(name="👥 Total Members | کۆی ئەندامان", value=f"`{total_members:,}`", inline=True)
    embed.add_field(name="📡 Latency | خێرایی", value=f"`{round(bot.latency * 1000)}ms`", inline=True)
    embed.add_field(name="⏱️ Uptime | ماوەی چالاکی", value=f"`{uptime_str}`", inline=True)
    embed.add_field(name="📦 Library | کتێبخانە", value=f"`discord.py {discord.__version__}`", inline=True)
    embed.add_field(name="🔧 Prefix | پێشگر", value=f"`{bot.command_prefix}`", inline=True)
    embed.add_field(name="📜 Commands | فەرمانەکان", value=f"`{len(bot.commands):,}`", inline=True)
    embed.set_footer(text=f"Requested by {ctx.author.display_name}")
    await ctx.send(embed=embed)

@bot.command()
async def channelinfo(ctx, channel: discord.TextChannel = None):
    channel = channel or ctx.channel
    embed = discord.Embed(title=f"#{channel.name} - Channel Info | زانیاری کەناڵ")
    embed.add_field(name="ID", value=str(channel.id), inline=True)
    embed.add_field(name="Type | جۆر", value=str(channel.type), inline=True)
    embed.add_field(name="Created | دروستکراوە", value=channel.created_at.strftime("%B %d, %Y"), inline=True)
    if getattr(channel, "topic", None):
        embed.add_field(name="Topic | بابەت", value=channel.topic, inline=False)
    if getattr(channel, "category", None):
        embed.add_field(name="Category | پۆل", value=channel.category.name, inline=True)
    await ctx.send(embed=embed)

@bot.command(name="roles")
async def roles_cmd(ctx):
    if ctx.guild is None:
        await ctx.send("This command can only be used in a server. | ئەم فەرمانە تەنها لە سێرڤەر دەکرێت بەکارهێنرێت.")
        return
    role_list = [r.mention for r in reversed(ctx.guild.roles) if r.name != "@everyone"]
    if not role_list:
        await ctx.send("This server has no roles. | ئەم سێرڤەرە هیچ رۆڵێکی نییە.")
        return
    text = " ".join(role_list)
    if len(text) > 4000:
        text = text[:3997] + "..."
    embed = discord.Embed(title=f"Roles | رۆڵەکان ({len(role_list)})", description=text)
    await ctx.send(embed=embed)

@bot.command()
@commands.has_permissions(manage_messages=True)
async def say(ctx, *, message: str):
    try:
        await ctx.message.delete()
    except discord.Forbidden:
        pass
    await ctx.send(message)

@say.error
async def say_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("You need the Manage Messages permission to use this. | مووچەی بەڕێوەبردنی پەیامەکان پێویستە.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Usage: $say <message> | بەکارهێنان: $say <پەیام>")

@bot.command()
@commands.has_permissions(kick_members=True)
async def kick(ctx, member: discord.Member, *, reason: str = "No reason provided | هیچ هۆکارێک نەدراوە"):
    if member == ctx.author:
        await ctx.send("You cannot kick yourself. | ناتوانیت خۆت لەدەربکەیت.")
        return
    if member.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
        await ctx.send("You cannot kick someone with an equal or higher role. | ناتوانیت کەسێک لەدەربکەیت کە رۆڵی یەکسان یان بەرزتر هەیە.")
        return
    try:
        await member.kick(reason=reason)
        await ctx.send(f"Kicked {member.mention}. Reason: {reason} | {member.mention} لەدەرکرا. هۆکار: {reason}")
    except discord.Forbidden:
        await ctx.send("I don't have permission to kick that member. | مووچەم نییە ئەم ئەندامە لەدەربکەم.")

@kick.error
async def kick_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("You need the Kick Members permission. | مووچەی لەدەرکردنی ئەندامان پێویستە.")
    elif isinstance(error, commands.MemberNotFound):
        await ctx.send("Member not found. | ئەندام نەدۆزرایەوە.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Usage: $kick @member [reason] | بەکارهێنان: $kick @ئەندام [هۆکار]")

@bot.command()
@commands.has_permissions(ban_members=True)
async def ban(ctx, member: discord.Member, *, reason: str = "No reason provided | هیچ هۆکارێک نەدراوە"):
    if member == ctx.author:
        await ctx.send("You cannot ban yourself. | ناتوانیت خۆت بلۆک بکەیت.")
        return
    if member.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
        await ctx.send("You cannot ban someone with an equal or higher role. | ناتوانیت کەسێک بلۆک بکەیت کە رۆڵی یەکسان یان بەرزتر هەیە.")
        return
    try:
        await member.ban(reason=reason, delete_message_days=0)
        await ctx.send(f"Banned {member.mention}. Reason: {reason} | {member.mention} بلۆک کرا. هۆکار: {reason}")
    except discord.Forbidden:
        await ctx.send("I don't have permission to ban that member. | مووچەم نییە ئەم ئەندامە بلۆک بکەم.")

@ban.error
async def ban_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("You need the Ban Members permission. | مووچەی بلۆک کردنی ئەندامان پێویستە.")
    elif isinstance(error, commands.MemberNotFound):
        await ctx.send("Member not found. | ئەندام نەدۆزرایەوە.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Usage: $ban @member [reason] | بەکارهێنان: $ban @ئەندام [هۆکار]")

@bot.command()
@commands.has_permissions(ban_members=True)
async def unban(ctx, user_id: int, *, reason: str = "No reason provided | هیچ هۆکارێک نەدراوە"):
    try:
        user = await bot.fetch_user(user_id)
        await ctx.guild.unban(user, reason=reason)
        await ctx.send(f"Unbanned {user}. | بلۆکی {user} لادرا.")
    except discord.NotFound:
        await ctx.send("That user is not banned (or does not exist). | ئەم بەکارهێنەرە بلۆک نەکراوە (یان بوونی نییە).")
    except discord.Forbidden:
        await ctx.send("I don't have permission to unban users. | مووچەم نییە بلۆکی بەکارهێنەران بلادەم.")

@unban.error
async def unban_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("You need the Ban Members permission. | مووچەی بلۆک کردنی ئەندامان پێویستە.")
    elif isinstance(error, (commands.BadArgument, commands.MissingRequiredArgument)):
        await ctx.send("Usage: $unban <user_id> [reason] | بەکارهێنان: $unban <ناسنامەی بەکارهێنەر> [هۆکار]")

@bot.command()
@commands.has_permissions(moderate_members=True)
async def mute(ctx, member: discord.Member, minutes: int = 10, *, reason: str = "No reason provided | هیچ هۆکارێک نەدراوە"):
    if minutes < 1 or minutes > 40320:
        await ctx.send("Duration must be between 1 minute and 28 days (40320 minutes). | ماوە دەبێت لە نێوان ١ خولەک و ٢٨ رۆژ (40320 خولەک) بێت.")
        return
    until = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=minutes)
    try:
        await member.timeout(until, reason=reason)
        await ctx.send(f"Muted {member.mention} for {minutes} minute(s). Reason: {reason} | {member.mention} بێدەنگ کرا بۆ {minutes} خولەک. هۆکار: {reason}")
    except discord.Forbidden:
        await ctx.send("I don't have permission to time out that member. | مووچەم نییە ئەم ئەندامە بێدەنگ بکەم.")

@mute.error
async def mute_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("You need the Moderate Members permission. | مووچەی کونترۆڵی ئەندامان پێویستە.")
    elif isinstance(error, commands.MemberNotFound):
        await ctx.send("Member not found. | ئەندام نەدۆزرایەوە.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Usage: $mute @member [minutes] [reason] | بەکارهێنان: $mute @ئەندام [خولەک] [هۆکار]")

@bot.command()
@commands.has_permissions(moderate_members=True)
async def unmute(ctx, member: discord.Member):
    try:
        await member.timeout(None)
        await ctx.send(f"Unmuted {member.mention}. | بێدەنگیی {member.mention} لادرا.")
    except discord.Forbidden:
        await ctx.send("I don't have permission to remove the timeout. | مووچەم نییە بێدەنگیەکە لابدەم.")

@unmute.error
async def unmute_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("You need the Moderate Members permission. | مووچەی کونترۆڵی ئەندامان پێویستە.")
    elif isinstance(error, commands.MemberNotFound):
        await ctx.send("Member not found. | ئەندام نەدۆزرایەوە.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Usage: $unmute @member | بەکارهێنان: $unmute @ئەندام")

@bot.command()
@commands.has_permissions(kick_members=True)
async def warn(ctx, member: discord.Member, *, reason: str = "No reason provided | هیچ هۆکارێک نەدراوە"):
    if member.bot:
        await ctx.send("You can't warn a bot. | ناتوانیت بۆتێک ئاگادار بکەیتەوە.")
        return
    g = warnings_data.setdefault(str(ctx.guild.id), {})
    user_warns = g.setdefault(str(member.id), [])
    user_warns.append({
        "reason": reason,
        "moderator": str(ctx.author.id),
        "timestamp": int(time.time()),
    })
    save_warnings()
    await ctx.send(f"Warned {member.mention}. They now have {len(user_warns)} warning(s). Reason: {reason}\n"
                   f"ئاگاداری دراوە {member.mention}. ئێستا {len(user_warns)} ئاگاداری هەیە. هۆکار: {reason}")

@warn.error
async def warn_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("You need the Kick Members permission to warn. | مووچەی لەدەرکردنی ئەندامان پێویستە بۆ ئاگادارکردنەوە.")
    elif isinstance(error, commands.MemberNotFound):
        await ctx.send("Member not found. | ئەندام نەدۆزرایەوە.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Usage: $warn @member [reason] | بەکارهێنان: $warn @ئەندام [هۆکار]")

@bot.command()
async def warnings(ctx, member: discord.Member = None):
    member = member or ctx.author
    g = warnings_data.get(str(ctx.guild.id), {})
    user_warns = g.get(str(member.id), [])
    if not user_warns:
        await ctx.send(f"{member.display_name} has no warnings. | {member.display_name} هیچ ئاگادارییەکی نییە.")
        return
    embed = discord.Embed(title=f"Warnings | ئاگاداریەکان for {member.display_name} ({len(user_warns)})")
    for i, w in enumerate(user_warns[-10:], start=1):
        when = datetime.datetime.fromtimestamp(w["timestamp"]).strftime("%Y-%m-%d %H:%M")
        mod = ctx.guild.get_member(int(w["moderator"]))
        mod_name = mod.display_name if mod else f"User {w['moderator']}"
        embed.add_field(name=f"#{i} - {when}", value=f"By | لەلایەن {mod_name}: {w['reason']}", inline=False)
    await ctx.send(embed=embed)

@bot.command(name="clearwarns")
@commands.has_permissions(kick_members=True)
async def clearwarns(ctx, member: discord.Member):
    g = warnings_data.get(str(ctx.guild.id), {})
    if str(member.id) in g:
        g.pop(str(member.id))
        save_warnings()
        await ctx.send(f"Cleared all warnings for {member.mention}. | هەموو ئاگاداریەکانی {member.mention} سڕدرایەوە.")
    else:
        await ctx.send(f"{member.display_name} has no warnings. | {member.display_name} هیچ ئاگادارییەکی نییە.")

@clearwarns.error
async def clearwarns_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ مووچەی Manage Guild پێویستە. | You need Manage Guild permission.")
    elif isinstance(error, commands.MemberNotFound):
        await ctx.send("❌ ئەندام نەدۆزرایەوە. | Member not found.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Usage: `!clearwarns @member`")

# --- RACE GAME DATA ---
ANIMALS = [
    "Lion", "Tiger", "Cheetah", "Leopard", "Horse", "Zebra", "Greyhound", "Jackal",
    "Wolf", "Coyote", "Fox", "Deer", "Antelope", "Gazelle", "Rabbit", "Hare",
    "Kangaroo", "Springbok", "Ostrich", "Emu", "Elephant", "Rhino", "Hippo",
    "Giraffe", "Bison", "Buffalo", "Wild Boar", "Pig", "Goat", "Sheep", "Dog",
    "Cat", "Camel", "Llama", "Gorilla", "Monkey", "Baboon", "Bear", "Panda",
    "Koala", "Sloth", "Snail", "Turtle", "Crab", "Frog", "Eagle",
    "Hawk", "Falcon", "Squirrel", "Mouse", "Rat", "Snump (Snail)"
]
RACE_EMOJIS = ["🏁", "🐎", "🐆", "🐇", "🐕", "🐘", "🐒", "🐢", "🐌", "🦊", "🐷", "🦁"]

class Racer:
    def __init__(self, name, emoji):
        self.name = name
        self.emoji = emoji
        self.distance = 0
        self.speed = random.randint(2, 12)
        self.finished = False

def get_race_progress_bar(percent):
    filled = int(round(15 * percent))
    bar = "█" * filled + "░" * (15 - filled)
    return f"[{bar}]"

# --- FUN & GAMES ---

@bot.command(aliases=["nick"])
@commands.has_permissions(manage_nicknames=True)
async def nickname(ctx, member: discord.Member, *, new_nick: str = None):
    try:
        await member.edit(nick=new_nick)
        if new_nick:
            await ctx.send(f"Changed {member.mention}'s nickname to **{new_nick}**. | ناوی نمایشی {member.mention} گۆڕدرا بۆ **{new_nick}**.")
        else:
            await ctx.send(f"Reset {member.mention}'s nickname. | ناوی نمایشی {member.mention} ڕێکخرایەوە.")
    except discord.Forbidden:
        await ctx.send("I don't have permission to change that nickname. | مووچەم نییە ئەو ناوی نمایشیە بگۆڕم.")

@nickname.error
async def nickname_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("You need the Manage Nicknames permission. | مووچەی بەڕێوەبردنی ناوی نمایشی پێویستە.")
    elif isinstance(error, commands.MemberNotFound):
        await ctx.send("Member not found. | ئەندام نەدۆزرایەوە.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Usage: $nickname @member [new nickname]  (omit to reset) | بەکارهێنان: $nickname @ئەندام [ناوی نوێ] (بەتاڵ بهێڵە بۆ ڕێکخستنەوە)")

@bot.command(name="timeout", aliases=["tmo"])
@commands.has_permissions(moderate_members=True)
async def timeout_cmd(ctx, member: discord.Member, minutes: int = 10, *, reason: str = "No reason provided | هیچ هۆکارێک نەدراوە"):
    await mute(ctx, member, minutes, reason=reason)

@timeout_cmd.error
async def timeout_cmd_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ مووچەی Moderate Members پێویستە. | You need Moderate Members permission.")
    elif isinstance(error, commands.MemberNotFound):
        await ctx.send("❌ ئەندام نەدۆزرایەوە. | Member not found.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Usage: `!timeout @member [minutes] [reason]`")

@bot.command(name="createchannel", aliases=["addchannel"])
@commands.has_permissions(manage_channels=True)
async def createchannel(ctx, channel_type: str, *, name: str):
    channel_type = channel_type.lower()
    try:
        if channel_type == "text":
            ch = await ctx.guild.create_text_channel(name)
        elif channel_type == "voice":
            ch = await ctx.guild.create_voice_channel(name)
        else:
            await ctx.send("Channel type must be `text` or `voice`. | جۆری کەناڵ دەبێت `text` یان `voice` بێت.")
            return
        await ctx.send(f"Created {channel_type} channel: {ch.mention} | کەناڵی {channel_type} دروستکرا: {ch.mention}")
    except discord.Forbidden:
        await ctx.send("I don't have permission to create channels. | مووچەم نییە کەناڵ دروست بکەم.")

@createchannel.error
async def createchannel_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("You need the Manage Channels permission. | مووچەی بەڕێوەبردنی کەناڵەکان پێویستە.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Usage: $createchannel <text|voice> <name> | بەکارهێنان: $createchannel <text|voice> <ناو>")

@bot.command(name="deletechannel")
@commands.has_permissions(manage_channels=True)
async def deletechannel(ctx, channel: discord.abc.GuildChannel = None):
    target = channel or ctx.channel
    name = target.name
    try:
        await target.delete()
        if channel is not None:
            await ctx.send(f"Deleted channel **#{name}**. | کەناڵی **#{name}** سڕدرایەوە.")
    except discord.Forbidden:
        await ctx.send("I don't have permission to delete that channel. | مووچەم نییە ئەو کەناڵە بسڕمەوە.")

@deletechannel.error
async def deletechannel_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("You need the Manage Channels permission. | مووچەی بەڕێوەبردنی کەناڵەکان پێویستە.")

@bot.command(name="addrole", aliases=["role"])
@commands.has_permissions(manage_roles=True)
async def addrole(ctx, member: discord.Member, *, role: discord.Role):
    if role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
        await ctx.send("You can't assign a role equal to or higher than your own. | ناتوانیت رۆڵێک دابنێیت کە یەکسانە یان بەرزتر لە رۆڵی خۆتە.")
        return
    if role >= ctx.guild.me.top_role:
        await ctx.send("That role is higher than mine, I can't assign it. | ئەو رۆڵە بەرزتر لە رۆڵی منە، ناتوانم دابنێم.")
        return
    try:
        await member.add_roles(role)
        await ctx.send(f"Added **{role.name}** to {member.mention}. | **{role.name}** زیادکرا بۆ {member.mention}.")
    except discord.Forbidden:
        await ctx.send("I don't have permission to add that role. | مووچەم نییە ئەو رۆڵە زیاد بکەم.")

@addrole.error
async def addrole_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("You need the Manage Roles permission. | مووچەی بەڕێوەبردنی رۆڵەکان پێویستە.")
    elif isinstance(error, (commands.MissingRequiredArgument, commands.RoleNotFound, commands.MemberNotFound)):
        await ctx.send("Usage: $addrole @member <role name> | بەکارهێنان: $addrole @ئەندام <ناوی رۆڵ>")

@bot.command(name="removerole")
@commands.has_permissions(manage_roles=True)
async def removerole(ctx, member: discord.Member, *, role: discord.Role):
    if role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
        await ctx.send("You can't remove a role equal to or higher than your own. | ناتوانیت رۆڵێک لابدەیت کە یەکسانە یان بەرزتر لە رۆڵی خۆتە.")
        return
    if role >= ctx.guild.me.top_role:
        await ctx.send("That role is higher than mine, I can't remove it. | ئەو رۆڵە بەرزتر لە رۆڵی منە، ناتوانم لابدەم.")
        return
    try:
        await member.remove_roles(role)
        await ctx.send(f"Removed **{role.name}** from {member.mention}. | **{role.name}** لەلایەن {member.mention} لادرا.")
    except discord.Forbidden:
        await ctx.send("I don't have permission to remove that role. | مووچەم نییە ئەو رۆڵە لابدەم.")

@removerole.error
async def removerole_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("You need the Manage Roles permission. | مووچەی بەڕێوەبردنی رۆڵەکان پێویستە.")
    elif isinstance(error, (commands.MissingRequiredArgument, commands.RoleNotFound, commands.MemberNotFound)):
        await ctx.send("Usage: $removerole @member <role name> | بەکارهێنان: $removerole @ئەندام <ناوی رۆڵ>")


@bot.command()
async def rps(ctx, choice: str = None):
    options = ["rock", "paper", "scissors"]
    if not choice or choice.lower() not in options:
        await ctx.send("Usage: $rps <rock|paper|scissors> | بەکارهێنان: $rps <بەردەوشک|کاغەز|مەقەس>")
        return
    user = choice.lower()
    bot_choice = random.choice(options)
    if user == bot_choice:
        result = "It's a tie! | یەکسانە!"
    elif (user, bot_choice) in [("rock", "scissors"), ("paper", "rock"), ("scissors", "paper")]:
        result = "You win! 🎉 | تۆ بردیت! 🎉"
    else:
        result = "I win! 🤖 | من بردم! 🤖"
    emojis = {"rock": "🪨", "paper": "📄", "scissors": "✂️"}
    await ctx.send(f"You | تۆ: {emojis[user]} {user}\nMe | من: {emojis[bot_choice]} {bot_choice}\n**{result}**")

number_games = {}
hangman_games = {}
lucky_games = {}
race_lobbies = {}
anime_quizzes = {}
active_quizzes = {}
tf_games = {}
greentea_games = {}
active_giveaways = {}
active_games = {}

@bot.command()
async def guess(ctx):
    if ctx.channel.id in number_games:
        await ctx.send("A number guessing game is already running here. Type `!stopgame` to end it. | یاری حەزرکردنی ژمارە بەردەوامە ئێرە. `!stopgame` بنووسە بۆ کۆتایی پێهێنان.")
        return
    number_games[ctx.channel.id] = {"number": random.randint(1, 100), "tries": 0, "host": ctx.author.id}
    await ctx.send(
        "🎯 I picked a number between **1** and **100**. | ژمارەیەک هەڵبژاردم لە نێوان **١** و **١٠٠**.\n"
        "Send your guesses in chat. Type `!stopgame` to give up. | حەزرەکانت بنێرە لە چاتدا. `!stopgame` بنووسە بۆ تەرككردن."
    )

@bot.command()
async def stopgame(ctx):
    game = number_games.pop(ctx.channel.id, None)
    hangman = hangman_games.pop(ctx.channel.id, None)
    lucky = lucky_games.pop(ctx.channel.id, None)
    if game:
        await ctx.send(f"Game ended. The number was **{game['number']}**. | یاری کۆتایی هات. ژمارەکە **{game['number']}** بوو.")
    elif hangman:
        await ctx.send(f"Game ended. The word was **{hangman['word']}**. | یاری کۆتایی هات. وشەکە **{hangman['word']}** بوو.")
    elif lucky:
        task = lucky.get("task")
        if task:
            task.cancel()
        await ctx.send(f"Lucky game ended. The number was **{lucky['number']}**. | یاری بەختەوار کۆتایی هات. ژمارەکە **{lucky['number']}** بوو.")
    else:
        await ctx.send("No game is running here. | هیچ یارییەک ئێرە ناکرێت.")

async def _lucky_timeout_watcher(channel_id: int):
    """
    Auto-ends a lucky game after inactivity:
    - 60 s  if nobody has guessed yet
    - 180 s if at least one guess was made
    Checks every 10 seconds so the sleep is interruptible via cancellation.
    """
    try:
        while True:
            await asyncio.sleep(10)
            game = lucky_games.get(channel_id)
            if game is None:
                return
            elapsed = time.time() - game["last_activity"]
            limit = 180 if game["has_guesses"] else 60
            if elapsed >= limit:
                lucky_games.pop(channel_id, None)
                channel = bot.get_channel(channel_id)
                if channel:
                    timeout_embed = discord.Embed(
                        title="⏰ Lucky Game Ended / یاری بەختەوار کۆتایی هات",
                        description=(
                            f"**English:** No activity for {limit} seconds! Game over. The number was **{game['number']}**.\n\n"
                            f"**کوردی:** {limit} چرکە چالاکی نەبوو! یاری کۆتایی هات. ژمارەکە **{game['number']}** بوو."
                        ),
                        color=discord.Color.red()
                    )
                    try:
                        await channel.send(embed=timeout_embed)
                    except (discord.Forbidden, discord.HTTPException):
                        pass
                return
    except asyncio.CancelledError:
        pass

@bot.command()
async def lucky(ctx):
    if ctx.channel.id in lucky_games:
        await ctx.send("A Lucky game is already running here! Type a number to guess, or `!stopgame` to end it. | یاری بەختەوار بەردەوامە ئێرە! ژمارەیەک بنووسە بۆ حەزرکردن، یان `!stopgame` بۆ کۆتایی پێهێنان.")
        return
    task = asyncio.create_task(_lucky_timeout_watcher(ctx.channel.id))
    lucky_games[ctx.channel.id] = {
        "number": random.randint(1, 100),
        "last_activity": time.time(),
        "has_guesses": False,
        "task": task,
        "guesses": 0,
        "guild_id": ctx.guild.id if ctx.guild else None,
    }
    embed = discord.Embed(
        title="🎮 Lucky Game / یاری بەختەوار",
        description=(
            "**English:** Hey there! I picked a number between **1 - 100**. Pick a number!\n\n"
            "**کوردی:** سڵاو! من ժمارەیەکم هەڵبժارد لەنێوان **۱ - ۱۰۰**. تکایە ժمارەیەک ئەگێڕە!\n\n"
            "⏰ **English:** Game auto-ends in **60s** if no one guesses, or **3 min** after last guess.\n"
            "⏰ **کوردی:** یارییەکە بە خۆی کۆتایی دێت لە **۶۰چ** ئەگەر کەس حەزر نەکات، یان **۳ خولەک** پاش کۆتایین حەزر."
        ),
        color=discord.Color.gold()
    )
    await ctx.send(embed=embed)

@bot.command(name="luckylb", aliases=["luckyleaderboard", "luckyboard"])
async def luckylb(ctx):
    if ctx.guild is None:
        await ctx.send("This command can only be used in a server. | ئەم فەرمانە تەنها لە سێرڤەر دەکرێت بەکارهێنرێت.")
        return
    conn = get_db()
    rows = conn.execute(
        "SELECT user_id, wins, total_guesses, best_guesses FROM lucky_leaderboard "
        "WHERE guild_id = ? AND wins > 0 ORDER BY wins DESC, best_guesses ASC LIMIT 10",
        (ctx.guild.id,)
    ).fetchall()
    conn.close()
    if not rows:
        await ctx.send("Nobody has won the Lucky game yet! Start one with `!lucky`. | هێشتا کەس یاری بەختەوارى نەبردووە! بە `!lucky` دەستپێبکە.")
        return
    medals = ["🥇", "🥈", "🥉"]
    lines = []
    for i, row in enumerate(rows):
        member = ctx.guild.get_member(row["user_id"])
        name = member.display_name if member else f"User {row['user_id']}"
        prefix = medals[i] if i < 3 else f"`#{i+1}`"
        avg = round(row["total_guesses"] / row["wins"], 1) if row["wins"] else 0
        best = row["best_guesses"]
        lines.append(
            f"{prefix} **{name}**\n"
            f"> 🏆 Wins: **{row['wins']}** · ⚡ Best: **{best}** guesses · 📊 Avg: **{avg}**"
        )
    embed = discord.Embed(
        title="🎮 Lucky Game Leaderboard / لیستی باشترینانی یاری بەختەوار",
        description="\n\n".join(lines),
        color=discord.Color.gold(),
        timestamp=datetime.datetime.utcnow(),
    )
    embed.set_footer(text=f"{ctx.guild.name} · Play with $lucky!")
    await ctx.send(embed=embed)

@bot.command()
async def bomb(ctx):
    wires = ["Red", "Blue", "Green", "Yellow"]
    correct_wire = random.choice(wires)
    embed = discord.Embed(
        title="💣 Defuse the Bomb! / بۆمبەکە خەڵات بکە!",
        description=(
            "**English:** A bomb has been planted! Cut the correct wire to defuse it before it explodes!\n\n"
            "**کوردی:** بۆمبەیەک دانراوە! وایەری دروست ببڕە بۆ خەڵات کردنی پێش ئەوەی تەقا بکات!"
        ),
        color=discord.Color.orange()
    )
    embed.set_footer(text="Choose wisely! / بە تێڕوانین هەڵبژێرە!")
    view = BombView(correct_wire)
    await ctx.send(embed=embed, view=view)


class RaceLobbyView(discord.ui.View):
    """Persistent join button for the race lobby."""

    def __init__(self, channel_id: int):
        super().__init__(timeout=35)   # slightly longer than the 30s lobby
        self.channel_id = channel_id

    @discord.ui.button(
        label="🏁 Join Race!  |  بەشداربوو!",
        style=discord.ButtonStyle.success,
        custom_id="race_join"
    )
    async def join_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel = interaction.channel
        lobby   = race_lobbies.get(self.channel_id)

        # Lobby gone (race already started or cancelled)
        if not lobby:
            button.disabled = True
            await interaction.response.edit_message(view=self)
            await interaction.followup.send(
                "❌ هیچ لۆبییەک نییە! | No active lobby right now.",
                ephemeral=True
            )
            return

        # Already joined
        if interaction.user.id in lobby["players"]:
            await interaction.response.send_message(
                f"⚠️ {interaction.user.mention} تۆ پێشتر بەشداربووی! | You already joined!",
                ephemeral=True
            )
            return

        # Lobby full
        if len(lobby["players"]) >= 5:
            await interaction.response.send_message(
                "🚫 لۆبی پڕە (٥/٥) | Lobby is full (5/5). Wait for the next race!",
                ephemeral=True
            )
            return

        # Add player
        used_animals = {r.name for r in lobby["players"].values()}
        available    = [a for a in ANIMALS if a not in used_animals] or ANIMALS
        animal_name  = random.choice(available)
        animal_emoji = random.choice(RACE_EMOJIS)
        racer        = Racer(animal_name, animal_emoji)
        lobby["players"][interaction.user.id] = racer

        updated_embed = await _build_lobby_embed(channel, countdown=None)

        # If lobby is now full, disable the button
        if len(lobby["players"]) >= 5:
            button.disabled = True

        try:
            await interaction.response.edit_message(embed=updated_embed, view=self)
        except Exception:
            await interaction.response.defer()

        await interaction.followup.send(
            f"✅ {interaction.user.mention} بەشداربوو! ئاژەڵەکەت {animal_emoji} **{animal_name}**ە! | "
            f"Joined! Your animal is {animal_emoji} **{animal_name}**! 🎉",
            ephemeral=True
        )

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True


async def _build_lobby_embed(channel, countdown=None):

    """Build the lobby waiting embed."""
    lobby = race_lobbies.get(channel.id)
    if not lobby:
        return None
    players = lobby["players"]
    lines = ""
    for uid, r in players.items():
        member = channel.guild.get_member(uid)
        name = member.display_name if member else f"User {uid}"
        lines += f"{r.emoji} **{name}** — {r.name}\n"
    if not lines:
        lines = "*No racers yet... / هێشتا کەس نەچووەتە ناو...*"
    timer_line = f"\n⏳ **{countdown}s** remaining / ماوەی بەردەوام" if countdown is not None else ""
    needed = max(0, 3 - len(players))
    status = (
        f"✅ **English:** Lobby open! Click the **Join Race** button below!{timer_line}\n"
        f"✅ **کوردی:** لۆبی کراوەیە! دوگمەی **بەشداربوو** لە خوارەوە دابگرە!\n\n"
        f"👥 **Players ({len(players)}/5):** *(need {needed} more / {needed} زیاتر پێویستە)*\n"
        f"{lines}"
    )
    embed = discord.Embed(
        title="🏁 Animal Race Lobby / لۆبیی پێشبڕکێی ئاژەڵان",
        description=status,
        color=discord.Color.gold()
    )
    embed.set_footer(text="Min 3 players to start · Max 5 · حەدەقەل ٣ بەشداربێ بۆ دەستپێکردن · زۆرینە ٥")
    return embed

async def _run_race(channel):
    """Countdown 30s then run or cancel the race."""
    lobby = race_lobbies.get(channel.id)
    if not lobby:
        return
    try:
        for secs_left in range(30, 0, -5):
            lobby = race_lobbies.get(channel.id)
            if not lobby:
                return
            embed = await _build_lobby_embed(channel, countdown=secs_left)
            if embed and lobby.get("lobby_msg"):
                try:
                    await lobby["lobby_msg"].edit(embed=embed)
                except Exception:
                    pass
            await asyncio.sleep(5)

        lobby = race_lobbies.pop(channel.id, None)
        if not lobby:
            return

        players = lobby["players"]

        if len(players) < 3:
            cancel_embed = discord.Embed(
                title="❌ Race Cancelled / پێشبڕکێ هەڵوەشایەوە",
                description=(
                    f"**English:** Not enough players joined. Need at least 3, only {len(players)} joined.\n\n"
                    f"**کوردی:** بەشداربوانی پێویست نەبوون. حەدەقەل ٣ دەکرێت، تەنها {len(players)} بەشداربوون."
                ),
                color=discord.Color.red()
            )
            try:
                await lobby["lobby_msg"].edit(embed=cancel_embed)
            except Exception:
                await channel.send(embed=cancel_embed)
            return

        racers = list(players.values())
        medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
        user_ids = list(players.keys())

        # Disable the join button — race is starting
        lobby_view = lobby.get("view") if lobby else None
        if lobby_view:
            for child in lobby_view.children:
                child.disabled = True
            try:
                await lobby["lobby_msg"].edit(view=lobby_view)
            except Exception:
                pass

        countdown_embed = discord.Embed(
            title="🚦 Get Ready! / ئامادە بە!",
            description=(
                "**English:** The race is about to begin! 3... 2... 1... GO!\n\n"
                "**کوردی:** پێشبڕکێکە دەست پێ دەکات! ٣... ٢... ١... بڕۆ!"
            ),
            color=discord.Color.orange()
        )
        for i, r in enumerate(racers):
            uid = user_ids[i]
            member = channel.guild.get_member(uid)
            mname = member.display_name if member else f"User {uid}"
            countdown_embed.add_field(name=f"{r.emoji} {r.name}", value=f"Ridden by **{mname}**", inline=True)
        try:
            await lobby["lobby_msg"].edit(embed=countdown_embed)
        except Exception:
            pass
        await asyncio.sleep(3)

        track_length = 100
        winners = []
        msg = lobby["lobby_msg"]

        while len(winners) < len(racers):
            for r in racers:
                if not r.finished:
                    r.distance = min(r.distance + r.speed + random.randint(1, 5), track_length)
                    if r.distance >= track_length:
                        r.finished = True
                        winners.append(r)

            status = ""
            for i, r in enumerate(racers):
                uid = user_ids[i]
                member = channel.guild.get_member(uid)
                mname = member.display_name if member else f"User {uid}"
                pct = r.distance / track_length
                bar = get_race_progress_bar(pct)
                pos_medal = medals[winners.index(r)] if r in winners else "🏃"
                status += f"{pos_medal} {r.emoji} {bar} **{int(pct*100)}%** {r.name} *({mname})*\n"

            race_embed = discord.Embed(
                title="🏃 Racing! / پێشبڕکێ بەردەوامە!",
                description=status,
                color=discord.Color.blue()
            )
            try:
                await msg.edit(embed=race_embed)
            except Exception:
                pass
            if len(winners) < len(racers):
                await asyncio.sleep(0.8)

        res = "**English:** Race complete! Results:\n**کوردی:** پێشبڕکێ تەواو بوو! ئەنجامەکان:\n\n"
        for i, r in enumerate(winners):
            uid = user_ids[racers.index(r)]
            member = channel.guild.get_member(uid)
            mname = member.display_name if member else f"User {uid}"
            res += f"{medals[i]} {r.emoji} **{r.name}** — {mname}\n"

        final_embed = discord.Embed(
            title="🏆 Race Results / ئەنجامەکانی پێشبڕکێ",
            description=res,
            color=discord.Color.green(),
            timestamp=datetime.datetime.utcnow()
        )
        winner_racer = winners[0]
        winner_uid = user_ids[racers.index(winner_racer)]
        winner_member = channel.guild.get_member(winner_uid)
        wname = winner_member.display_name if winner_member else "Someone"
        if "Snail" in winner_racer.name or "Snump" in winner_racer.name:
            final_embed.set_footer(text=f"A Snail won?! GG {wname}! / بزوێنەرەکە بردیەوە؟!")
        elif "Horse" in winners[-1].name:
            final_embed.set_footer(text=f"The Horse came last?! GG {wname}! / ئەسپەکە کۆتایی هات؟!")
        else:
            final_embed.set_footer(text=f"🎉 GG {wname}! Great race! / پێشبڕکێیەکی باش!")
        try:
            await msg.edit(embed=final_embed)
        except Exception:
            await channel.send(embed=final_embed)

    except asyncio.CancelledError:
        pass

@bot.command()
async def race(ctx):
    channel = ctx.channel

    # If a lobby is already open, tell them to click the button
    if channel.id in race_lobbies:
        lobby = race_lobbies[channel.id]
        if ctx.author.id in lobby["players"]:
            await ctx.send(
                f"⚠️ {ctx.author.mention} تۆ پێشتر بەشداربووی! | You already joined this race!",
                delete_after=8
            )
        elif len(lobby["players"]) >= 5:
            await ctx.send(
                f"🚫 لۆبی پڕە (٥/٥) | Lobby full (5/5). Wait for the next race!",
                delete_after=8
            )
        else:
            await ctx.send(
                f"🏁 {ctx.author.mention} **دوگمەی بەشداربوو** لە لۆبیی سەرەوەدا بکە! | "
                f"Click the **Join Race** button on the lobby message above!",
                delete_after=10
            )
        try:
            await ctx.message.delete()
        except Exception:
            pass
        return

    # Create a new lobby
    animal_name  = random.choice(ANIMALS)
    animal_emoji = random.choice(RACE_EMOJIS)
    racer        = Racer(animal_name, animal_emoji)
    view         = RaceLobbyView(channel.id)

    task = asyncio.get_event_loop().create_task(_run_race(channel))
    race_lobbies[channel.id] = {
        "players":   {ctx.author.id: racer},
        "task":      task,
        "lobby_msg": None,
        "view":      view,
    }

    lobby_embed = await _build_lobby_embed(channel, countdown=30)
    lobby_msg   = await ctx.send(embed=lobby_embed, view=view)
    race_lobbies[channel.id]["lobby_msg"] = lobby_msg

    try:
        await ctx.message.delete()
    except Exception:
        pass

# ── SPY GAME CONSTANTS ────────────────────────────────────────────────────────
SPY_LOCATIONS = [
    "خوێندنگە | School", "زانکۆ | University", "نەخۆشخانە | Hospital",
    "فڕۆکەخانە | Airport", "سینەما | Cinema", "چێشتخانە | Restaurant",
    "بازاڕ | Bazaar", "یاریگا | Stadium", "پۆلیس | Police Station",
    "کتێبخانە | Library", "پارک | Park", "مۆڵ | Mall",
    "کافێ | Café", "بانک | Bank", "مزگەوت | Mosque",
    "هۆتێل | Hotel", "گاراژ | Garage", "نانەوایی | Bakery",
    "ئارایشگا | Hair Salon", "وەرزشگا | Gym", "قاوەخانە | Teahouse",
    "کۆمپانیا | Company", "کێڵگە | Farm", "باغ | Garden", "دەریاچە | Lake",
]
SPY_TOTAL_ROUNDS  = 5
SPY_ROUND_SECONDS = 60
SPY_ROUND_COLORS  = [0x5865f2, 0xfee75c, 0xed4245, 0x57f287, 0xeb459e]
SPY_MEDALS        = ["🥇","🥈","🥉","4️⃣","5️⃣","6️⃣","7️⃣","8️⃣","9️⃣","🔟"]
SPY_LOBBY_TIMEOUT = 30
spy_games: dict   = {}


def _spy_lobby_embed(gid: int, countdown: int) -> discord.Embed:
    game    = spy_games.get(gid)
    players = game["players"] if game else []
    count   = len(players)
    roster  = (
        "\n".join(f"{SPY_MEDALS[i]} {p.mention}" for i, p in enumerate(players))
        or "*هیچ یاریزانێک نییە | No players yet*"
    )
    bar   = "🟩" * min(count, 3) + "⬛" * max(0, 3 - count)
    ready = count >= 3
    e = discord.Embed(
        title="🕵️ یاری سیخوڕ — SPY GAME LOBBY | لۆبی",
        description=(
            "```diff\n+ CLASSIFIED OPERATION | کارگێڕی نهێنی\n```\n"
            "**چۆن یاری دەکرێت | How to play:**\n"
            "• هاووڵاتییەکان شوێنەکەیان دەزانن | Civilians know the location\n"
            "• سیخوڕ شوێنەکە نازانێت — خۆی تێکەڵ بکات | Spy must blend in\n"
            "• هەر دوور یەک وشە بڵێ دەربارەی شوێن | Say ONE word per round\n"
            "• سیخوڕ بدۆزنەوە پێش کۆتایی دوورەکان! | Find the spy before it's too late!\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"👥 **یاریزانەکان | Players ({count}/10)**\n{roster}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"🎯 **دۆخ | Status:** {bar} "
            + ("✅ ئامادەی دەستپێکردن! | Ready to start!" if ready
               else f"پێویستمانە بە **{max(0,3-count)}** تری | Need **{max(0,3-count)}** more")
            + f"\n⏳ **کاوت داون | Countdown:** `{countdown}` چرکە | seconds\n\n"
            f"🌀 `{SPY_TOTAL_ROUNDS}` دوور | rounds  ×  `{SPY_ROUND_SECONDS}`چ | s each\n\n"
            "⬇️ دوگمەی **بەشداربوو** داپرسە | Press **Join** to enter!"
        ),
        color=0x5865f2,
    )
    e.set_footer(text="!spystop هەڵوەشاندن • $spystatus دۆخ • $spyleave جێبهێشتن | cancel • status • leave")
    return e


class SpyLobbyView(discord.ui.View):
    def __init__(self, gid: int, channel):
        super().__init__(timeout=120)
        self.gid     = gid
        self.channel = channel

    @discord.ui.button(label="🕵️ بەشداربوو | Join", style=discord.ButtonStyle.primary, custom_id="spy_join_btn")
    async def join_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        game = spy_games.get(self.gid)
        if not game or game.get("started"):
            return await interaction.response.send_message(
                "یاری پێشتر دەستی پێکردووە! | Game already started!", ephemeral=True)
        if interaction.user in game["players"]:
            return await interaction.response.send_message(
                "✅ تۆ پێشتر بەشداربووی! | You already joined!", ephemeral=True)
        if len(game["players"]) >= 10:
            return await interaction.response.send_message(
                "🚫 لۆبی پڕە (١٠/١٠) | Lobby is full!", ephemeral=True)
        game["players"].append(interaction.user)
        embed = _spy_lobby_embed(self.gid, game.get("countdown", SPY_LOBBY_TIMEOUT))
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="🚪 جێبهێشتن | Leave", style=discord.ButtonStyle.secondary, custom_id="spy_leave_btn2")
    async def leave_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        game = spy_games.get(self.gid)
        if not game or game.get("started"):
            return await interaction.response.send_message(
                "ناتوانیت بچیت لە ناوەندی یاری | Can't leave mid-game!", ephemeral=True)
        if interaction.user not in game["players"]:
            return await interaction.response.send_message(
                "⚠️ تۆ لە لۆبیدا نییت! | You're not in the lobby!", ephemeral=True)
        game["players"].remove(interaction.user)
        if not game["players"]:
            spy_games.pop(self.gid, None)
            self.stop()
            for child in self.children:
                child.disabled = True
            e = discord.Embed(
                title="💀 لۆبی بەتاڵ — Lobby Empty",
                description="هیچ یاریزانێک نەماوە. یاری هەڵوەشایەوە. | No players remain. Cancelled.\n`!spy` بنووسە بۆ دەستپێکردنی نوێ | Type `!spy` for a new game!",
                color=0x2b2d31)
            return await interaction.response.edit_message(embed=e, view=self)
        embed = _spy_lobby_embed(self.gid, game.get("countdown", SPY_LOBBY_TIMEOUT))
        await interaction.response.edit_message(embed=embed, view=self)


async def _spy_lobby_task(gid: int, channel, view: SpyLobbyView):
    """Counts down SPY_LOBBY_TIMEOUT seconds, updating the embed, then auto-starts."""
    remaining = SPY_LOBBY_TIMEOUT
    while remaining > 0:
        game = spy_games.get(gid)
        if not game or game.get("started"):
            return
        game["countdown"] = remaining
        try:
            await game["lobby_msg"].edit(embed=_spy_lobby_embed(gid, remaining), view=view)
        except Exception:
            pass
        tick = min(10, remaining)
        await asyncio.sleep(tick)
        remaining -= tick

    game = spy_games.get(gid)
    if not game or game.get("started"):
        return

    for child in view.children:
        child.disabled = True
    try:
        closing = _spy_lobby_embed(gid, 0)
        closing.title = "🔴 دەستپێکردن… | Starting the game…"
        await game["lobby_msg"].edit(embed=closing, view=view)
    except Exception:
        pass

    if len(game["players"]) < 3:
        spy_games.pop(gid, None)
        e = discord.Embed(
            title="❌ یاری هەڵوەشایەوە | Game Cancelled",
            description=(
                f"یاریزانی پێویست نەبوو. پێویستمانە بە ٣+ — تەنها **{len(game['players'])}** بەشداربوون. | "
                f"Not enough players (need 3+, got {len(game['players'])}).\n"
                "`!spy` بنووسە بۆ هەوڵدانی دووبارە | Type `!spy` to try again."
            ),
            color=0xed4245)
        await channel.send(embed=e)
        return

    await _spy_run_game(gid, channel)


async def _spy_run_game(gid: int, channel):
    """Assigns spy + location and runs all rounds."""
    game = spy_games.get(gid)
    if not game:
        return
    game["started"]  = True
    game["spy"]      = random.choice(game["players"])
    game["location"] = random.choice(SPY_LOCATIONS)

    roster = "\n".join(f"{SPY_MEDALS[i]} {p.mention}" for i, p in enumerate(game["players"]))
    e = discord.Embed(
        title="🔴 OPERATION SPY HUNT — ACTIVE | کارگێڕی نێچیرکردنی سیخوڕ — چالاک",
        description=(
            "```\n🕵️  یاری سیخوڕ دەستی پێکرد  🕵️\n```\n"
            "**پەیامە تایبەتەکانت بپشکنە! | Check your DMs!**\n"
            "هاووڵاتییەکان — شوێنەکەتان دەزانن. سیخوڕەکە بدۆزنەوە. | Civilians — find the spy.\n"
            "سیخوڕ — تۆ هیچ نازانیت. خۆت تێکەڵ بکە! | Spy — blend in!\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"👥 **ئاجێنتەکان | Agents ({len(game['players'])})**\n{roster}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"🌀 **{SPY_TOTAL_ROUNDS} دوور | rounds × {SPY_ROUND_SECONDS}چ | s each**\n"
            "`!spyvote` دەنگدانی زوو  •  `!spystop` کۆتایی پێهێنان"
        ),
        color=0x2b2d31)
    e.set_footer(text="🔴 سیخوڕ لەنێوانتانەوە — بەختی باش! | The spy is among you — good luck!")
    await channel.send(embed=e)

    for rnd in range(1, SPY_TOTAL_ROUNDS + 1):
        cur = spy_games.get(gid)
        if not cur or not cur.get("started") or cur.get("voting"):
            return
        location = cur["location"]
        dm_fails = []
        for player in cur["players"]:
            try:
                if player.id == cur["spy"].id:
                    dm = discord.Embed(
                        title=f"🕵️ دور {rnd}/{SPY_TOTAL_ROUNDS} — تۆ سیخوڕیت | YOU ARE THE SPY",
                        description=(
                            "```diff\n- CLASSIFIED | نهێنی\n```\n"
                            "😈 **تۆ سیخوڕیت! | You are the spy!**\n\n"
                            "هێشتا شوێنەکە نازانیت. | You still don't know the location.\n"
                            "گوێ بگرە، پرسیارە زیرەکانە بپرسە — **دەستگیر مەبە! | Don't get caught!**"
                        ),
                        color=0xed4245)
                    dm.set_footer(text=f"دوور | Round {rnd}/{SPY_TOTAL_ROUNDS} • ئارام بمێنەوە 🧊 | Stay cool")
                else:
                    dm = discord.Embed(
                        title=f"📍 دور {rnd}/{SPY_TOTAL_ROUNDS} — نوێکردنەوەی شوێن | LOCATION UPDATE",
                        description=(
                            f"```diff\n+ CIVILIAN BRIEFING — دوور | ROUND {rnd}\n```\n"
                            f"🗺️ شوێنی نهێنی ئەم دووری | This round's secret location:\n\n"
                            f"# ‎{location}\n\n"
                            "**یەک وشە** بدە وەک ئاگادارکردنەوە — شوێنەکە ڕاستەوخۆ مەڵێ! | "
                            "Give **one word** clue — don't say the location directly!"
                        ),
                        color=0x57f287)
                    dm.set_footer(text=f"دوور | Round {rnd}/{SPY_TOTAL_ROUNDS} • سیخوڕەکە بدۆزەرەوە 🔍 | Find the spy")
                await player.send(embed=dm)
            except discord.Forbidden:
                dm_fails.append(player.display_name)

        mentions  = " ".join(p.mention for p in cur["players"])
        color     = SPY_ROUND_COLORS[rnd - 1]
        progress  = "🟥" * rnd + "⬛" * (SPY_TOTAL_ROUNDS - rnd)
        rnd_embed = discord.Embed(
            title=f"🌀 دور {rnd}/{SPY_TOTAL_ROUNDS} — ROUND | دوور",
            description=(
                f"{mentions}\n\n"
                f"```\n🎙  یەک وشە دەربارەی شوێنەکە بڵێ! | SAY ONE WORD about the location!\n```\n"
                "هاووڵاتییەکان — ئاگاداری بدە بەبێ ئاشکراکردنی شوێن. | Civilians — hint without revealing.\n"
                "سیخوڕ — شتێک دروست بکە 😈 | Spy — make something up!\n\n"
                f"**پێشکەوتن | Progress:** {progress}\n"
                f"⏳ **{SPY_ROUND_SECONDS} چرکە | seconds** — دواتر دووری داهاتوو! | then next round!"
            ),
            color=color)
        if dm_fails:
            rnd_embed.add_field(
                name="⚠️ پەیامە تایبەتەکان داخراون | DMs Blocked",
                value=", ".join(dm_fails) + " — DM چالاک بکە! | Enable DMs to receive clues!",
                inline=False)
        rnd_embed.set_footer(text=f"دوور | Round {rnd}/{SPY_TOTAL_ROUNDS} • $spyvote دەنگدانی زوو • $spystop کۆتایی")
        try:
            await channel.send(embed=rnd_embed)
        except Exception:
            return
        await asyncio.sleep(SPY_ROUND_SECONDS)

    final = spy_games.get(gid)
    if not final or not final.get("started") or final.get("voting"):
        return
    mentions = " ".join(p.mention for p in final["players"])
    done = discord.Embed(
        title="🏁 هەموو دوورەکان تەواو بوون! | ALL ROUNDS DONE!",
        description=(
            f"{mentions}\n\n"
            "```diff\n- D I S C U S S I O N   O V E R | نووسراوە تەواو بوو\n```\n"
            "🟥🟥🟥🟥🟥 پێنج دوور تەواو! | Five rounds complete!\n\n"
            "کاتی دەنگدانە. **کێ سیخوڕەکەیە؟ | Who is the spy?**\n"
            "دەنگدانەکە لە کاتێکدا دەکرێتەوە… | The ballot opens in a moment… 🗳️"
        ),
        color=0xfee75c)
    done.set_footer(text="بە وریاییەوە هەڵبژێرە | Choose carefully.")
    try:
        await channel.send(embed=done)
    except Exception:
        pass
    await _start_spy_vote(gid, channel)


class SpyVoteView(discord.ui.View):
    def __init__(self, gid: int, players: list, channel):
        super().__init__(timeout=60)
        self.gid     = gid
        self.channel = channel
        self.votes   = {}
        self.players = players
        self._closed = False
        for p in players:
            btn = discord.ui.Button(
                label=p.display_name[:20],
                style=discord.ButtonStyle.secondary,
                custom_id=f"svote_{p.id}",
            )
            btn.callback = self._make_cb(p)
            self.add_item(btn)

    def _make_cb(self, target):
        async def callback(interaction: discord.Interaction):
            if self._closed:
                return await interaction.response.send_message(
                    "دەنگدان کۆتایی هاتووە. | Voting is closed.", ephemeral=True)
            game = spy_games.get(self.gid)
            if not game:
                return await interaction.response.send_message(
                    "یاری کۆتایی هاتووە. | Game ended.", ephemeral=True)
            voter = interaction.user
            if voter not in self.players:
                return await interaction.response.send_message(
                    "تەنها یاریزانان دەنگ دەدەن. | Only players can vote.", ephemeral=True)
            if voter.id in self.votes:
                return await interaction.response.send_message(
                    f"پێشتر دەنگت دا بۆ **{self.votes[voter.id].display_name}**. | Already voted!", ephemeral=True)
            self.votes[voter.id] = target
            await interaction.response.send_message(
                f"✅ دەنگت دا بۆ **{target.display_name}** | Voted for **{target.display_name}**.", ephemeral=True)
            if len(self.votes) >= len(self.players):
                self._closed = True
                self.stop()
        return callback

    async def on_timeout(self):
        self._closed = True
        await _spy_reveal(self.gid, self.channel, self.votes, self.players)


async def _start_spy_vote(gid: int, channel):
    game = spy_games.get(gid)
    if not game or game.get("voting"):
        return
    game["voting"] = True
    players = game["players"]
    view    = SpyVoteView(gid, players, channel)
    tally_t = "\n".join(f"{SPY_MEDALS[i]} {p.mention}" for i, p in enumerate(players))
    e = discord.Embed(
        title="🗳️ دەنگدان — VOTE! کێ سیخوڕەکەیە؟ | Who is the spy?",
        description=(
            "```diff\n+ BALLOT OPEN — ٦٠ چرکە | 60 SECONDS TO VOTE\n```\n"
            "دوگمەی ناوی کەسێک بکە کە فکر دەکەیت سیخوڕەکەیە! | Click the name of who you think is the spy!\n\n"
            f"👥 **یاریزانەکان | Players:**\n{tally_t}"
        ),
        color=0xfee75c)
    e.set_footer(text="هەموو یاریزانان دەنگ بدەن | All players vote • 60s timeout")
    await channel.send(embed=e, view=view)
    await view.wait()
    if not view._closed:
        await _spy_reveal(gid, channel, view.votes, players)


async def _spy_reveal(gid: int, channel, votes: dict, players: list):
    game = spy_games.pop(gid, None)
    if not game:
        return
    spy      = game.get("spy")
    location = game.get("location", "?")
    tally    = {}
    for voted in votes.values():
        tally[voted.id] = tally.get(voted.id, 0) + 1
    most_id    = max(tally, key=tally.get) if tally else None
    voted_out  = next((p for p in players if p.id == most_id), None)
    spy_caught = voted_out and spy and voted_out.id == spy.id
    vote_lines = "\n".join(
        f"{SPY_MEDALS[i]} {p.mention} — **{tally.get(p.id, 0)}** دەنگ | votes"
        for i, p in enumerate(players)
    ) or "*هیچ دەنگێک نەدرا | No votes cast*"
    color   = 0x57f287 if spy_caught else (0xed4245 if spy else 0x2b2d31)
    verdict = (
        f"✅ **سیخوڕەکە دەستگیر کرا! | SPY CAUGHT!**\n{spy.mention} سیخوڕ بوو! | was the spy!" if spy_caught
        else f"❌ **سیخوڕەکە هەڵات! | SPY ESCAPED!**\n{spy.mention} سیخوڕ بوو! | was the spy!" if spy
        else "⚠️ هیچ زانیاریەک نەدۆزرایەوە. | No spy data."
    )
    e = discord.Embed(
        title="🏁 کۆتایی یاری — GAME OVER | یاری کۆتایی هات",
        description=(
            f"```diff\n{'+ AGENTS WIN | ئاجێنتەکان بردن' if spy_caught else '- SPY WINS | سیخوڕ برد'}\n```\n"
            f"{verdict}\n"
            f"📍 شوێنەکە بوو | Location was: **{location}**\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🗳️ **دەنگەکان | Vote Tally:**\n{vote_lines}"
        ),
        color=color)
    e.set_footer(text="!spy بنووسە بۆ یاریکردنی دووبارە | Type $spy for a new game!")
    try:
        await channel.send(embed=e)
    except Exception:
        pass


@bot.command(name="spy")
async def spy_cmd(ctx):
    """!spy — Spy Game lobby with Join button and 30-second auto-start."""
    if not ctx.guild:
        return await ctx.send("This command only works in a server. | ئەم فەرمانە تەنها لە سێرڤەر کاردەکات.")
    gid  = ctx.guild.id
    game = spy_games.get(gid)
    try:
        await ctx.message.delete()
    except Exception:
        pass

    if game:
        if game.get("started"):
            e = discord.Embed(
                title="⚠️ یاری بەردەوامە | Game Already Active",
                description="یاری سیخوڕ ئێستا بەردەوامە! `!spystop` بەکارهێنە بۆ کۆتایی. | A spy game is running! Use `!spystop` to end it.",
                color=0xfee75c)
            return await ctx.send(embed=e, delete_after=10)
        if ctx.author in game["players"]:
            e = discord.Embed(
                title="⚠️ پێشتر بەشداربووی | Already in Lobby",
                description="تۆ پێشتر لە لۆبیدایی! دوگمەی **Leave** بکە. | You're already in the lobby! Use the **Leave** button.",
                color=0xfee75c)
            return await ctx.send(embed=e, delete_after=8)
        game["players"].append(ctx.author)
        try:
            await game["lobby_msg"].edit(embed=_spy_lobby_embed(gid, game.get("countdown", SPY_LOBBY_TIMEOUT)))
        except Exception:
            pass
        e = discord.Embed(
            title="✅ بەشداربوویت! | Joined the lobby!",
            description=f"{ctx.author.mention} بەشداری لۆبیی یاری سیخوڕ بوو! | joined the Spy Game lobby!",
            color=0x57f287)
        return await ctx.send(embed=e, delete_after=8)

    spy_games[gid] = {
        "players":   [ctx.author],
        "started":   False,
        "spy":       None,
        "location":  None,
        "voting":    False,
        "lobby_msg": None,
        "countdown": SPY_LOBBY_TIMEOUT,
    }
    view  = SpyLobbyView(gid, ctx.channel)
    embed = _spy_lobby_embed(gid, SPY_LOBBY_TIMEOUT)
    msg   = await ctx.send(embed=embed, view=view)
    spy_games[gid]["lobby_msg"]  = msg
    spy_games[gid]["lobby_task"] = asyncio.get_event_loop().create_task(
        _spy_lobby_task(gid, ctx.channel, view)
    )


@bot.command(name="spyvote")
async def spy_vote_cmd(ctx):
    if not ctx.guild:
        return await ctx.send("This command only works in a server. | ئەم فەرمانە تەنها لە سێرڤەر کاردەکات.")
    gid  = ctx.guild.id
    game = spy_games.get(gid)
    if not game or not game["started"]:
        e = discord.Embed(title="❌ هیچ یارییەکی چالاکی نییە | No Active Game",
                          description="هیچ یارییەک ناکرێت! `!spy` بەکارهێنە. | No game running! Use `!spy`.", color=0xed4245)
        return await ctx.send(embed=e)
    if game.get("voting"):
        e = discord.Embed(title="🗳️ پێشتر دەنگدرا | Already Voting",
                          description="دەنگدان ئێستا کراوەیە! | Voting is already open!", color=0xfee75c)
        return await ctx.send(embed=e)
    e = discord.Embed(
        title="🗳️ دەنگدانی زوو داوایکرا! | Early Vote Called!",
        description=f"{ctx.author.mention} داوای دەنگدانی زووی کرد! | called for an early vote!\nدەنگدانەکە ئێستا دەکرێتەوە… | Opening the ballot now…",
        color=0xfee75c)
    await ctx.send(embed=e)
    await _start_spy_vote(gid, ctx.channel)


@bot.command(name="spystop")
async def spy_stop(ctx):
    if not ctx.guild:
        return await ctx.send("This command only works in a server. | ئەم فەرمانە تەنها لە سێرڤەر کاردەکات.")
    game = spy_games.pop(ctx.guild.id, None)
    if not game:
        e = discord.Embed(title="❌ هیچ شتێک بۆ هەڵوەشاندنەوە نییە | Nothing to Stop",
                          description="هیچ یاری سیخوڕی چالاکی نەدۆزرایەوە. | No active Spy Game found.", color=0xed4245)
        return await ctx.send(embed=e)
    task = game.get("lobby_task")
    if task:
        task.cancel()
    spy_name = game["spy"].display_name if game.get("spy") else "نەزانراو | Unknown"
    loc      = game.get("location") or "نەزانراو | Unknown"
    e = discord.Embed(
        title="🛑 یاری هەڵوەشاندرایەوە — GAME TERMINATED | کۆتایی یاری",
        description=(
            f"```diff\n- CANCELLED BY {ctx.author.display_name.upper()} | هەڵوەشاندرایەوە\n```\n"
            f"🕵️ سیخوڕەکە بوو | The spy was: **{spy_name}**\n"
            f"📍 شوێنی کۆتایی | Last location: **{loc}**"
        ),
        color=0xed4245)
    e.set_footer(text="!spy بنووسە بۆ یاریکردنی دووبارە | Use $spy to play again")
    await ctx.send(embed=e)


@bot.command(name="spyleave")
async def spy_leave(ctx):
    if not ctx.guild:
        return await ctx.send("This command only works in a server. | ئەم فەرمانە تەنها لە سێرڤەر کاردەکات.")
    game = spy_games.get(ctx.guild.id)
    if not game:
        e = discord.Embed(title="❌ هیچ لۆبییەک نییە | No Lobby",
                          description="هیچ لۆبیی چالاکی بۆ جێهێشتن نییە. | No active lobby to leave.", color=0xed4245)
        return await ctx.send(embed=e)
    if game["started"]:
        e = discord.Embed(title="🚫 یاری بەردەوامە | Game Running",
                          description="ناتوانیت لە ناوەندی یاری بچیت! `!spystop` بەکارهێنە. | Can't leave mid-game! Use `!spystop`.", color=0xed4245)
        return await ctx.send(embed=e)
    player = next((p for p in game["players"] if p.id == ctx.author.id), None)
    if not player:
        e = discord.Embed(title="⚠️ لە لۆبیدا نییت | Not in Lobby",
                          description="تۆ لە لۆبیدا نییت! | You're not in the lobby!", color=0xfee75c)
        return await ctx.send(embed=e)
    game["players"].remove(player)
    remaining = len(game["players"])
    e = discord.Embed(
        title="🚪 ئاجێنت چوو | Agent Left",
        description=f"**{ctx.author.display_name}** لۆبی جێهێشت. | left the lobby.\n`{remaining}` یاریزان ماوەتەوە. | player(s) remaining.",
        color=0x2b2d31)
    e.set_footer(text="!spy بنووسە بۆ بەشداریکردنی دووبارە | Type $spy to rejoin")
    await ctx.send(embed=e)
    if not game["players"]:
        task = game.get("lobby_task")
        if task:
            task.cancel()
        spy_games.pop(ctx.guild.id, None)
        e2 = discord.Embed(
            title="💀 لۆبی بەتاڵ — Disbanded | هەڵوەشایەوە",
            description="هیچ یاریزانێک نەماوە. یاری هەڵوەشایەوە.\nUse `!spy` to start fresh! | `!spy` بەکارهێنە بۆ دەستپێکردنی نوێ!",
            color=0x2b2d31)
        await ctx.send(embed=e2)


@bot.command(name="spystatus")
async def spy_status(ctx):
    if not ctx.guild:
        return await ctx.send("This command only works in a server. | ئەم فەرمانە تەنها لە سێرڤەر کاردەکات.")
    game = spy_games.get(ctx.guild.id)
    if not game:
        e = discord.Embed(title="❌ هیچ یارییەکی چالاکی نییە | No Active Game",
                          description="هیچ یاری سیخوڕی ناکرێت.\n`!spy` بنووسە بۆ دەستپێکردن! | Use `!spy` to start one!", color=0xed4245)
        return await ctx.send(embed=e)
    if game["started"] and game.get("voting"):
        phase, color = "🔴 قۆناغی دەنگدان | Voting Phase", 0xfee75c
    elif game["started"]:
        phase, color = "🟢 نووسراوە — دوور بەردەوامە | Discussion Round", 0x57f287
    else:
        phase, color = "🟡 لۆبی — چاوەڕوانی یاریزانان | Lobby", 0x5865f2
    roster = "\n".join(
        f"{SPY_MEDALS[i]} **{p.display_name}**" for i, p in enumerate(game["players"])
    ) or "*هێشتا هیچ یاریزانێک نییە | No players yet*"
    countdown = game.get("countdown", 0)
    e = discord.Embed(title="🕵️ SPY GAME — STATUS REPORT | ڕاپۆرتی دۆخ", color=color)
    e.add_field(name="📡 قۆناغ | Phase",       value=phase,                           inline=True)
    e.add_field(name="👥 ئاجێنتەکان | Agents", value=f"**{len(game['players'])}**",   inline=True)
    if not game["started"] and countdown:
        e.add_field(name="⏳ کاوت داون | Countdown", value=f"`{countdown}s`",          inline=True)
    e.add_field(name="🗂️ لیستی یاریزانان | Roster", value=roster,                    inline=False)
    if not game["started"]:
        cnt    = len(game["players"])
        needed = max(0, 3 - cnt)
        bar    = "🟩" * min(cnt, 3) + "⬛" * max(0, 3 - cnt)
        e.add_field(
            name="🎯 ئامادەیی | Readiness",
            value=f"{bar} {'✅ ئامادەی دەستپێکردن! | Ready!' if not needed else f'پێویستمانە بە **{needed}** تری | Need **{needed}** more'}",
            inline=False)
    e.set_footer(text="!spy دەستپێکردن • $spyvote دەنگدان • $spystop هەڵوەشاندن • $spyleave جێبهێشتن")
    await ctx.send(embed=e)


# --- MUSIC ---

import yt_dlp as _ytdlp_lib

_music_log = logging.getLogger("music")
logging.getLogger("yt_dlp").setLevel(logging.ERROR)

_pool = _cf.ThreadPoolExecutor(max_workers=4, thread_name_prefix="music")

_YDL_OPTS = {
    # Prefer direct HTTP streams; fallback to adaptive only if nothing else works
    "format": "bestaudio[protocol=https]/bestaudio[protocol=http]/bestaudio/best",
    "noplaylist": True,
    "quiet": True,
    "no_warnings": True,
    "skip_download": True,
    "geo_bypass": True,
    "nocheckcertificate": True,
    "ignoreerrors": True,
    "source_address": "0.0.0.0",
    "socket_timeout": 15,
    "retries": 3,
    "extractor_retries": 3,
    "http_chunk_size": 1048576,
}

# Default User-Agent FFmpeg will send when no headers are provided
_DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

def _build_ffmpeg_opts(http_headers: dict) -> dict:
    """Build FFmpeg options, injecting yt-dlp HTTP headers so CDNs accept the connection."""
    h = dict(http_headers or {})
    h.setdefault("User-Agent", _DEFAULT_UA)
    # Format as FFmpeg -headers value: each header on its own line ending with \r\n
    header_block = "".join(f"{k}: {v}\r\n" for k, v in h.items())
    return {
        "before_options": (
            f"-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 "
            f"-nostdin -loglevel warning "
            f"-headers \"{header_block}\""
        ),
        "options": "-vn",
    }

_mcache: dict = {}
_MCACHE_MAX = 60

# ── Guild state ────────────────────────────────────────────────────────────────

class GuildPlayer:
    __slots__ = ("queue", "current", "volume", "loop", "loop_queue", "start_time")
    def __init__(self):
        self.queue:       list  = []
        self.current:     dict  = None
        self.volume:      float = 0.80
        self.loop:        bool  = False
        self.loop_queue:  bool  = False
        self.start_time:  float = 0.0

_players: dict = {}

def get_player(guild_id: int) -> GuildPlayer:
    if guild_id not in _players:
        _players[guild_id] = GuildPlayer()
    return _players[guild_id]

# ── yt-dlp helpers ─────────────────────────────────────────────────────────────

def _ydl_extract(full_query: str):
    try:
        with _ytdlp_lib.YoutubeDL(_YDL_OPTS) as ydl:
            info = ydl.extract_info(full_query, download=False)
        if not info:
            return None
        if "entries" in info:
            info = next((e for e in info["entries"] if e), None)
        if not info:
            return None
        # Try top-level url first; then walk formats picking best audio bitrate
        stream = info.get("url")
        headers = dict(info.get("http_headers") or {})
        if not stream:
            for fmt in sorted(info.get("formats") or [], key=lambda f: f.get("abr") or 0, reverse=True):
                if fmt.get("acodec", "none") != "none" and fmt.get("url"):
                    stream = fmt["url"]
                    # Use format-level headers if present (they may differ from top-level)
                    if fmt.get("http_headers"):
                        headers = dict(fmt["http_headers"])
                    break
        if not stream:
            return None
        info["_stream_url"] = stream
        info["_http_headers"] = headers
        return info
    except Exception as exc:
        _music_log.debug("ydl error (%s): %s", full_query[:50], exc)
        return None

def _spotify_title(spotify_url: str) -> str:
    """Use Spotify's public oEmbed endpoint (no API key needed) to get track title."""
    import urllib.request, urllib.parse
    try:
        url = f"https://open.spotify.com/oembed?url={urllib.parse.quote(spotify_url, safe='')}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = json.loads(resp.read())
        return data.get("title", "").strip() or ""
    except Exception:
        return ""

def _friendly_source(info: dict) -> str:
    """Return a clean platform name from yt-dlp extractor info."""
    ext = (info.get("extractor_key") or info.get("extractor") or "").lower()
    mapping = {
        "youtube":      "YouTube",
        "soundcloud":   "SoundCloud",
        "spotify":      "Spotify",
        "bandcamp":     "Bandcamp",
        "twitch":       "Twitch",
        "vimeo":        "Vimeo",
        "dailymotion":  "Dailymotion",
        "tiktok":       "TikTok",
        "twitter":      "Twitter/X",
        "instagram":    "Instagram",
        "facebook":     "Facebook",
        "reddit":       "Reddit",
        "bilibili":     "Bilibili",
        "niconico":     "NicoNico",
        "mixcloud":     "Mixcloud",
        "audiomack":    "Audiomack",
        "rumble":       "Rumble",
    }
    for key, label in mapping.items():
        if key in ext:
            return label
    uploader = info.get("extractor_key") or "Direct"
    return uploader

async def fetch_track(query: str):
    loop = asyncio.get_event_loop()
    key = query.strip().lower()
    if key in _mcache:
        return _mcache[key], ""
    is_url = query.startswith(("http://", "https://"))

    # ── Spotify URL: use public oEmbed to get title → search YouTube ──────────
    if is_url and "spotify.com" in query:
        search_q = await loop.run_in_executor(_pool, lambda: _spotify_title(query))
        if not search_q:
            return None, "Couldn't read that Spotify link. Try pasting the song name instead. | ئەم لینکی Spotify نەتوانرا بخوێنرێتەوە. ناوی گۆرانیەکە بنووسەرەوە."
        yt_res = await loop.run_in_executor(_pool, lambda: _ydl_extract("ytsearch1:" + search_q))
        if isinstance(yt_res, dict):
            track = _build_track(yt_res, source="Spotify→YouTube")
            _mcache_put(key, track)
            return track, ""
        sc_res = await loop.run_in_executor(_pool, lambda: _ydl_extract("scsearch1:" + search_q))
        if isinstance(sc_res, dict):
            track = _build_track(sc_res, source="Spotify→SoundCloud")
            _mcache_put(key, track)
            return track, ""
        return None, f"Found Spotify track **{search_q}** but couldn't stream it. | گۆرانیەکە لە Spotify دۆزرایەوە بەڵام ستریمی نەدۆزرایەوە."

    # ── Any other direct URL (YouTube, SoundCloud, Twitch, Bandcamp, etc.) ─────
    if is_url:
        info = await loop.run_in_executor(_pool, lambda: _ydl_extract(query))
        if info:
            src = _friendly_source(info)
            track = _build_track(info, source=src)
            _mcache_put(key, track)
            return track, ""
        return None, "Could not load that URL. It may be private, age-restricted, or from an unsupported site. | ئەم لینکە نەتوانرا بار بکرێت. تایبەتی، مەوایپێکراو، یان مەرجبەندی تەمەنی بۆ کراوە."

    # ── Search term: YouTube + SoundCloud in parallel ─────────────────────────
    yt_fut = loop.run_in_executor(_pool, lambda: _ydl_extract("ytsearch1:" + query))
    sc_fut = loop.run_in_executor(_pool, lambda: _ydl_extract("scsearch1:" + query))
    yt_res, sc_res = await asyncio.gather(yt_fut, sc_fut, return_exceptions=True)
    if isinstance(yt_res, dict):
        track = _build_track(yt_res, source="YouTube")
        _mcache_put(key, track)
        return track, ""
    if isinstance(sc_res, dict):
        track = _build_track(sc_res, source="SoundCloud")
        _mcache_put(key, track)
        return track, ""
    return None, "No results found on YouTube or SoundCloud. Try a different search or paste a direct link. | هیچ ئەنجامێک نەدۆزرایەوە. پەیڤی تر هەوڵبدەرەوە یان لینکی ڕاستەوخۆ بچسپێنە."

def _build_track(info: dict, source: str) -> dict:
    return {
        "title":        info.get("title", "Unknown Title | ناونەزانراو"),
        "url":          info["_stream_url"],
        "webpage_url":  info.get("webpage_url") or info.get("original_url", ""),
        "thumbnail":    info.get("thumbnail"),
        "duration":     info.get("duration"),
        "uploader":     info.get("uploader") or info.get("channel") or "Unknown Artist | هونەرمەندی نەزانراو",
        "source":       source,
        "requester":    None,
        "channel_id":   0,
        "http_headers": info.get("_http_headers") or {},
    }

def _mcache_put(key: str, value: dict):
    if len(_mcache) >= _MCACHE_MAX:
        del _mcache[next(iter(_mcache))]
    _mcache[key] = value

# ── Playback engine ────────────────────────────────────────────────────────────

def _fmt_dur(secs) -> str:
    if not secs:
        return "🔴 Live"
    s = int(secs)
    h, r = divmod(s, 3600)
    m, sec = divmod(r, 60)
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"

def _after_track(guild_id: int, error):
    if error:
        _music_log.warning("Player error guild %s: %s", guild_id, error)
    asyncio.run_coroutine_threadsafe(_advance(guild_id), bot.loop)

async def _advance(guild_id: int):
    guild = bot.get_guild(guild_id)
    if not guild:
        return
    vc = guild.voice_client
    if not vc:
        return
    player = get_player(guild_id)
    if player.loop and player.current:
        track = player.current
    else:
        if player.loop_queue and player.current:
            player.queue.append(player.current)
        if not player.queue:
            player.current = None
            return
        track = player.queue.pop(0)
        player.current = track
    await _play_track(vc, player, track, guild_id)

async def _play_track(vc, player: GuildPlayer, track: dict, guild_id: int):
    # Always re-fetch a fresh stream URL right before playing.
    # yt-dlp stream URLs (YouTube especially) expire within seconds.
    loop = asyncio.get_event_loop()
    wp = track.get("webpage_url") or track.get("url", "")
    fresh = None
    if wp:
        fresh = await loop.run_in_executor(_pool, lambda: _ydl_extract(wp))
    if fresh:
        track["url"]          = fresh["_stream_url"]
        track["http_headers"] = fresh.get("_http_headers") or {}
        if fresh.get("thumbnail"):
            track["thumbnail"] = fresh["thumbnail"]
        if fresh.get("uploader") or fresh.get("channel"):
            track["uploader"] = fresh.get("uploader") or fresh.get("channel")
    else:
        # webpage_url failed — abort cleanly instead of letting FFmpeg crash
        _music_log.warning("Could not refresh stream URL for: %s", track.get("title"))
        ch = bot.get_channel(track.get("channel_id", 0))
        if ch:
            try:
                await ch.send(embed=_m_err(
                    f"⚠️ Couldn't load stream for **{track['title']}**, skipping… | نەتوانرا ستریمی **{track['title']}** بار بکرێت، تێدەپەڕێت…"
                ))
            except discord.Forbidden:
                pass
        await _advance(guild_id)
        return
    # Build FFmpeg options with the headers yt-dlp provided so CDNs accept the connection
    ffmpeg_opts = _build_ffmpeg_opts(track.get("http_headers") or {})
    try:
        src = discord.FFmpegPCMAudio(track["url"], **ffmpeg_opts)
        src = discord.PCMVolumeTransformer(src, volume=player.volume)
        vc.play(src, after=lambda e: _after_track(guild_id, e))
        player.start_time = time.time()
    except Exception as exc:
        _music_log.error("FFmpeg error for %s: %s", track.get("title"), exc)
        ch = bot.get_channel(track.get("channel_id", 0))
        if ch:
            try:
                await ch.send(embed=_m_err(
                    f"⚠️ FFmpeg failed for **{track['title']}**, skipping… | نەتوانرا **{track['title']}** بلێدرێت، تێدەپەڕێت…"
                ))
            except discord.Forbidden:
                pass
        await _advance(guild_id)
        return
    ch = bot.get_channel(track.get("channel_id", 0))
    if ch:
        try:
            await ch.send(embed=_np_embed(track, player, guild_id))
        except discord.Forbidden:
            pass

# ── Embed builders ─────────────────────────────────────────────────────────────

_SRC_COLOR = {
    "YouTube":           discord.Color.from_rgb(255, 0, 0),
    "SoundCloud":        discord.Color.from_rgb(255, 100, 0),
    "Spotify→YouTube":   discord.Color.from_rgb(30, 215, 96),
    "Spotify→SoundCloud":discord.Color.from_rgb(30, 215, 96),
    "Bandcamp":          discord.Color.from_rgb(29, 157, 118),
    "Twitch":            discord.Color.from_rgb(145, 70, 255),
    "Vimeo":             discord.Color.from_rgb(26, 183, 234),
    "Dailymotion":       discord.Color.from_rgb(0, 120, 220),
    "TikTok":            discord.Color.from_rgb(0, 0, 0),
    "Twitter/X":         discord.Color.from_rgb(29, 161, 242),
    "Mixcloud":          discord.Color.from_rgb(82, 46, 139),
    "Audiomack":         discord.Color.from_rgb(255, 165, 0),
    "Rumble":            discord.Color.from_rgb(133, 193, 77),
    "Direct":            discord.Color.from_rgb(88, 101, 242),
}
_SRC_EMOJI = {
    "YouTube":           "▶️",
    "SoundCloud":        "☁️",
    "Spotify→YouTube":   "🟢",
    "Spotify→SoundCloud":"🟢",
    "Bandcamp":          "🎸",
    "Twitch":            "🟣",
    "Vimeo":             "🎬",
    "Dailymotion":       "📺",
    "TikTok":            "🎵",
    "Twitter/X":         "🐦",
    "Mixcloud":          "🎛️",
    "Audiomack":         "🎧",
    "Rumble":            "📹",
}

def _np_embed(track: dict, player: GuildPlayer, guild_id: int) -> discord.Embed:
    src   = track.get("source", "")
    emoji = _SRC_EMOJI.get(src, "🎵")
    color = _SRC_COLOR.get(src, discord.Color.blurple())
    wp    = track.get("webpage_url", "")
    title = f"[{track['title']}]({wp})" if wp else track["title"]
    embed = discord.Embed(
        title=f"{emoji}  Now Playing | ئێستا دەلێدرێت",
        description=f"### {title}",
        color=color,
        timestamp=datetime.datetime.utcnow(),
    )
    if track.get("thumbnail"):
        embed.set_thumbnail(url=track["thumbnail"])
    dur       = _fmt_dur(track.get("duration"))
    vol       = int(player.volume * 100)
    q_len     = len(player.queue)
    elapsed   = time.time() - player.start_time
    total_sec = track.get("duration") or 0
    if total_sec > 0:
        pct    = min(elapsed / total_sec, 1.0)
        filled = int(pct * 18)
        bar    = "▓" * filled + "░" * (18 - filled)
        prog   = f"`{_fmt_dur(elapsed)} {bar} {dur}`"
    else:
        prog = f"`{dur}`"
    embed.add_field(name="⏱️ Progress | پێشکەوتن",   value=prog,                          inline=False)
    embed.add_field(name="🎤 Artist | هونەرمەند",    value=track.get("uploader", "?"),    inline=True)
    embed.add_field(name="🔈 Volume | دەنگ",         value=f"`{vol}%`",                    inline=True)
    embed.add_field(name="🔊 Source | سەرچاوە",      value=f"`{src}`",                     inline=True)
    loop_state = "🔁 Track | گۆرانی" if player.loop else ("🔄 Queue | ڕیز" if player.loop_queue else "➡️ Off | ناچالاک")
    embed.add_field(name="🔁 Loop | دووبارەکردنەوە", value=loop_state,                     inline=True)
    embed.add_field(name="📋 In Queue | لە ڕیزدا",  value=f"`{q_len} track(s)`",          inline=True)
    if track.get("requester"):
        embed.add_field(name="👤 Requested by | داواکراوە لەلایەن", value=f"<@{track['requester']}>", inline=True)
    if q_len:
        embed.add_field(name="⏭️ Up Next | دواتر", value=f"`{player.queue[0]['title'][:50]}`", inline=False)
    embed.set_footer(text="!skip • $pause • $stop • $queue • $np • $loop • $vol  |  تێپەڕاندن • وەستاندن • ڕاگرتن")
    return embed

def _queue_embed(player: GuildPlayer) -> discord.Embed:
    embed = discord.Embed(
        title="📋  Music Queue | ڕیزی مۆسیقا",
        color=discord.Color.blurple(),
        timestamp=datetime.datetime.utcnow(),
    )
    if player.current:
        src   = player.current.get("source", "")
        emoji = _SRC_EMOJI.get(src, "🎵")
        dur   = _fmt_dur(player.current.get("duration"))
        loop_tag = " 🔁" if player.loop else ""
        embed.add_field(
            name=f"▶️  Now Playing | ئێستا دەلێدرێت{loop_tag}",
            value=f"{emoji} **{player.current['title'][:55]}** `[{dur}]`",
            inline=False,
        )
    if not player.queue:
        embed.add_field(
            name="📭  Queue is empty | ڕیزەکە بەتاڵە",
            value="Use `!play <song>` to add music! | `!play <گۆرانی>` بەکارهێنە!",
            inline=False,
        )
    else:
        shown = player.queue[:12]
        lines = []
        for i, t in enumerate(shown):
            src   = t.get("source", "")
            emoji = _SRC_EMOJI.get(src, "🎵")
            dur   = _fmt_dur(t.get("duration"))
            lines.append(f"`{i+1}.` {emoji} **{t['title'][:48]}** `[{dur}]`")
        if len(player.queue) > 12:
            lines.append(f"\n*…و {len(player.queue)-12} گۆرانیی تر | and {len(player.queue)-12} more tracks*")
        embed.add_field(name="📋  Up Next | دواتر", value="\n".join(lines), inline=False)
    total = sum(t.get("duration") or 0 for t in player.queue)
    vol   = int(player.volume * 100)
    lq    = "🔄 Queue loop ON | دووبارەکردنەوەی ڕیز" if player.loop_queue else ""
    embed.set_footer(text=f"{len(player.queue)} track(s) | گۆرانی  •  Total | کۆی گشتی: {_fmt_dur(total)}  •  Vol | دەنگ: {vol}%  {lq}")
    return embed

def _m_ok(msg: str, color=discord.Color.green()) -> discord.Embed:
    return discord.Embed(description=msg, color=color)

def _m_err(msg: str) -> discord.Embed:
    return discord.Embed(description=msg, color=discord.Color.red())

def _m_warn(msg: str) -> discord.Embed:
    return discord.Embed(description=msg, color=discord.Color.orange())

async def _ensure_voice(ctx):
    if not ctx.author.voice or not ctx.author.voice.channel:
        await ctx.send(embed=_m_err("🔇  Join a voice channel first! | پێشتر بەشداری کەناڵی دەنگ بکە."))
        return None
    target = ctx.author.voice.channel
    vc = ctx.guild.voice_client
    if vc is None:
        try:
            vc = await target.connect(self_deaf=True)
        except Exception as exc:
            await ctx.send(embed=_m_err(f"❌  Could not join **{target.name}**: `{exc}`"))
            return None
    elif vc.channel != target:
        await vc.move_to(target)
    return vc

# ── Idle disconnect task ───────────────────────────────────────────────────────

@tasks.loop(minutes=5)
async def idle_check():
    for guild in bot.guilds:
        vc = guild.voice_client
        if vc and not vc.is_playing() and not vc.is_paused():
            player = get_player(guild.id)
            if not player.queue and not player.current:
                try:
                    await vc.disconnect()
                except Exception:
                    pass

# ── Music commands ─────────────────────────────────────────────────────────────

@bot.command(name="volume", aliases=["vol"])
async def volume(ctx, vol: int = None):
    player = get_player(ctx.guild.id)
    if vol is None:
        cur = int(player.volume * 100)
        await ctx.send(embed=_m_ok(f"🔈  Current volume | دەنگی ئێستا: **{cur}%**  •  `!volume <1-200>`", discord.Color.blurple()))
        return
    if not 1 <= vol <= 200:
        await ctx.send(embed=_m_err("⚠️  Volume must be between **1** and **200**. | دەنگ دەبێت لە نێوان **١** و **٢٠٠** بێت."))
        return
    player.volume = vol / 100
    vc = ctx.guild.voice_client
    if vc and vc.source and isinstance(vc.source, discord.PCMVolumeTransformer):
        vc.source.volume = player.volume
    bar = "🟩" * min(int(vol / 10), 10) + "⬛" * max(0, 10 - int(vol / 10))
    await ctx.send(embed=discord.Embed(title="🔈  Volume | دەنگ", description=f"{bar}\n**{vol}%**", color=discord.Color.green()))

@bot.command(name="loop")
async def loop_cmd(ctx, mode: str = "track"):
    player = get_player(ctx.guild.id)
    mode = mode.lower()
    if mode in ("track", "song", "t"):
        player.loop       = not player.loop
        player.loop_queue = False
        state = "enabled 🔁 | چالاک کرا" if player.loop else "disabled | ناچالاک کرا"
        await ctx.send(embed=_m_ok(f"🔁  Track loop **{state}**. | دووبارەکردنەوەی گۆرانی"))
    elif mode in ("queue", "q"):
        player.loop_queue = not player.loop_queue
        player.loop       = False
        state = "enabled 🔄 | چالاک کرا" if player.loop_queue else "disabled | ناچالاک کرا"
        await ctx.send(embed=_m_ok(f"🔄  Queue loop **{state}**. | دووبارەکردنەوەی ڕیز"))
    elif mode in ("off", "none", "0"):
        player.loop       = False
        player.loop_queue = False
        await ctx.send(embed=_m_ok("➡️  Loop **disabled**. | چرکەپشتیکردنەوە ناچالاک کرا."))
    else:
        await ctx.send(embed=_m_warn("Usage | بەکارهێنان: `!loop track` | `!loop queue` | `!loop off`"))

@bot.command(name="qremove", aliases=["qrm"])
async def qremove(ctx, index: int):
    player = get_player(ctx.guild.id)
    if not player.queue:
        await ctx.send(embed=_m_warn("⚠️  The queue is empty. | ڕیزەکە بەتاڵە."))
        return
    if not 1 <= index <= len(player.queue):
        await ctx.send(embed=_m_err(f"⚠️  Invalid position. Queue has **{len(player.queue)}** track(s). | ژمارەی نادروستە."))
        return
    removed = player.queue.pop(index - 1)
    await ctx.send(embed=_m_ok(f"🗑️  Removed **{removed['title']}** from the queue. | لە ڕیزەکە لابرا.", discord.Color.orange()))

@bot.command()
async def snipe(ctx):
    s = sniped.get(ctx.channel.id)
    if not s:
        await ctx.send("Nothing to snipe here. | هیچ شتێک بۆ سنایپکردن ئێرە نییە.")
        return
    embed = discord.Embed(description=s["content"], color=discord.Color.red())
    embed.set_author(name=s["author"], icon_url=s["author_avatar"])
    embed.set_footer(text=f"Deleted | سڕدرایەوە • {time.strftime('%H:%M:%S', time.gmtime(s['time']))} UTC")
    await ctx.send(embed=embed)

@bot.command()
async def editsnipe(ctx):
    s = edit_sniped.get(ctx.channel.id)
    if not s:
        await ctx.send("No edits to snipe here. | هیچ دەستکاریکردنێک بۆ سنایپکردن ئێرە نییە.")
        return
    embed = discord.Embed(color=discord.Color.orange())
    embed.set_author(name=s["author"], icon_url=s["author_avatar"])
    embed.add_field(name="Before | پێش", value=s["before"][:1024], inline=False)
    embed.add_field(name="After | دوا", value=s["after"][:1024], inline=False)
    embed.set_footer(text=f"Edited | دەستکاریکرا • {time.strftime('%H:%M:%S', time.gmtime(s['time']))} UTC")
    await ctx.send(embed=embed)

@bot.command()
async def membercount(ctx):
    await ctx.send(f"👥 **{ctx.guild.member_count}** members | ئەندام")

@bot.command()
async def humancount(ctx):
    n = sum(1 for m in ctx.guild.members if not m.bot)
    await ctx.send(f"👤 **{n}** humans | مرۆڤ")

@bot.command()
async def botcount(ctx):
    n = sum(1 for m in ctx.guild.members if m.bot)
    await ctx.send(f"🤖 **{n}** bots | بۆت")

@bot.command()
async def channelcount(ctx):
    await ctx.send(f"📺 **{len(ctx.guild.channels)}** total channels | کۆی کەناڵەکان")

@bot.command()
async def textchannels(ctx):
    await ctx.send(f"💬 **{len(ctx.guild.text_channels)}** text channels | کەناڵی نووسراوە")

@bot.command()
async def voicechannels(ctx):
    await ctx.send(f"🎙️ **{len(ctx.guild.voice_channels)}** voice channels | کەناڵی دەنگ")

@bot.command()
async def rolecount(ctx):
    await ctx.send(f"🏷️ **{len(ctx.guild.roles)}** roles | رۆڵ")

@bot.command()
async def emojis(ctx):
    e = ctx.guild.emojis
    if not e:
        await ctx.send("No custom emojis. | هیچ ئیمۆجیی تایبەتی نییە.")
        return
    text = " ".join(str(em) for em in e[:30])
    extra = "" if len(e) <= 30 else f"\n...and {len(e) - 30} more | و {len(e) - 30} تری"
    await ctx.send(text + extra)

@bot.command()
async def emojicount(ctx):
    await ctx.send(f"😀 **{len(ctx.guild.emojis)}** custom emojis | ئیمۆجیی تایبەت")

@bot.command()
async def boostcount(ctx):
    await ctx.send(f"🚀 Boost level | ئاستی بووست **{ctx.guild.premium_tier}** with | بە **{ctx.guild.premium_subscription_count}** boosts | بووست")

@bot.command()
async def owner(ctx):
    o = ctx.guild.owner
    await ctx.send(f"👑 Server owner | خاوەنی سێرڤەر: {o.mention if o else 'unknown | نەزانراو'}")

@bot.command()
async def oldestmember(ctx):
    members = [m for m in ctx.guild.members if not m.bot and m.joined_at]
    if not members:
        await ctx.send("No members found. | هیچ ئەندامێک نەدۆزرایەوە.")
        return
    m = min(members, key=lambda x: x.joined_at)
    await ctx.send(f"🕰️ Oldest member | کۆنترین ئەندام: {m.mention} (joined | بەشداریکرد {m.joined_at.strftime('%Y-%m-%d')})")

@bot.command()
async def newestmember(ctx):
    members = [m for m in ctx.guild.members if not m.bot and m.joined_at]
    if not members:
        await ctx.send("No members found. | هیچ ئەندامێک نەدۆزرایەوە.")
        return
    m = max(members, key=lambda x: x.joined_at)
    await ctx.send(f"🌱 Newest member | نوێترین ئەندام: {m.mention} (joined | بەشداریکرد {m.joined_at.strftime('%Y-%m-%d')})")

@bot.command()
async def servericon(ctx):
    if ctx.guild.icon:
        embed = discord.Embed(title=f"{ctx.guild.name} icon | ئایکۆنی سێرڤەر")
        embed.set_image(url=ctx.guild.icon.url)
        await ctx.send(embed=embed)
    else:
        await ctx.send("This server has no icon. | ئەم سێرڤەرە هیچ ئایکۆنێکی نییە.")

@bot.command()
async def serverbanner(ctx):
    if ctx.guild.banner:
        embed = discord.Embed(title=f"{ctx.guild.name} banner | بانەری سێرڤەر")
        embed.set_image(url=ctx.guild.banner.url)
        await ctx.send(embed=embed)
    else:
        await ctx.send("This server has no banner. | ئەم سێرڤەرە هیچ بانەرێکی نییە.")

# --- USER STATS ---

@bot.command()
async def userbanner(ctx, member: discord.Member = None):
    member = member or ctx.author
    user = await bot.fetch_user(member.id)
    if user.banner:
        embed = discord.Embed(title=f"{member.display_name}'s banner | بانەری {member.display_name}")
        embed.set_image(url=user.banner.url)
        await ctx.send(embed=embed)
    else:
        await ctx.send(f"{member.display_name} has no banner set. | {member.display_name} هیچ بانەرێکی دانراو نییە.")

@bot.command()
async def joinposition(ctx, member: discord.Member = None):
    member = member or ctx.author
    members = sorted(
        [m for m in ctx.guild.members if m.joined_at],
        key=lambda x: x.joined_at,
    )
    pos = members.index(member) + 1 if member in members else "?"
    await ctx.send(f"{member.mention} joined as member | بەشداری کرد وەک ئەندامی **#{pos}**")

@bot.command()
async def accountage(ctx, member: discord.Member = None):
    member = member or ctx.author
    days = (datetime.datetime.now(datetime.timezone.utc) - member.created_at).days
    await ctx.send(f"{member.mention}'s account is | ئەکاونتی **{days}** days | رۆژ old | کۆنە.")

@bot.command()
async def myid(ctx):
    await ctx.send(f"Your ID | ناسنامەت: `{ctx.author.id}`")

@bot.command(name="mention")
async def mention_cmd(ctx, member: discord.Member):
    await ctx.send(f"`{member.mention}`")

@bot.command()
async def myroles(ctx):
    roles = [r.mention for r in ctx.author.roles if r.name != "@everyone"]
    await ctx.send("Your roles | رۆڵەکانت: " + (", ".join(roles) if roles else "none | هیچ"))

@bot.command()
async def perms(ctx, member: discord.Member = None):
    member = member or ctx.author
    perms_list = [n.replace("_", " ").title() for n, v in member.guild_permissions if v]
    await ctx.send(
        f"**{member.display_name}**'s permissions | مووچەکانی: " +
        (", ".join(perms_list[:25]) + ("..." if len(perms_list) > 25 else "") if perms_list else "none | هیچ")
    )

@bot.command()
async def isbot(ctx, member: discord.Member):
    await ctx.send(f"{'🤖 Yes, ' + member.display_name + ' is a bot. | بەڵێ، بۆتە.' if member.bot else '👤 No, ' + member.display_name + ' is human. | نەخێر، مرۆڤە.'}")

# --- CHANNEL MANAGEMENT ---

@bot.command()
@commands.has_permissions(manage_channels=True)
async def lock(ctx):
    overwrite = ctx.channel.overwrites_for(ctx.guild.default_role)
    overwrite.send_messages = False
    await ctx.channel.set_permissions(ctx.guild.default_role, overwrite=overwrite)
    await ctx.send("🔒 Channel locked. | کەناڵ داخراو.")

@bot.command()
@commands.has_permissions(manage_channels=True)
async def unlock(ctx):
    overwrite = ctx.channel.overwrites_for(ctx.guild.default_role)
    overwrite.send_messages = None
    await ctx.channel.set_permissions(ctx.guild.default_role, overwrite=overwrite)
    await ctx.send("🔓 Channel unlocked. | کەناڵ کراوەیە.")

@bot.command()
@commands.has_permissions(manage_channels=True)
async def slowmode(ctx, seconds: int):
    if seconds < 0 or seconds > 21600:
        await ctx.send("Pick 0-21600 seconds. | لە ٠ بۆ ٢١٦٠٠ چرکە هەڵبژێرە.")
        return
    await ctx.channel.edit(slowmode_delay=seconds)
    await ctx.send(f"🐌 Slowmode set to | مۆدی هێواشکردن دانرا بۆ **{seconds}s**.")

@bot.command()
@commands.has_permissions(manage_channels=True)
async def renamechannel(ctx, *, name: str):
    old = ctx.channel.name
    await ctx.channel.edit(name=name)
    await ctx.send(f"Renamed | ناو گۆڕدرا `#{old}` to | بۆ `#{name}`.")

@bot.command()
@commands.has_permissions(manage_channels=True)
async def settopic(ctx, *, topic: str):
    await ctx.channel.edit(topic=topic)
    await ctx.send("📝 Topic updated. | بابەتەکە نوێکرایەوە.")

@bot.command()
@commands.has_permissions(manage_channels=True)
async def hidechannel(ctx):
    overwrite = ctx.channel.overwrites_for(ctx.guild.default_role)
    overwrite.view_channel = False
    await ctx.channel.set_permissions(ctx.guild.default_role, overwrite=overwrite)
    await ctx.send("🙈 Channel hidden from @everyone. | کەناڵ شاردرایەوە لە @everyone.")

@bot.command()
@commands.has_permissions(manage_channels=True)
async def showchannel(ctx):
    overwrite = ctx.channel.overwrites_for(ctx.guild.default_role)
    overwrite.view_channel = None
    await ctx.channel.set_permissions(ctx.guild.default_role, overwrite=overwrite)
    await ctx.send("👀 Channel visible. | کەناڵ بەرچاوە.")

@bot.command()
@commands.has_permissions(manage_channels=True)
async def nuke(ctx):
    pos = ctx.channel.position
    new_ch = await ctx.channel.clone(reason=f"Nuked by | نوکەکرا لەلایەن {ctx.author}")
    await new_ch.edit(position=pos)
    await ctx.channel.delete()
    await new_ch.send(f"💥 Channel nuked by | کەناڵ نوکەکرا لەلایەن {ctx.author.mention}!")

# --- VOICE MANAGEMENT ---

@bot.command()
@commands.has_permissions(mute_members=True)
async def vcmute(ctx, member: discord.Member):
    await member.edit(mute=True)
    await ctx.send(f"🔇 VC-muted | بێدەنگ کرا لە دەنگدا {member.mention}.")

@bot.command()
@commands.has_permissions(mute_members=True)
async def vcunmute(ctx, member: discord.Member):
    await member.edit(mute=False)
    await ctx.send(f"🔊 VC-unmuted | بێدەنگی لادرا لە دەنگدا {member.mention}.")

@bot.command()
@commands.has_permissions(deafen_members=True)
async def vcdeafen(ctx, member: discord.Member):
    await member.edit(deafen=True)
    await ctx.send(f"🔇 Deafened | گوێ داخرا {member.mention}.")

@bot.command()
@commands.has_permissions(deafen_members=True)
async def vcundeafen(ctx, member: discord.Member):
    await member.edit(deafen=False)
    await ctx.send(f"🔉 Undeafened | گوێ کرایەوە {member.mention}.")

@bot.command()
@commands.has_permissions(move_members=True)
async def vcdisconnect(ctx, member: discord.Member):
    await member.move_to(None)
    await ctx.send(f"⛔ Disconnected | پەیوەندی بڕدرا {member.mention} from voice. | لە دەنگ.")

# --- QUOTES, JOKES, ETC ---

@bot.command()
async def rpsls(ctx, choice: str = None):
    options = ["rock", "paper", "scissors", "lizard", "spock"]
    if not choice or choice.lower() not in options:
        await ctx.send("Usage: `!rpsls <rock|paper|scissors|lizard|spock>` | بەکارهێنان: `!rpsls <بەردەوشک|کاغەز|مەقەس|مار|سپۆک>`")
        return
    user = choice.lower()
    bot_choice = random.choice(options)
    rules = {
        "rock": ["scissors", "lizard"],
        "paper": ["rock", "spock"],
        "scissors": ["paper", "lizard"],
        "lizard": ["paper", "spock"],
        "spock": ["rock", "scissors"],
    }
    if user == bot_choice:
        result = "Tie! | یەکسانە!"
    elif bot_choice in rules[user]:
        result = "You win! 🎉 | تۆ بردیت! 🎉"
    else:
        result = "I win! 🤖 | من بردم! 🤖"
    await ctx.send(f"You | تۆ: **{user}**\nMe | من: **{bot_choice}**\n{result}")

@bot.command()
async def firstmessage(ctx):
    async for m in ctx.channel.history(limit=1, oldest_first=True):
        await ctx.send(f"📜 First message in | یەکەمین پەیام لە #{ctx.channel.name}: {m.jump_url}")
        return
    await ctx.send("No messages found. | هیچ پەیامێک نەدۆزرایەوە.")

@bot.command()
async def vote(ctx, *, question: str):
    msg = await ctx.send(f"📊 **{question}**")
    for emo in ("👍", "👎", "🤷"):
        await msg.add_reaction(emo)

@bot.command()
async def suggest(ctx, *, suggestion: str):
    embed = discord.Embed(title="💡 Suggestion | پێشنیار", description=suggestion[:4000], color=discord.Color.teal())
    embed.set_author(name=str(ctx.author), icon_url=ctx.author.display_avatar.url)
    msg = await ctx.send(embed=embed)
    for emo in ("👍", "👎"):
        await msg.add_reaction(emo)

# --- THE COOLER AFK COMMAND ---

@bot.command()
async def afk(ctx, *, reason: str = "AFK"):
    if ctx.guild is None:
        await ctx.send("AFK only works in a server. | AFK تەنها لە سێرڤەر کاردەکات.")
        return

    key = (ctx.guild.id, ctx.author.id)
    now = time.time()
    if key in afk_cooldowns and (now - afk_cooldowns[key]) < 60:
        remaining = int(60 - (now - afk_cooldowns[key]))
        embed = discord.Embed(
            title="⏰ Slow down! | هێواش بکەرەوە!",
            description=f"You can change your AFK status again in **{remaining}s**. | دەتوانیت دۆخی AFK خۆت بگۆڕیت لە **{remaining}چ** دیکەدا.",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)
        return

    old_nick = ctx.author.nick

    new_nick = f"💤 {ctx.author.display_name}"[:32]
    try:
        await ctx.author.edit(nick=new_nick)
    except (discord.Forbidden, discord.HTTPException):
        pass

    image_url = None
    if ctx.message.attachments:
        for att in ctx.message.attachments:
            if att.content_type and "image" in att.content_type:
                image_url = att.url
                break

    try:
        status_text = f"!afk {reason}"[:128]
        new_activities = [discord.CustomActivity(name=status_text)]
        for a in ctx.author.activities:
            if not isinstance(a, discord.CustomActivity):
                new_activities.append(a)
        await ctx.author.edit(activities=new_activities)
    except Exception:
        pass

    afk_since = time.time()
    afk_users[key] = {
        "reason": reason,
        "since": afk_since,
        "old_nick": old_nick,
        "image_url": image_url
    }
    afk_cooldowns[key] = now
    save_afk()

    afk_moods = ["🌙", "😴", "💤", "🛌", "🎧", "🌌", "☕", "🔇"]
    mood = random.choice(afk_moods)

    embed = discord.Embed(
        title=f"{mood}  Gone AFK | ڕوحستی",
        color=discord.Color.from_rgb(88, 101, 242),
        timestamp=datetime.datetime.utcfromtimestamp(afk_since)
    )
    embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)
    embed.add_field(name="📝 Reason | هۆکار", value=f"*{reason}*", inline=False)
    embed.add_field(name="🕐 AFK Since | AFK لەکاتی", value=f"<t:{int(afk_since)}:R>", inline=True)
    embed.add_field(name="🔔 Pings? | پینگ؟", value="I'll notify others who ping you | ئاگادارکردنەوەی ئەوانەی پینگت دەکەن", inline=True)
    if image_url:
        embed.set_image(url=image_url)
    else:
        embed.set_thumbnail(url=ctx.author.display_avatar.url)
    embed.set_footer(text="Send any message to come back • Your nickname & status are updated | هەر پەیامێک بنێرە بۆ گەڕانەوە • ناو و دۆخت نوێکراوەتەوە")
    await ctx.send(embed=embed)

@bot.command()
async def github(ctx, user: str):
    await ctx.send(f"🐙 https://github.com/{user}")

@bot.command()
async def youtube(ctx, *, query: str):
    q = query.replace(" ", "+")
    await ctx.send(f"▶️ https://www.youtube.com/results?search_query={q}")

@bot.command()
async def google(ctx, *, query: str):
    q = query.replace(" ", "+")
    await ctx.send(f"🔎 https://www.google.com/search?q={q}")

@bot.command()
async def lmgtfy(ctx, *, query: str):
    q = query.replace(" ", "+")
    await ctx.send(f"https://lmgtfy.app/?q={q}")

@bot.command()
async def serverid(ctx):
    await ctx.send(f"Server ID | ناسنامەی سێرڤەر: `{ctx.guild.id}`")

@bot.command()
async def channelid(ctx):
    await ctx.send(f"Channel ID | ناسنامەی کەناڵ: `{ctx.channel.id}`")

@bot.command()
async def messageid(ctx):
    await ctx.send(f"Your message ID | ناسنامەی پەیامەکەت: `{ctx.message.id}`")

@bot.command()
async def invite(ctx):
    try:
        inv = await ctx.channel.create_invite(max_age=3600, max_uses=1, reason="!invite")
        await ctx.send(f"📨 {inv.url}")
    except discord.Forbidden:
        await ctx.send("I don't have permission to create invites. | مووچەم نییە داواکاری دروست بکەم.")

@bot.command()
async def about(ctx):
    embed = discord.Embed(
        title="About | دەربارە",
        description="A multipurpose Discord bot built with discord.py — moderation, leveling, fun, games, music, economy and more. | بۆتێکی پرپشکی Discord دروستکراوە بە discord.py — کونترۆڵ، ئاست، کێف، یاری، مۆسیقا، ئابووری و زیاتر.",
        color=discord.Color.blurple(),
    )
    embed.add_field(name="Commands | فەرمانەکان", value="Use `!help` to see them all. | `!help` بەکارهێنە بۆ بینینی هەموویان.", inline=False)
    embed.add_field(name="Uptime | ماوەی چالاکی", value=fmt_uptime(time.time() - START_TIME), inline=False)
    await ctx.send(embed=embed)


# ── HELP DATA ─────────────────────────────────────────────────────────────────
HELP_CATEGORIES = [
    ("📢 General | گشتی", [
        ("!hello",                            "Bot says hello | بۆت سڵاو دەکاتەوە"),
        ("!dm @member <message>",             "Send a DM to yourself | پەیامی تایبەت"),
        ("!reply",                            "Bot replies to your message | بۆت وەڵامت دەداتەوە"),
        ("!say <message>",                    "Bot repeats your message | بۆت پەیامەکەت دووبارە دەکاتەوە"),
        ("!poll <question>",                  "Create a yes/no poll | دەنگدانی خێرا دروست بکە"),
        ("!invite",                           "Get bot invite link | لینکی بانگهێشتکردن"),
        ("!language <en|ku>",                 "Switch bot language | زمانی بۆت بگۆڕە"),
        ("!about",                            "About this bot | دەربارەی ئەم بۆتە"),
        ("!apply",                            "Staff application form | فۆرمی داواکاریی ستاف"),
        ("!stafflist",                        "Show all staff members | لیستی هەموو ستافەکان"),
    ]),
    ("ℹ️ Info | زانیاری", [
        ("!ping",                             "Bot latency | لەنجی بۆت"),
        ("!uptime",                           "Bot uptime | ماوەی چالاکیی بۆت"),
        ("!serverinfo",                       "Server details | وردەکارییەکانی سێرڤەر"),
        ("!userinfo [@member]",               "User details | وردەکارییەکانی بەکارهێنەر"),
        ("!avatar [@member]",                 "Show avatar | وێنەی پرۆفایل"),
        ("!botinfo",                          "Bot details | وردەکارییەکانی بۆت"),
        ("!channelinfo [#channel]",           "Channel details | وردەکارییەکانی چانێل"),
        ("!roles",                            "List all roles | لیستی هەموو رۆڵەکان"),
        ("!membercount",                      "Total member count | کۆی ژمارەی ئەندامان"),
        ("!humancount",                       "Human member count | ژمارەی مرۆڤان"),
        ("!botcount",                         "Bot count | ژمارەی بۆتەکان"),
        ("!channelcount",                     "Channel count | ژمارەی چانێلەکان"),
        ("!rolecount",                        "Role count | ژمارەی رۆڵەکان"),
        ("!boostcount",                       "Server boost count | ژمارەی بووستەکان"),
        ("!owner",                            "Server owner info | زانیاری خاوەنی سێرڤەر"),
        ("!servericon",                       "Server icon | ئایقۆنی سێرڤەر"),
        ("!serverbanner",                     "Server banner | بانەری سێرڤەر"),
        ("!myid",                             "Your Discord ID | ئای‌ددی تۆ"),
        ("!serverid",                         "Server ID | ئای‌ددی سێرڤەر"),
        ("!channelid",                        "Channel ID | ئای‌ددی چانێل"),
        ("!snipe",                            "Last deleted message | کۆتا پەیامی سڕاوەتەوە"),
        ("!editsnipe",                        "Last edited message | کۆتا پەیامی گۆڕدراو"),
        ("!github <query>",                   "Search GitHub | گەڕان لە GitHub"),
        ("!google <query>",                   "Google search link | لینکی گووگڵ"),
        ("!suggest <text>",                   "Send a suggestion | پێشنیار بنێرە"),
        ("!invites [@member]",                "Check invite count | ژمارەی بانگهێشتکردن"),
        ("!invitetop",                        "Top inviters leaderboard | باڵاترین بانگهێشتکەرەکان"),
        ("!accountage [@member]",             "Account age in days | تەمەنی ئەکاونت"),
        ("!joinposition [@member]",           "Join position in server | جێگای پەیوەستبوون"),
        ("!perms [@member]",                  "Show member permissions | مووچەکانی ئەندام"),
        ("!myroles",                          "Your own roles | رۆڵەکانت"),
        ("!userbanner [@member]",             "Member banner | بانەری ئەندام"),
        ("!oldestmember",                     "First member to join | کۆنترین ئەندام"),
        ("!newestmember",                     "Most recent member | نوێترین ئەندام"),
    ]),
    ("⭐ Leveling | ئاست", [
        ("!rank [@member]",                   "View XP rank | ئاست و XP ببینە"),
        ("!top / !lb",                        "XP leaderboard | تابلۆی پێشەنگان"),
        ("!toplevel",                         "Level leaderboard | تابلۆی ئاستەکان"),
        ("!luckylb",                          "Lucky game leaderboard | تابلۆی یاری بەخت"),
    ]),
    ("🔨 Moderation | کونترۆڵ", [
        ("!clear <n>",                        "Delete N messages | N پەیام بسڕەوە"),
        ("!kick @member [reason]",            "Kick a member | ئەندامێک دەربکە"),
        ("!ban @member [reason]",             "Ban a member | ئەندامێک بانبکە"),
        ("!unban <user_id>",                  "Unban a user | بانی بکرێتەوە"),
        ("!mute @member",                     "Mute member | بێدەنگ بکە"),
        ("!unmute @member",                   "Unmute member | بێدەنگی بکرێتەوە"),
        ("!warn @member [reason]",            "Warn a member | ئاگادار بکە"),
        ("!warnings @member",                 "View warnings | ئاگاداریەکان ببینە"),
        ("!clearwarns @member",               "Clear warnings | ئاگاداریەکان بسڕەوە"),
        ("!timeout @member <minutes>",        "Timeout a member | تایم‌ئاوت بکە"),
        ("!nickname @member <name>",          "Change nickname | پشکنامە بگۆڕە"),
        ("!addrole @member @role",            "Add role to member | رۆڵ زیاد بکە"),
        ("!removerole @member @role",         "Remove role from member | رۆڵ لابدە"),
        ("!giverole @member @role",           "Give a role (admin) | رۆڵ ببەخشە"),
        ("!takerole @member @role",           "Take a role (admin) | رۆڵ وەربگرە"),
        ("!promote @member",                  "Promote member one rank | ئەندام بەرز بکەوە"),
        ("!demote @member",                   "Demote member one rank | ئەندام دابەزێنە"),
        ("!lock [#channel]",                  "Lock channel | چانێل قفڵ بکە"),
        ("!unlock [#channel]",                "Unlock channel | قفڵی بکرێتەوە"),
        ("!slowmode <seconds>",               "Set slowmode | کاربەستی هێواش دیاری بکە"),
        ("!nuke",                             "Nuke channel | چانێل نووک بکە"),
        ("!hidechannel",                      "Hide channel | چانێل بشارەوە"),
        ("!showchannel",                      "Show channel | چانێل ئاشکرا بکە"),
        ("!vcmute @member",                   "VC mute member | بێدەنگی VC"),
        ("!vcunmute @member",                 "VC unmute member | بێدەنگی VC بکرێتەوە"),
        ("!vcdisconnect @member",             "Disconnect from VC | لە VC دەرببە"),
        ("!anti_link",                        "Toggle anti-link filter | فیلتەری لینک چالاک/ناچالاک"),
    ]),
    ("💤 AFK", [
        ("!afk [reason]",                     "Set AFK status | دۆخی AFK دیاری بکە"),
    ]),
    ("🎁 Giveaway | گیڤەوەی", [
        ("!gcreate",                          "Start a giveaway (form) | فۆرمی بەخشین"),
        ("!greroll",                          "Reroll giveaway winner | دووبارە هەڵبژاردن"),
        ("!gend <message_id>",                "End a giveaway early | گیڤەوەی زوو کۆتایی بهێنە"),
        ("!glist",                            "List active giveaways | لیستی گیڤەوەی چالاک"),
    ]),
    ("🎵 Music | مۆسیقا", [
        ("!play <url/name>",                  "Play a song | ئاهەنگ لێبدەوە"),
        ("!pause",                            "Pause playback | وەستان"),
        ("!resume",                           "Resume playback | بەردەوام بکە"),
        ("!stop",                             "Stop and clear queue | وەستاندن و پاکردنەوەی ڕیز"),
        ("!skip",                             "Skip current track | ئاهەنگی ئێستا هەڵبژێرەوە"),
        ("!np / !nowplaying",                 "Now playing info | ئاهەنگی ئێستا"),
        ("!queue",                            "Show queue | ڕیزی ئاهەنگ ببینە"),
        ("!join",                             "Join your voice channel | بەشداریی کەناڵی دەنگ"),
        ("!leave",                            "Leave voice channel | کەناڵی دەنگ جێبهێشتە"),
        ("!shuffle",                          "Shuffle queue | ڕیز بە ئەتفال"),
        ("!seek <seconds>",                   "Seek to position | بچۆ بۆ کاتی دیاریکراو"),
        ("!restart",                          "Restart current track | ئاهەنگی ئێستا دووبارە کەیتەوە"),
        ("!volume <1-200>",                   "Set volume | دەنگ دیاری بکە"),
        ("!loop [track|queue|off]",           "Toggle loop mode | گەردوون چالاک/ناچالاک"),
        ("!qremove <n>",                      "Remove track from queue | ئاهەنگ لە ڕیزەوە بسڕەوە"),
    ]),
    ("💰 Reklam | ڕیکلام", [
        ("!reklam",                           "Request a reklam slot | داواکاریی بڵاوکردنەوەی ڕیکلام"),
    ]),
    ("👥 Staff Tools | ئامرازەکانی ستاف", [
        ("!staffdone",                        "Log completed task | تۆمارکردنی کاری تەواوبوو"),
        ("!staffdonelog [today|week|all]",    "View staff done log | تۆمارەکانی کاری ستاف"),
        ("!dailyactive",                      "Daily activity tracker | شوێنکەوتنی چالاکیی ڕۆژانە"),
        ("!staffweekly",                      "Weekly activity tracker | شوێنکەوتنی چالاکیی هەفتانە"),
        ("!staff daily",                      "Send daily staff message | پەیامی ڕۆژانەی ستاف"),
        ("!staff setchannel #channel",        "Set auto-daily staff channel | چانێلی ستافی ئۆتۆ"),
        ("!staff removechannel",              "Remove auto-daily channel | چانێلی ئۆتۆ لابدە"),
    ]),
    ("🎮 Games & Fun | یاری و کێف", [
        ("!spy",                              "Spy Game lobby | لۆبی یاری سیخوڕ"),
        ("!spyvote",                          "Early vote in Spy Game | دەنگدانی زوو"),
        ("!spystop",                          "End Spy Game | یاری سیخوڕ کۆتایی بهێنە"),
        ("!spyleave",                         "Leave Spy lobby | لۆبی جێبهێشتە"),
        ("!spystatus",                        "Spy Game status | دۆخی یاری سیخوڕ"),
        ("!guess",                            "Number guessing game | یاری حەزرکردنی ژمارە"),
        ("!stopgame",                         "Stop current game | یاری ئێستا بوەستێنە"),
        ("!lucky",                            "Lucky number game | یاری ژمارەی بەخت"),
        ("!luckylb",                          "Lucky game leaderboard | تابلۆی یاری بەخت"),
        ("!bomb",                             "Bomb defuse mini-game | یاری بێتەقینەوەی بۆم"),
        ("!rps <rock|paper|scissors>",        "Rock Paper Scissors | بەرد کاغەز مەقەس"),
        ("!rpsls <choice>",                   "Rock Paper Scissors Lizard Spock"),
        ("!tf",                               "True or False quiz | ڕاست یان هەڵە"),
        ("!animequiz",                        "Anime character quiz | تاقیکردنەوەی ئانیمە"),
        ("!race",                             "Animal racing game | یاری مشەمەی ئاژەڵ"),
        ("!shadow",                           "Among the Shadows — mafia game | یاری مافیا"),
        ("!shadowstop",                       "End Shadow game | یاری سێبەر کۆتایی بهێنە"),
        ("!roulette <amount>",                "Russian roulette bet | گەردوونی رووسی"),
        ("!td <amount>",                      "Tower defense mini-game | یاری پاراستنی بورج"),
        ("!hangman",                          "Hangman word game | یاری مرۆڤی دارووخراو"),
        ("!poll <question>",                  "Quick yes/no poll | دەنگدانی خێرا"),
        ("!trivia [easy|medium|hard]",        "Trivia battle game — یاری تریۚیا | یاری پرسیار دانی"),
        ("!triviastop",                        "Stop trivia game | یاری تریۚیا بوەستێنە"),
        ("!triviascore [@member]",             "Your trivia score | خاڵەکەی تریۚیای تۆ"),
        ("!trivialeaderboard",                 "Trivia leaderboard | تابڵۆی تریۚیا"),
    ]),
    ("🔗 Link Setup | دامەزراندنی لینک", [
        ("!setuplink",                           "Interactive link setup panel | پانێلی دامەزراندنی لینک"),
        ("!link",                                "Show server join link or channel | نیشاندانی لینکی گەیشتن"),
    ]),
    ("🎭 Auto-Role | رۆڵی ئۆتۆماتیک", [
        ("!setautorole @role",                   "Auto-give role to new members | رۆڵ بە ئەندامە نوێیەکان بدە"),
        ("!removeautorole",                      "Remove auto-role | ئۆتۆرۆڵ لابدە"),
        ("!checkautorole",                       "Check current auto-role | ئۆتۆرۆڵی ئێستا ببینە"),
    ]),
    ("🔧 Welcome Embed Setup | دامەزراندنی بەخێرھاتن", [
        ("!welcomeembedsetup",                   "Interactive welcome embed editor | دەستکاریکردنی ئێستا"),
        ("!testwelcome",                         "Preview welcome embed | تاقیکردنەوەی ئمبید"),
        ("!setwelcomeembed #channel",            "Set welcome channel | چانێلی بەخێرھاتن دیاری بکە"),
        ("!setboostembed #channel",              "Set boost channel | چانێلی بووست"),
        ("!setinviteembed #channel",             "Set invite-join channel | چانێلی بانگھێشت"),
    ]),
    ("🌐 Language | زمان", [
        ("!languageallbot <en|ku|both>",          "Set bot display language for this server | زمانی بۆت بگۆۜە"),
        ("!language <en|ku>",                    "Your personal language preference | زمانی تایبەت"),
    ]),
]

GAME_CATEGORIES_KEYS = {"🎮 Games & Fun | یاری و کێف"}

PANEL_CATEGORIES = [
    ("🎫 Ticket System | سیستەمی تیکیت", [
        ("!setpanel #channel",                   "Post ticket panel in channel — NEEDS: #channel | دانانی پانێلی تیکیت — پێویست: #channel"),
        ("!setstaffrole @role",                  "Set which role can see tickets — NEEDS: @role | رۆڵی ستاف دیاری بکە — پێویست: @role"),
        ("!setticketcategory <name>",            "Category name for ticket channels — NEEDS: category name | ناوی کاتەگۆری — پێویست: ناو"),
        ("!setticketlog #channel",               "Log closed tickets here — NEEDS: #channel | لۆگی داخستنی تیکیت — پێویست: #channel"),
        ("!ticketstatus",                        "Show current ticket config | دۆخی دامەزراندنی تیکیت"),
        ("!staffsubmitlog #channel",             "Staff application log channel — NEEDS: #channel | چانێلی لۆگی داواکاری ستاف — پێویست: #channel"),
    ]),

    ("📜 Rules System | سیستەمی قانوون", [
        ("!rule [#channel]",                     "Post bilingual rules panel with Edit Text & Language buttons | پانێلی قانوون — دوگمەی دەستکاری و زمان"),
        ("!rules [#channel]",                    "Alias for !rule | هاوتای !rule"),
    ]),

    ("🏷️ Tag System | سیستەمی تاگ", [
        ("!settag [name]",                       "Create/edit a tag via modal form | دروستکردن/دەستکاریکردنی تاگ"),
        ("!tag <name>",                          "Show a saved tag response | پیشاندانی وەڵامی تاگ"),
        ("tag <name>",                           "No-prefix shortcut — no ! needed | بەبێ ! — وەکو !tag"),
        ("!taglist",                             "List all tags for this server | لیستی هەموو تاگەکان"),
        ("!deltag <name>",                       "Delete a tag | سڕینەوەی تاگ — پێویست: ناو"),
    ]),
    ("👋 Welcome & Boost | بەخێرهاتن و بووست", [
        ("!setwelcomeembed #channel",            "Welcome new members here — NEEDS: #channel | پێشوازی ئەندامی نوێ — پێویست: #channel"),
        ("!removewelcomeembed",                  "Remove welcome channel | چانێلی بەخێرهاتن لابدە"),
        ("!testwelcome",                         "Preview welcome embed in configured channel | تاقیکردنەوەی ئمبیدی بەخێرهاتن"),
        ("!setboostembed #channel",              "Boost announcement channel — NEEDS: #channel | چانێلی بووست — پێویست: #channel"),
        ("!testboost",                           "Preview boost embed in configured channel | تاقیکردنەوەی ئمبیدی بووست"),
        ("!setinviteembed #channel",             "Invite-join announcement channel — NEEDS: #channel | چانێلی بانگهێشت — پێویست: #channel"),
        ("!removeinviteembed",                   "Remove invite channel | چانێلی بانگهێشت لابدە"),
        ("!testinvite",                          "Preview invite embed in configured channel | تاقیکردنەوەی ئمبیدی بانگهێشت"),
    ]),
    ("⭐ Leveling Setup | دامەزراندنی ئاست", [
        ("!setlevelchannel #channel",            "Level-up messages go here — NEEDS: #channel | پەیامی ئاستبالابوون — پێویست: #channel"),
        ("!removelevelchannel",                  "Remove level-up channel | چانێلی ئاستبالابوون لابدە"),
        ("!setlevelup #channel [message]",       "Set level-up channel + custom message — NEEDS: #channel | چانێل و پەیامی تایبەت — پێویست: #channel"),
        ("!startlevelup",                        "Preview level-up announcement | دێمۆی ئاگاداری ئاستبالابوون"),
    ]),
    ("🎭 Reaction Roles | رۆڵی ئەکتیڤ", [
        ("!reactionrole [#ch] Title | @r | @r",  "Create button-role panel — NEEDS: title + @roles | پانێلی دوگمەی رۆڵ — پێویست: ناو + @رۆڵەکان"),
        ("!setupreaction [#channel] [title]",    "Interactive role setup picker — NEEDS: nothing (guided) | دامەزراندنی ئینتەراکتیڤ — پێویست: هیچ"),
        ("!reactionselect [#channel] [title]",   "Dropdown role select panel — NEEDS: nothing (guided) | مێنیوی هەڵبژاردنی رۆڵ"),
        ("!setselfrole [#ch] Title | 🎮 @role",  "Emoji reaction roles — NEEDS: emoji + @role pairs | رۆڵی ئیمۆجی — پێویست: ئیمۆجی + @رۆڵ"),
        ("!reactionroles",                       "List all reaction role panels | لیستی پانێلەکانی رۆڵ"),
        ("!removeselfrole <message_id>",         "Delete a self-role panel — NEEDS: message ID | پانێلی رۆڵی ئیمۆجی بسڕەوە"),
    ]),
    ("📋 Logs & Apply | لۆگ و داواکاری", [
        ("!setlog #channel",                     "Server event log channel — NEEDS: #channel | چانێلی لۆگی سێرڤەر — پێویست: #channel"),
        ("!removelog",                           "Remove log channel | چانێلی لۆگ لابدە"),
        ("!logs",                                "Show log system status | دۆخی سیستەمی لۆگ"),
        ("!setapplychannel #channel",            "Staff application channel — NEEDS: #channel | چانێلی داواکاری — پێویست: #channel"),
        ("!removeapplychannel",                  "Remove apply channel | چانێلی داواکاری لابدە"),
    ]),
    ("📢 Reklam Setup | دامەزراندنی ڕیکلام", [
        ("!setreklam",                           "Configure reklam system (guided) — NEEDS: nothing (interactive) | دامەزراندنی ڕیکلام — پێویست: هیچ (ئینتەراکتیڤ)"),
    ]),
    ("👥 Staff Management | بەڕێوەبردنی ستاف", [
        ("!promote @member",                     "Promote member one rank — NEEDS: @member | ئەندام بەرز بکەوە — پێویست: @ئەندام"),
        ("!demote @member",                      "Demote member one rank — NEEDS: @member | ئەندام دابەزێنە — پێویست: @ئەندام"),
        ("!giverole @member @role",              "Give role to member — NEEDS: @member @role | رۆڵ ببەخشە — پێویست: @ئەندام @رۆڵ"),
        ("!takerole @member @role",              "Remove role from member — NEEDS: @member @role | رۆڵ وەربگرە — پێویست: @ئەندام @رۆڵ"),
        ("!stafflist",                           "Show all staff members | لیستی هەموو ستافەکان"),
        ("!setdonelog #channel",                 "Staff done-log channel — NEEDS: #channel | چانێلی تۆمارکردنی کار — پێویست: #channel"),
        ("!anti_link",                           "Toggle anti-link filter (Manage Server) | فیلتەری لینک"),
        ("!setupstaffdaily",                     "Pick roles pinged by auto staff daily (interactive) | رۆڵی پینگی دەیلی ستاف دیاری بکە"),
        ("!staff daily",                         "Show staff daily config / send test ping | دۆخی دەیلی ستاف و تاقیکردنەوە"),
        ("!staff setchannel #channel",           "Auto-daily staff channel — NEEDS: #channel | چانێلی ئۆتۆی ستاف — پێویست: #channel"),
        ("!staff removechannel",                 "Remove auto-daily staff channel | چانێلی ئۆتۆ لابدە"),
    ]),
]

def _build_help_embed(title: str, subtitle: str, categories: list, footer: str = "", lang: str = "both") -> discord.Embed:
    """Build ONE single embed with all categories — no multi-page splitting.
    Shows full usage + English description for every command."""
    e = discord.Embed(title=title, description=subtitle, color=0x5865f2)
    for cat_name, items in categories:
        cat_display = _strip_lang(cat_name, lang)
        lines_full = []
        for usage, desc in items:
            eng_desc = desc.split("|")[0].strip()
            lines_full.append(f"`{usage}` — {eng_desc}")
        value = "\n".join(lines_full)
        if len(value) > 1024:
            # fallback: compact — cmd + short desc, 1 per line
            lines_short = []
            for usage, desc in items:
                cmd_part = usage.split()[0]
                eng_desc = desc.split("|")[0].strip()
                lines_short.append(f"`{cmd_part}` — {eng_desc}")
            value = "\n".join(lines_short)
            if len(value) > 1024:
                # last resort: names only
                names = [f"`{u.split()[0]}`" for u, _ in items]
                rows  = [" · ".join(names[i:i+4]) for i in range(0, len(names), 4)]
                value = "\n".join(rows)
                if len(value) > 1024:
                    value = value[:1020] + "…"
        e.add_field(name=cat_display, value=value, inline=False)
    if footer:
        e.set_footer(text=footer)
    return e


@bot.command(name="help")
async def help_cmd(ctx, *, command_name: str = None):
    """!help — show all commands in one message. $help <cmd> for details."""
    _lang = guild_langs.get(str(ctx.guild.id) if ctx.guild else "0", "both")
    # ── detail view ──────────────────────────────────────────────────────────
    if command_name:
        cmd = bot.get_command(command_name.lstrip("!").lower())
        if cmd is None:
            return await ctx.send(
                f"هیچ فەرمانێک بە ناوی `{command_name}` نەدۆزرایەوە. | "
                f"No command `{command_name}` found. Try `!help`."
            )
        all_cats = HELP_CATEGORIES + PANEL_CATEGORIES
        for category, items in all_cats:
            for usage, desc in items:
                tokens = [t.lstrip("!").lower() for t in usage.split() if t.startswith("!")]
                if cmd.name.lower() in tokens or any(a.lower() in tokens for a in cmd.aliases):
                    e = discord.Embed(
                        title=f"`${cmd.name}`",
                        description=f"**بەکارهێنان | Usage:** `{usage}`\n\n{desc}",
                        color=0x5865f2,
                    )
                    e.set_footer(text=f"پۆل | Category: {category}")
                    return await ctx.send(embed=e)
        e = discord.Embed(title=f"`${cmd.name}`", description="هیچ زانیارییەک نییە | No help entry found.", color=0x5865f2)
        return await ctx.send(embed=e)

    # ── main help — all non-game non-panel categories in ONE embed ────────────
    non_game = [(c, i) for c, i in HELP_CATEGORIES if c not in GAME_CATEGORIES_KEYS]
    subtitle = (
        "**پێشگر | Prefix:** `$`   ·   `!help <فەرمان>` بۆ وردەکاری | for details\n"
        "🎮 `!helpgame` — یاریەکان | Games   ·   ⚙️ `!helppanel` — دامەزراندن | Setup"
    )
    embed = _build_help_embed(
        title=f"📖 {bot.user.name} — فەرمانەکان | Commands",
        subtitle=subtitle,
        categories=non_game,
        lang=_lang,
        footer="!helpgame  ·  $helppanel  ·  $help <cmd>",
    )
    await ctx.send(embed=embed)


@bot.command(name="helpgame", aliases=["hgame", "gamehelp", "ghelp"])
async def helpgame_cmd(ctx):
    """!helpgame — all game commands in one message."""
    _lang = guild_langs.get(str(ctx.guild.id) if ctx.guild else "0", "both")
    game_cats = [(c, i) for c, i in HELP_CATEGORIES if c in GAME_CATEGORIES_KEYS]
    if not game_cats:
        return await ctx.send("هیچ پۆلێکی یاری نەدۆزرایەوە. | No game categories found.")
    embed = _build_help_embed(
        title="🎮 یاری و کێف — Game & Fun Commands | فەرمانەکانی یاری",
        subtitle="**پێشگر | Prefix:** `$`   ·   هەموو فەرمانەکانی یاری لە خوارەوە | All game commands below\n📖 `!help` فەرمانەکانی تر | Other commands",
        categories=game_cats,
        lang=_lang,
        footer="!help  ·  $helppanel",
    )
    await ctx.send(embed=embed)


@bot.command(name="helppanel", aliases=["panelhelp", "setuphelp"])
async def helppanel_cmd(ctx):
    """!helppanel — all panel/setup commands in one message."""
    _lang = guild_langs.get(str(ctx.guild.id) if ctx.guild else "0", "both")
    embed = _build_help_embed(
        title="⚙️ پانێل و دامەزراندن — Panel & Setup Commands | فەرمانەکان",
        subtitle=(
            "**پێشگر | Prefix:** `$`   ·   فەرمانەکانی ئەدمین و دامەزراندن لە خوارەوە | Admin/setup commands below\n"
            "📖 `!help` فەرمانەکانی تر | Other commands   ·   🎮 `!helpgame` یاریەکان | Games"
        ),
        categories=PANEL_CATEGORIES,
        lang=_lang,
        footer="!help  ·  $helpgame  ·  $helppanel",
    )
    await ctx.send(embed=embed)


@bot.command(name="setlevelup", aliases=["levelupchannel", "setlvlup"])
@commands.has_permissions(administrator=True)
async def setlevelup_cmd(ctx, channel: discord.TextChannel = None, *, message: str = None):
    """Set the channel (and optionally a custom message) for level-up notifications."""
    if channel is None:
        e = discord.Embed(
            title="⚙️ $setlevelup — Usage | بەکارهێنان",
            description=(
                "**بەکارهێنان | Usage:** `!setlevelup #channel [custom message]`\n\n"
                "**نموونە | Examples:**\n"
                "`!setlevelup #general`\n"
                "`!setlevelup #levels GG {user} — you hit level {level}! 🎉`\n\n"
                "**Tags | تاگەکان:**\n"
                "`{user}` — mention  •  `{level}` — new level  •  `{xp}` — total XP"
            ),
            color=discord.Color.blurple(),
        )
        return await ctx.send(embed=e)

    gid = str(ctx.guild.id)
    level_channels[gid] = channel.id
    save_level_channels()

    custom = message or "{user} بالا چوو بۆ ئاستی **{level}** 🎉 | leveled up to **{level}**! 🎉"
    # store custom message in bot's memory (use a simple dict)
    if not hasattr(bot, "_levelup_messages"):
        bot._levelup_messages = {}
    bot._levelup_messages[gid] = custom

    e = discord.Embed(
        title="✅ چانێلی ئاستبالابوون دیاری کرا | Level-up Channel Set",
        description=(
            f"📢 چانێل | Channel: {channel.mention}\n"
            f"💬 پەیام | Message: `{custom}`\n\n"
            "دوای ئەوەی کەسێک ئاستیان بالا بچێت، ئاگادارکردنەوەکە دەنێردرێت! | "
            "A notification will be sent whenever someone levels up!"
        ),
        color=0x57f287,
    )
    e.set_footer(text="!startlevelup بنووسە بۆ دێمۆ | Type $startlevelup for a demo")
    await ctx.send(embed=e)


@setlevelup_cmd.error
async def setlevelup_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("پێویستت بە مووچەی ئەدمینایتی هەیە. | You need Administrator permission.")
    elif isinstance(error, commands.ChannelNotFound):
        await ctx.send("چانێلەکە نەدۆزرایەوە. | Channel not found. Usage: `!setlevelup #channel`")


@bot.command(name="startlevelup", aliases=["demoLevelup", "testlevelup"])
@commands.has_permissions(administrator=True)
async def startlevelup_cmd(ctx):
    """Send a demo level-up announcement to the configured level-up channel."""
    gid = str(ctx.guild.id)
    cid = level_channels.get(gid)
    target = ctx.guild.get_channel(cid) if cid else ctx.channel
    if target is None:
        target = ctx.channel

    custom_msg = None
    if hasattr(bot, "_levelup_messages"):
        custom_msg = bot._levelup_messages.get(gid)

    demo_level = 0
    demo_xp    = 0

    level_enabled[gid] = True

    if custom_msg:
        text = (custom_msg
                .replace("{user}", ctx.author.mention)
                .replace("{level}", str(demo_level))
                .replace("{xp}", str(demo_xp)))
    else:
        text = f"🚀 سیستەمی ئاست چالاک کرا! | Leveling system is now **active**!\n\n{ctx.author.mention} سیستەمی ئاست دەستی پێکرد بۆ **{ctx.guild.name}** | started the leveling system for **{ctx.guild.name}**!"

    e = discord.Embed(
        title="⭐ سیستەمی ئاست دەستی پێکرد! | Leveling System Started!",
        description=text,
        color=0xfee75c,
    )
    e.add_field(name="⭐ ئاستی دەستپێکردن | Starting Level", value=f"**{demo_level}**", inline=True)
    e.add_field(name="📊 کۆی XP | Total XP",                value=f"**{demo_xp}**",    inline=True)
    e.add_field(name="💬 چۆن XP بەدەست بهێنیت | How to earn XP",
                value="پەیام بنێرە `15–25 XP` · دەنگ چالاک بە `10 XP/min`\nSend messages `15–25 XP` · Be active in voice `10 XP/min`",
                inline=False)
    e.set_thumbnail(url=ctx.guild.icon.url if ctx.guild.icon else ctx.author.display_avatar.url)
    e.set_footer(text=f"Started by {ctx.author.display_name} · $rank بنووسە بۆ بینینی ئاستت | Type $rank to see your level")

    await target.send(embed=e)
    if target != ctx.channel:
        confirm = discord.Embed(
            title="✅ سیستەمی ئاست چالاک کرا | Leveling System Active",
            description=f"ئاگادارییەکە نێردرا بۆ {target.mention} | Announcement sent to {target.mention}",
            color=0x57f287,
        )
        await ctx.send(embed=confirm)


@startlevelup_cmd.error
async def startlevelup_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("پێویستت بە مووچەی ئەدمینایتی هەیە. | You need Administrator permission.")


@bot.command()
@commands.has_role(secret_role)
async def secret(ctx):
    await ctx.send("Welcome to the club! | بەخێربووت بۆ کلوبەکە!")

@secret.error
async def secret_error(ctx, error):
    if isinstance(error, commands.MissingRole):
        await ctx.send("You do not have permission to do that! | مووچەت نییە ئەوە بکەیت!")

# 🌍 LANGUAGE COMMAND
@bot.command()
async def language(ctx, lang=None):
    if lang not in ["en", "ku"]:
        await ctx.send("Choose: `en` or `ku` | هەڵبژێرە: `en` یان `ku`")
        return

    user_langs[ctx.author.id] = lang

    if lang == "ku":
        await ctx.send("🇹🇯 زمانی بۆتەکە گۆڕدرا بۆ کوردی | Bot language changed to Kurdish")
    else:
        await ctx.send("🇺🇸 Bot language changed to English | زمانی بۆتەکە گۆڕدرا بۆ ئینگلیزی")

# 🌍 SERVER-WIDE LANGUAGE COMMAND
@bot.command(name="languageallbot", aliases=["botlanguage", "serverlang", "setbotlang", "langbot"])
@commands.has_permissions(administrator=True)
async def languageallbot_cmd(ctx, lang: str = None):
    """!languageallbot <en|ku|both> — change the bot's display language for this server."""
    if lang not in ("en", "ku", "both"):
        e = discord.Embed(
            color=0x5865F2,
            title="🌍 زمانی بۆت | Bot Language",
            description=(
                "**🇬🇧 English only:** `!languageallbot en`\n"
                "**🏳️ کوردی تەنھا:** `!languageallbot ku`\n"
                "**🌐 دووزمانە | Bilingual:** `!languageallbot both`\n\n"
                f"ئێستا | Current: **`{guild_langs.get(str(ctx.guild.id), 'both')}`**"
            ),
        )
        return await ctx.send(embed=e)
    guild_langs[str(ctx.guild.id)] = lang
    with get_db() as _conn:
        _conn.execute(
            "INSERT INTO guild_lang_settings (guild_id, lang) VALUES (?,?) "
            "ON CONFLICT(guild_id) DO UPDATE SET lang=excluded.lang",
            (ctx.guild.id, lang)
        )
        _conn.commit()
    _names = {"en": "English 🇬🇧", "ku": "کوردی 🏳️", "both": "Bilingual 🌐"}
    e = discord.Embed(
        color=0x57F287,
        title="✅ زمانی بۆت گۆۜدرا | Bot Language Changed",
        description=f"زمانی بۆت گۆۜدرا بۆ **{_names[lang]}** | Bot language changed to **{_names[lang]}**"
    )
    e.set_footer(text=ctx.guild.name)
    await ctx.send(embed=e)

@languageallbot_cmd.error
async def languageallbot_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ مووچەی ئەدمین پەویستە. | You need Administrator permission.")


# ─────────────────────────────────────────────────────────────────────────────
# ─────────────────────────────────────────────────────────────────────────────
# --- TICKET SYSTEM ---
# ─────────────────────────────────────────────────────────────────────────────

def _guild_icon_url(guild: discord.Guild):
    if guild and guild.icon:
        return guild.icon.url
    return None


# ── Ticket panel embed builders ───────────────────────────────────────────────

def build_ticket_panel_embed(guild_name: str, icon_url: str = None) -> discord.Embed:
    embed = discord.Embed(
        color=0xFFD700,
        title=f"🎫 {guild_name} — پشتگیری | Support",
        description=(
            "🇬🇧 **Need help? Create a ticket!**\n"
            "🇮🇶 **بێنویست بە یارمەتیە؟ تیکەتێک دروست بکە!**\n\n"
            "──────────────────────\n\n"
            "🇬🇧 Click the button below to open a support ticket.\n"
            "Our team will respond as soon as possible.\n\n"
            "**What we can help with:**\n"
            "• General support and questions\n"
            "• Product purchases and pricing\n"
            "• Technical issues and bugs\n"
            "• Report rule violations\n\n"
            "──────────────────────\n\n"
            "🇮🇶 کرتە بکەرە لەسەر دوگمەکە بۆ کردنەوەی تیکەتی پشتگیری.\n"
            "تیمەکەمان زووترین کات وەڵامت دەداتەوە.\n\n"
            "**چۆن یارمەتیت دەدەین:**\n"
            "• پشتگیری گشتی و پرسیارەکان\n"
            "• کریێنی بەرهەم و نرخەکان\n"
            "• کێشەی تەکنیکی و هەڵەکان\n"
            "• ڕاپۆرتکردنی پێشێلکاری یاساکان\n\n"
            "──────────────────────\n"
            f"*{guild_name} | پشتگیری بیشەی 24/7*"
        ),
        timestamp=datetime.datetime.utcnow(),
    )
    embed.set_footer(text=f"{guild_name} Support System")
    if icon_url:
        embed.set_image(url=icon_url)
    return embed


def build_ticket_panel_embed_en(guild_name: str, icon_url: str = None) -> discord.Embed:
    embed = discord.Embed(
        color=0xFFD700,
        title=f"🎫 {guild_name} — Support",
        description=(
            "🇬🇧 **Need help? Create a ticket!**\n\n"
            "──────────────────────\n\n"
            "Click the button below to open a support ticket.\n"
            "Our team will respond as soon as possible.\n\n"
            "**What we can help with:**\n"
            "• General support and questions\n"
            "• Product purchases and pricing\n"
            "• Technical issues and bugs\n"
            "• Report rule violations\n\n"
            "──────────────────────\n"
            f"*{guild_name} | 24/7 Support*"
        ),
        timestamp=datetime.datetime.utcnow(),
    )
    embed.set_footer(text=f"{guild_name} Support System")
    if icon_url:
        embed.set_image(url=icon_url)
    return embed


def build_ticket_panel_embed_ku(guild_name: str, icon_url: str = None) -> discord.Embed:
    embed = discord.Embed(
        color=0xFFD700,
        title=f"🎫 {guild_name} — پشتگیری",
        description=(
            "🇮🇶 **بێنویست بە یارمەتیە؟ تیکەتێک دروست بکە!**\n\n"
            "──────────────────────\n\n"
            "کرتە بکەرە لەسەر دوگمەکە بۆ کردنەوەی تیکەتی پشتگیری.\n"
            "تیمەکەمان زووترین کات وەڵامت دەداتەوە.\n\n"
            "**چۆن یارمەتیت دەدەین:**\n"
            "• پشتگیری گشتی و پرسیارەکان\n"
            "• کریێنی بەرهەم و نرخەکان\n"
            "• کێشەی تەکنیکی و هەڵەکان\n"
            "• ڕاپۆرتکردنی پێشێلکاری یاساکان\n\n"
            "──────────────────────\n"
            f"*{guild_name} | پشتگیری بیشەی 24/7*"
        ),
        timestamp=datetime.datetime.utcnow(),
    )
    embed.set_footer(text=f"{guild_name} Support System")
    if icon_url:
        embed.set_image(url=icon_url)
    return embed


# ── Staff application channel embed builders ──────────────────────────────────

def build_staff_app_embed(guild_name: str, user_avatar: str = None, icon_url: str = None) -> discord.Embed:
    embed = discord.Embed(
        color=0x5865F2,
        title=f"📋 {guild_name} — داواکاریی ستاف | Staff Application",
        description=(
            "🇬🇧 **Welcome to your staff application channel!**\n"
            "🇮🇶 **بەخێربێیت بۆ کەناڵی داواکاریی ستافت!**\n\n"
            "──────────────────────\n\n"
            "🇬🇧 Click **Fill Application** below to open the form.\n"
            "A staff member will review your application soon.\n\n"
            "**The form asks about:** name, age, experience, active hours, why join.\n\n"
            "──────────────────────\n\n"
            "🇮🇶 کرتە بکە لەسەر **پڕکردنەوەی داواکاری** بۆ کردنەوەی فۆرمەکە.\n"
            "ئەندامێکی تیم داواکارییەکەت دەخوێنێتەوە بە زووترین کات.\n\n"
            "**فۆرمەکە دەپرسێت:** ناو، تەمەن، ئەزموون، کاتژمێری چالاکی، بۆچی.\n\n"
            "──────────────────────\n"
            f"*{guild_name} | Staff Applications*"
        ),
        timestamp=datetime.datetime.utcnow(),
    )
    if user_avatar:
        embed.set_thumbnail(url=user_avatar)
    if icon_url:
        embed.set_image(url=icon_url)
    embed.set_footer(text=f"{guild_name} Staff Team")
    return embed


def build_staff_app_embed_en(guild_name: str, user_avatar: str = None, icon_url: str = None) -> discord.Embed:
    embed = discord.Embed(
        color=0x5865F2,
        title=f"📋 {guild_name} — Staff Application",
        description=(
            "🇬🇧 **Welcome to your staff application channel!**\n\n"
            "──────────────────────\n\n"
            "Click **Fill Application** below to open the form.\n"
            "A staff member will review your application soon.\n\n"
            "**The form asks about:** name, age, experience, active hours, why join.\n\n"
            "──────────────────────\n"
            f"*{guild_name} | Staff Applications*"
        ),
        timestamp=datetime.datetime.utcnow(),
    )
    if user_avatar:
        embed.set_thumbnail(url=user_avatar)
    if icon_url:
        embed.set_image(url=icon_url)
    embed.set_footer(text=f"{guild_name} Staff Team")
    return embed


def build_staff_app_embed_ku(guild_name: str, user_avatar: str = None, icon_url: str = None) -> discord.Embed:
    embed = discord.Embed(
        color=0x5865F2,
        title=f"📋 {guild_name} — داواکاریی ستاف",
        description=(
            "🇮🇶 **بەخێربێیت بۆ کەناڵی داواکاریی ستافت!**\n\n"
            "──────────────────────\n\n"
            "کرتە بکە لەسەر **پڕکردنەوەی داواکاری** بۆ کردنەوەی فۆرمەکە.\n"
            "ئەندامێکی تیم داواکارییەکەت دەخوێنێتەوە بە زووترین کات.\n\n"
            "**فۆرمەکە دەپرسێت:** ناو، تەمەن، ئەزموون، کاتژمێری چالاکی، بۆچی.\n\n"
            "──────────────────────\n"
            f"*{guild_name} | داواکاریی ستاف*"
        ),
        timestamp=datetime.datetime.utcnow(),
    )
    if user_avatar:
        embed.set_thumbnail(url=user_avatar)
    if icon_url:
        embed.set_image(url=icon_url)
    embed.set_footer(text=f"{guild_name} Staff Team")
    return embed


# ── Rules embed builders ──────────────────────────────────────────────────────

def build_rules_embed(guild_name: str, text_en: str = "", text_ku: str = "", icon_url: str = None) -> discord.Embed:
    en_block = text_en.strip() if text_en.strip() else "_No English rules set yet. Click **Edit Text** to add them._"
    ku_block = text_ku.strip() if text_ku.strip() else "_هیچ قانوونی کوردی دانەنراوە. کرتە بکە لەسەر **دەقی بگۆڕە**._"
    embed = discord.Embed(
        color=0xED4245,
        title=f"📜 {guild_name} — قانوونەکان | Rules",
        description=(
            "🇬🇧 **English Rules:**\n" + en_block
            + "\n\n──────────────────────\n\n"
            + "🇮🇶 **قانوونەکانی کوردی:**\n" + ku_block
        ),
        timestamp=datetime.datetime.utcnow(),
    )
    embed.set_footer(text=f"{guild_name} · Click Edit Text to update rules (admins only)")
    if icon_url:
        embed.set_image(url=icon_url)
    return embed


def build_rules_embed_en(guild_name: str, text_en: str = "", icon_url: str = None) -> discord.Embed:
    en_block = text_en.strip() if text_en.strip() else "_No English rules set yet. Click **Edit Text** to add them._"
    embed = discord.Embed(
        color=0xED4245,
        title=f"📜 {guild_name} — Rules",
        description="🇬🇧 **Rules:**\n" + en_block,
        timestamp=datetime.datetime.utcnow(),
    )
    embed.set_footer(text=f"{guild_name} · Click Edit Text to update rules (admins only)")
    if icon_url:
        embed.set_image(url=icon_url)
    return embed


def build_rules_embed_ku(guild_name: str, text_ku: str = "", icon_url: str = None) -> discord.Embed:
    ku_block = text_ku.strip() if text_ku.strip() else "_هیچ قانوونی کوردی دانەنراوە. کرتە بکە لەسەر **دەقی بگۆڕە**._"
    embed = discord.Embed(
        color=0xED4245,
        title=f"📜 {guild_name} — قانوونەکان",
        description="🇮🇶 **قانوونەکان:**\n" + ku_block,
        timestamp=datetime.datetime.utcnow(),
    )
    embed.set_footer(text=f"{guild_name} · کرتە بکە لەسەر دەقی بگۆڕە بۆ نوێکردنەوەی قانوونەکان (ئەدمین)")
    if icon_url:
        embed.set_image(url=icon_url)
    return embed


# ── Universal language selector ───────────────────────────────────────────────

class LanguageSelectView(discord.ui.View):
    def __init__(
        self,
        panel_message_id: int,
        panel_channel_id: int,
        guild_name: str,
        icon_url: str = None,
        mode: str = "panel",
        user_avatar: str = None,
    ):
        super().__init__(timeout=60)
        self.panel_message_id = panel_message_id
        self.panel_channel_id = panel_channel_id
        self.guild_name       = guild_name
        self.icon_url         = icon_url
        self.mode             = mode
        self.user_avatar      = user_avatar

    async def _switch(self, interaction: discord.Interaction, lang: str):
        ch = interaction.guild.get_channel(self.panel_channel_id)
        if ch:
            try:
                msg = await ch.fetch_message(self.panel_message_id)
                if self.mode == "staff_app":
                    fns = {
                        "en":   build_staff_app_embed_en,
                        "ku":   build_staff_app_embed_ku,
                        "both": build_staff_app_embed,
                    }
                    embed = fns[lang](self.guild_name, self.user_avatar, self.icon_url)
                elif self.mode == "rules":
                    gid = str(interaction.guild.id)
                    s   = rules_settings.get(gid, {})
                    ten = s.get("text_en", "")
                    tku = s.get("text_ku", "")
                    if lang == "en":
                        embed = build_rules_embed_en(self.guild_name, ten, self.icon_url)
                    elif lang == "ku":
                        embed = build_rules_embed_ku(self.guild_name, tku, self.icon_url)
                    else:
                        embed = build_rules_embed(self.guild_name, ten, tku, self.icon_url)
                else:
                    fns = {
                        "en":   build_ticket_panel_embed_en,
                        "ku":   build_ticket_panel_embed_ku,
                        "both": build_ticket_panel_embed,
                    }
                    embed = fns[lang](self.guild_name, self.icon_url)
                await msg.edit(embed=embed)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                pass
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(view=self)

    @discord.ui.button(label="🇬🇧 English", style=discord.ButtonStyle.primary)
    async def english_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._switch(interaction, "en")

    @discord.ui.button(label="🇮🇶 کوردی | Kurdish", style=discord.ButtonStyle.success)
    async def kurdish_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._switch(interaction, "ku")

    @discord.ui.button(label="🌐 Both | دووزمانە", style=discord.ButtonStyle.secondary)
    async def both_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._switch(interaction, "both")

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True


# ── Submit Staff modal ────────────────────────────────────────────────────────

class SubmitStaffModal(discord.ui.Modal, title="📋 داواکاریی ستاف | Staff Application"):
    staff_name_age = discord.ui.TextInput(
        label="ناو و تەمەن | Name & Age",
        placeholder="e.g. Ahmed, 20 / ناو و تەمەنەکەت بنووسە",
        max_length=80,
        style=discord.TextStyle.short,
    )
    staff_experience = discord.ui.TextInput(
        label="ئەزموونی ئەدمینیت هەیە؟ | Admin experience?",
        placeholder="Describe your experience / ئەزموونەکەت شرۆڤە بکە",
        max_length=500,
        style=discord.TextStyle.paragraph,
    )
    staff_active = discord.ui.TextInput(
        label="چەند کاتژمێر ئەکتیڤ بیت? | Active hours/day?",
        placeholder="e.g. 4-6 hours / رۆژانە 4-6 کاتژمێر",
        max_length=80,
        style=discord.TextStyle.short,
    )
    staff_why = discord.ui.TextInput(
        label="بۆچی دەتەوێت ستاف بیت؟ | Why join staff?",
        placeholder="Tell us why / بۆچیەکەت بڵێ",
        max_length=500,
        style=discord.TextStyle.paragraph,
    )
    staff_server_tag = discord.ui.TextInput(
        label="تاگی سێرڤەر؟ | Server Tag?",
        placeholder="بەڵێ / نەخێر · Yes / No — explain briefly",
        max_length=200,
        style=discord.TextStyle.short,
    )

    async def on_submit(self, interaction: discord.Interaction):
        guild  = interaction.guild
        gid    = str(guild.id) if guild else None
        log_ch = None
        if gid and gid in staff_submit_log_channels:
            log_ch = guild.get_channel(staff_submit_log_channels[gid])

        embed = discord.Embed(
            color=0x5865F2,
            title="📋 داواکاریی ستافی نوێ | New Staff Application",
            timestamp=datetime.datetime.utcnow(),
        )
        embed.set_author(
            name=f"{interaction.user.display_name} ({interaction.user})",
            icon_url=interaction.user.display_avatar.url,
        )
        embed.add_field(name="1️⃣ ناو و تەمەن | Name & Age",    value=self.staff_name_age.value    or "—", inline=True)
        embed.add_field(name="2️⃣ ئەزموون | Experience",          value=self.staff_experience.value  or "—", inline=False)
        embed.add_field(name="3️⃣ کاتژمێری چالاکی | Active",      value=self.staff_active.value      or "—", inline=True)
        embed.add_field(name="4️⃣ بۆچی ستاف؟ | Why Staff?",       value=self.staff_why.value         or "—", inline=False)
        embed.add_field(name="5️⃣ تاگی سێرڤەر؟ | Server Tag?",   value=self.staff_server_tag.value  or "—", inline=False)
        if guild and guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        embed.set_footer(
            text="User ID: " + str(interaction.user.id) + " · " + (guild.name if guild else ""),
            icon_url=guild.icon.url if guild and guild.icon else None,
        )

        conf_embed = discord.Embed(
            color=0x57F287,
            title="✅ داواکارییەکەت نێردرا! | Application Submitted! 🎉",
            description=(
                "🇬🇧 Your staff application has been sent to the review team.\n"
                "Please wait — a staff member will reach out to you soon.\n\n"
                "🇮🇶 داواکارییەکەت نێردرا بۆ تیمی پێداچوونەوە.\n"
                "تکایە چاوەڕێ بکە — ئەندامێکی ستاف بەم زووانە پەیوەندیت پێدەکات."
            ),
            timestamp=datetime.datetime.utcnow(),
        )
        if guild and guild.icon:
            conf_embed.set_thumbnail(url=guild.icon.url)

        if log_ch:
            try:
                await log_ch.send(embed=embed)
                await interaction.response.send_message(embed=conf_embed, ephemeral=False)
            except (discord.Forbidden, discord.HTTPException):
                await interaction.response.send_message(
                    "❌ نەتوانرا بنێردرێت. | Could not send application. Contact an admin.",
                    ephemeral=True,
                )
        else:
            await interaction.response.send_message(
                "❌ هیچ کەناڵی لۆگی ستاف دانەنراوە. | No staff log channel set. Ask an admin to run `!staffsubmitlog #channel`.",
                ephemeral=True,
            )

    async def on_error(self, interaction: discord.Interaction, error: Exception):
        try:
            await interaction.response.send_message(
                "❌ هەڵەیەک ڕوویدا. | An error occurred. Please try again.", ephemeral=True
            )
        except Exception:
            pass


# ── Staff application channel control view ────────────────────────────────────

class StaffAppControlView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="📋 Fill Application | داواکاری پڕ بکەرەوە",
        style=discord.ButtonStyle.success,
        custom_id="staff:apply",
        row=0,
    )
    async def fill_application(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.response.send_modal(SubmitStaffModal())
        except Exception as exc:
            try:
                await interaction.response.send_message(
                    f"❌ هەڵەیەک ڕوویدا. | Error opening form: `{exc}`", ephemeral=True
                )
            except Exception:
                pass

    @discord.ui.button(
        label="🌐 Choose Language | زمان هەڵبژێرە",
        style=discord.ButtonStyle.secondary,
        custom_id="staff:language",
        row=0,
    )
    async def choose_language(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = LanguageSelectView(
            panel_message_id=interaction.message.id,
            panel_channel_id=interaction.channel_id,
            guild_name=interaction.guild.name,
            icon_url=_guild_icon_url(interaction.guild),
            mode="staff_app",
            user_avatar=interaction.user.display_avatar.url,
        )
        await interaction.response.send_message(
            "🌐 **زمانێک هەڵبژێرە | Choose the language:**",
            view=view,
            ephemeral=True,
        )

    @discord.ui.button(
        label="❌ Close Application | داخستنی داواکاری",
        style=discord.ButtonStyle.danger,
        custom_id="staff:close",
        row=0,
    )
    async def close_application(self, interaction: discord.Interaction, button: discord.ui.Button):
        for (gid, uid), cid in list(open_staff_apps.items()):
            if cid == interaction.channel_id:
                open_staff_apps.pop((gid, uid), None)
                break
        save_open_staff_apps()
        await interaction.response.send_message(
            "❌ داخستنی داواکاری لە 5 چرکەدا... | Closing application channel in 5 seconds...",
            ephemeral=False,
        )
        await asyncio.sleep(5)
        try:
            await interaction.channel.delete(reason="Staff application closed")
        except (discord.Forbidden, discord.HTTPException):
            pass


# ── Main ticket panel view ────────────────────────────────────────────────────

class TicketPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    # ── Button 1: Create Ticket ───────────────────────────────────────────────
    @discord.ui.button(
        label="🎫 Create Ticket | تیکەت دروست بکە",
        style=discord.ButtonStyle.success,
        custom_id="ticket:create",
        row=0,
    )
    async def create_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Acknowledge immediately — this prevents "This interaction failed"
        try:
            await interaction.response.defer(ephemeral=True)
        except Exception:
            return

        try:
            guild = interaction.guild
            if not guild:
                return await interaction.followup.send("❌ Server only.", ephemeral=True)

            cfg = get_ticket_cfg(guild.id)
            key = (str(guild.id), str(interaction.user.id))

            # ── Already has an open ticket? ───────────────────────────────────
            existing_cid = open_tickets_map.get(key)
            if existing_cid:
                existing_ch = guild.get_channel(int(existing_cid))
                if existing_ch:
                    return await interaction.followup.send(
                        "❌ تیکەتێکی کراوەت هەیە | You already have an open ticket: "
                        + existing_ch.mention,
                        ephemeral=True,
                    )
                open_tickets_map.pop(key, None)

            safe_name = "".join(c for c in interaction.user.name.lower() if c.isalnum())[:20] or "user"
            cat_id    = cfg.get("category_id")
            category  = guild.get_channel(int(cat_id)) if cat_id else None

            overwrites = {
                guild.default_role: discord.PermissionOverwrite(view_channel=False),
                interaction.user:   discord.PermissionOverwrite(
                    view_channel=True, send_messages=True, read_message_history=True,
                    attach_files=True,
                ),
                guild.me: discord.PermissionOverwrite(
                    view_channel=True, send_messages=True, read_message_history=True,
                    manage_channels=True, manage_messages=True, embed_links=True,
                ),
            }
            staff_rid = cfg.get("staff_role_id")
            if staff_rid:
                staff_role = guild.get_role(int(staff_rid))
                if staff_role:
                    overwrites[staff_role] = discord.PermissionOverwrite(
                        view_channel=True, send_messages=True,
                        read_message_history=True, manage_messages=True,
                        attach_files=True,
                    )

            # ── Create the channel ────────────────────────────────────────────
            try:
                ticket_ch = await guild.create_text_channel(
                    name="ticket-" + safe_name,
                    category=category,
                    overwrites=overwrites,
                )
            except discord.Forbidden:
                return await interaction.followup.send(
                    "❌ بۆتەکە مووچەی پێویستی نییە بۆ دروستکردنی کەناڵ.\n"
                    "The bot lacks permission to create channels. Please give it **Manage Channels** + **Manage Roles**.",
                    ephemeral=True,
                )
            except discord.HTTPException as e:
                return await interaction.followup.send(
                    "❌ نەتوانرا تیکەت دروست بکرێت | Could not create ticket: `" + str(e) + "`",
                    ephemeral=True,
                )

            # ── Track & save ──────────────────────────────────────────────────
            open_tickets_map[key] = ticket_ch.id
            save_open_tickets()

            # ── Build the welcome embed ───────────────────────────────────────
            ticket_embed = discord.Embed(
                color=0xFFD700,
                title="🎫 Ticket — " + interaction.user.display_name,
                description=(
                    "سڵاو " + interaction.user.mention + " 👋\n\n"
                    "🇬🇧 Welcome! Please describe your issue and a staff member will assist you shortly.\n\n"
                    "🇮🇶 بەخێربێیت! تکایە کێشەکەت شرۆڤە بکە و ئەندامێکی تیم زووترین کات یارمەتیت دەدات.\n\n"
                    "──────────────────────\n"
                    "🔒 To close this ticket, click the button below.\n"
                    "🔒 بۆ داخستنی تیکەت، دوگمەکە دابگرە."
                ),
                timestamp=datetime.datetime.utcnow(),
            )
            ticket_embed.set_thumbnail(url=interaction.user.display_avatar.url)
            ticket_embed.set_footer(text=guild.name + " Support")
            icon = _guild_icon_url(guild)
            if icon:
                ticket_embed.set_image(url=icon)

            mention_str = interaction.user.mention
            if staff_rid:
                mention_str += " <@&" + str(staff_rid) + ">"

            # ── Send welcome message (wrapped — never let this crash the interaction) ──
            try:
                await ticket_ch.send(content=mention_str, embed=ticket_embed, view=TicketControlView())
            except (discord.Forbidden, discord.HTTPException):
                pass  # channel exists, message failed — still show the link

            # ── Confirm to user ───────────────────────────────────────────────
            await interaction.followup.send(
                "✅ تیکەتەکەت دروستکرا | Your ticket has been created: " + ticket_ch.mention,
                ephemeral=True,
            )
            await ticket_log(guild, "🎫 **Ticket opened** by " + interaction.user.mention + " → " + ticket_ch.mention)

        except Exception as e:
            try:
                await interaction.followup.send(
                    "❌ هەڵەیەک ڕوویدا | An unexpected error occurred: `"
                    + type(e).__name__ + ": " + str(e) + "`",
                    ephemeral=True,
                )
            except Exception:
                pass

    # ── Button 2: Choose Language ─────────────────────────────────────────────
    @discord.ui.button(
        label="🌐 Choose Language | زمان هەڵبژێرە",
        style=discord.ButtonStyle.secondary,
        custom_id="ticket:language",
        row=0,
    )
    async def choose_language(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = LanguageSelectView(
            panel_message_id=interaction.message.id,
            panel_channel_id=interaction.channel_id,
            guild_name=interaction.guild.name,
            icon_url=_guild_icon_url(interaction.guild),
            mode="panel",
        )
        await interaction.response.send_message(
            "🌐 **زمانێک هەڵبژێرە | Choose the panel language:**",
            view=view,
            ephemeral=True,
        )

    # ── Button 3: Submit Staff ────────────────────────────────────────────────
    @discord.ui.button(
        label="📋 Submit Staff | داواکاری ستاف",
        style=discord.ButtonStyle.blurple,
        custom_id="ticket:submitstaff",
        row=0,
    )
    async def submit_staff(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.response.defer(ephemeral=True)
        except Exception:
            return

        try:
            guild = interaction.guild
            if not guild:
                return await interaction.followup.send("❌ Server only.", ephemeral=True)

            cfg = get_ticket_cfg(guild.id)
            key = (str(guild.id), str(interaction.user.id))

            # ── Already has an open staff application? ────────────────────────
            existing_cid = open_staff_apps.get(key)
            if existing_cid:
                existing_ch = guild.get_channel(int(existing_cid))
                if existing_ch:
                    return await interaction.followup.send(
                        "❌ داواکارییەکی کراوەت هەیە | You already have an open application: "
                        + existing_ch.mention,
                        ephemeral=True,
                    )
                open_staff_apps.pop(key, None)

            safe_name = "".join(c for c in interaction.user.name.lower() if c.isalnum())[:20] or "user"
            cat_id    = cfg.get("category_id")
            category  = guild.get_channel(int(cat_id)) if cat_id else None

            overwrites = {
                guild.default_role: discord.PermissionOverwrite(view_channel=False),
                interaction.user:   discord.PermissionOverwrite(
                    view_channel=True, send_messages=True, read_message_history=True,
                    attach_files=True,
                ),
                guild.me: discord.PermissionOverwrite(
                    view_channel=True, send_messages=True, read_message_history=True,
                    manage_channels=True, manage_messages=True, embed_links=True,
                ),
            }
            staff_rid = cfg.get("staff_role_id")
            if staff_rid:
                staff_role = guild.get_role(int(staff_rid))
                if staff_role:
                    overwrites[staff_role] = discord.PermissionOverwrite(
                        view_channel=True, send_messages=True,
                        read_message_history=True, manage_messages=True,
                        attach_files=True,
                    )

            # ── Create the staff app channel ──────────────────────────────────
            try:
                app_ch = await guild.create_text_channel(
                    name="staff-app-" + safe_name,
                    category=category,
                    overwrites=overwrites,
                )
            except discord.Forbidden:
                return await interaction.followup.send(
                    "❌ بۆتەکە مووچەی پێویستی نییە بۆ دروستکردنی کەناڵ.\n"
                    "The bot lacks permission to create channels. Please give it **Manage Channels** + **Manage Roles**.",
                    ephemeral=True,
                )
            except discord.HTTPException as e:
                return await interaction.followup.send(
                    "❌ نەتوانرا کەناڵی داواکاری دروست بکرێت | Could not create application channel: `"
                    + str(e) + "`",
                    ephemeral=True,
                )

            open_staff_apps[key] = app_ch.id
            save_open_staff_apps()

            app_embed = build_staff_app_embed(
                guild.name,
                user_avatar=interaction.user.display_avatar.url,
                icon_url=_guild_icon_url(guild),
            )
            mention_str = interaction.user.mention
            if staff_rid:
                mention_str += " <@&" + str(staff_rid) + ">"

            try:
                await app_ch.send(content=mention_str, embed=app_embed, view=StaffAppControlView())
            except (discord.Forbidden, discord.HTTPException):
                pass

            await interaction.followup.send(
                "✅ کەناڵی داواکارییەکەت دروستکرا | Your application channel has been created: "
                + app_ch.mention,
                ephemeral=True,
            )
            await ticket_log(guild, "📋 **Staff application opened** by " + interaction.user.mention + " → " + app_ch.mention)

        except Exception as e:
            try:
                await interaction.followup.send(
                    "❌ هەڵەیەک ڕوویدا | An unexpected error occurred: `"
                    + type(e).__name__ + ": " + str(e) + "`",
                    ephemeral=True,
                )
            except Exception:
                pass


# ── Ticket control view ───────────────────────────────────────────────────────

class TicketControlView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="🔒 Close Ticket | داخستنی تیکەت",
        style=discord.ButtonStyle.danger,
        custom_id="ticket:close",
    )
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            "🔒 داخستنی تیکەت لە 5 چرکەدا... | Closing ticket in 5 seconds...",
            ephemeral=False,
        )
        for (gid, uid), cid in list(open_tickets_map.items()):
            if int(cid) == interaction.channel_id:
                open_tickets_map.pop((gid, uid), None)
                break
        save_open_tickets()
        await ticket_log(
            interaction.guild,
            "🔒 **Ticket closed** " + interaction.channel.mention + " by " + interaction.user.mention,
        )
        await asyncio.sleep(5)
        try:
            await interaction.channel.delete(reason="Ticket closed")
        except (discord.Forbidden, discord.HTTPException):
            pass

    @discord.ui.button(
        label="✋ Claim Ticket | وەرگرتنی تیکەت",
        style=discord.ButtonStyle.primary,
        custom_id="ticket:claim",
    )
    async def claim_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = get_ticket_cfg(interaction.guild.id)
        staff_rid = cfg.get("staff_role_id")
        if staff_rid:
            staff_role = interaction.guild.get_role(int(staff_rid))
            if staff_role and staff_role not in interaction.user.roles:
                return await interaction.response.send_message(
                    "❌ تەنها ستاف دەتوانێت تیکەت وەربگرێت | Only staff can claim tickets.",
                    ephemeral=True,
                )
        await interaction.response.send_message(
            "✋ ئەم تیکەتە وەرگیرا لەلایەن | This ticket has been claimed by "
            + interaction.user.mention
        )
        await ticket_log(
            interaction.guild,
            "✋ **Ticket claimed** " + interaction.channel.mention + " by " + interaction.user.mention,
        )


# ── Ticket setup commands ─────────────────────────────────────────────────────

@bot.command(name="setpanel", aliases=["ticketpanel"])
@commands.has_permissions(administrator=True)
async def setpanel(ctx, channel: discord.TextChannel = None):
    if ctx.guild is None:
        return await ctx.send("Server only. | تەنها لە سێرڤەر.")
    target = channel or ctx.channel
    cfg = ticket_settings.setdefault(str(ctx.guild.id), {})
    cfg["panel_channel_id"] = target.id
    save_ticket_settings()
    embed = build_ticket_panel_embed(ctx.guild.name, _guild_icon_url(ctx.guild))
    await target.send(embed=embed, view=TicketPanelView())
    if target != ctx.channel:
        await ctx.send(
            "✅ پانێلی تیکەت نێردرا بۆ " + target.mention + " | Ticket panel sent to " + target.mention + ".",
            delete_after=10,
        )
    try:
        await ctx.message.delete()
    except (discord.Forbidden, discord.HTTPException):
        pass

@bot.command(name="setstaffrole", aliases=["ticketstaffrole"])
@commands.has_permissions(administrator=True)
async def setstaffrole(ctx, role: discord.Role):
    if ctx.guild is None:
        return
    cfg = ticket_settings.setdefault(str(ctx.guild.id), {})
    cfg["staff_role_id"] = role.id
    save_ticket_settings()
    await ctx.send("✅ رۆڵی ستاف دانرا: " + role.mention + " | Staff role set to " + role.mention + ".")

@bot.command(name="setticketcategory", aliases=["ticketcategory"])
@commands.has_permissions(manage_guild=True)
async def setticketcategory(ctx, *, category_name: str):
    if ctx.guild is None:
        return
    cat = discord.utils.get(ctx.guild.categories, name=category_name)
    if not cat:
        return await ctx.send("❌ کاتێگۆری نەدۆزرایەوە | Category `" + category_name + "` not found.")
    cfg = ticket_settings.setdefault(str(ctx.guild.id), {})
    cfg["category_id"] = cat.id
    save_ticket_settings()
    await ctx.send("✅ کاتێگۆری دانرا: **" + cat.name + "** | Ticket category set to **" + cat.name + "**.")

@bot.command(name="setticketlog", aliases=["ticketlog"])
@commands.has_permissions(manage_guild=True)
async def setticketlog(ctx, channel: discord.TextChannel = None):
    if ctx.guild is None:
        return
    target = channel or ctx.channel
    cfg = ticket_settings.setdefault(str(ctx.guild.id), {})
    cfg["log_channel_id"] = target.id
    save_ticket_settings()
    await ctx.send(
        "✅ کەناڵی لۆگی تیکەت دانرا: " + target.mention + " | Ticket log channel set to " + target.mention + "."
    )

@bot.command(name="staffsubmitlog", aliases=["setstaffsubmitlog", "stafflogchannel"])
@commands.has_permissions(administrator=True)
async def staffsubmitlog_cmd(ctx, channel: discord.TextChannel = None):
    if ctx.guild is None:
        return await ctx.send("Server only. | تەنها لە سێرڤەر.")
    target = channel or ctx.channel
    staff_submit_log_channels[str(ctx.guild.id)] = target.id
    save_staff_submit_log_channels()
    e = discord.Embed(
        color=0x57F287,
        title="✅ کەناڵی لۆگی داواکاری دانراو! | Staff Submit Log Set!",
        description=(
            "داواکارییەکانی ستاف دەنێردرێن بۆ " + target.mention + ".\n"
            "Staff applications will be logged to " + target.mention + "."
        ),
        timestamp=datetime.datetime.utcnow(),
    )
    if ctx.guild.icon:
        e.set_thumbnail(url=ctx.guild.icon.url)
    e.set_footer(text="Set by " + ctx.author.display_name)
    await ctx.send(embed=e)
    try:
        await ctx.message.delete()
    except (discord.Forbidden, discord.HTTPException):
        pass

@staffsubmitlog_cmd.error
async def staffsubmitlog_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ مووچەی Manage Server پێویستە. | You need Manage Server permission.")
    elif isinstance(error, commands.ChannelNotFound):
        await ctx.send("❌ کەناڵ نەدۆزرایەوە. | Channel not found.")

@bot.command(name="ticketstatus")
@commands.has_permissions(manage_guild=True)
async def ticketstatus(ctx):
    if ctx.guild is None:
        return
    cfg      = get_ticket_cfg(ctx.guild.id)
    staff_rid = cfg.get("staff_role_id")
    cat_id    = cfg.get("category_id")
    log_cid   = cfg.get("log_channel_id")
    panel_cid = cfg.get("panel_channel_id")
    gid_str   = str(ctx.guild.id)
    slog_cid  = staff_submit_log_channels.get(gid_str)
    open_count = sum(1 for (gid, _), _ in open_tickets_map.items() if gid == gid_str)
    apps_count = sum(1 for (gid, _), _ in open_staff_apps.items()  if gid == gid_str)
    embed = discord.Embed(
        color=0xFFD700,
        title="🎫 Ticket System Status | دۆخی سیستەمی تیکەت",
        timestamp=datetime.datetime.utcnow(),
    )
    embed.add_field(name="👮 Staff Role",        value="<@&" + str(staff_rid) + ">" if staff_rid else "❌ Not set", inline=True)
    embed.add_field(name="📂 Category",          value="<#"  + str(cat_id)    + ">" if cat_id    else "❌ Not set", inline=True)
    embed.add_field(name="📋 Ticket Log",        value="<#"  + str(log_cid)   + ">" if log_cid   else "❌ Not set", inline=True)
    embed.add_field(name="📢 Panel Channel",     value="<#"  + str(panel_cid) + ">" if panel_cid else "❌ Not set", inline=True)
    embed.add_field(name="📨 Staff Submit Log",  value="<#"  + str(slog_cid)  + ">" if slog_cid  else "❌ Not set", inline=True)
    embed.add_field(name="🎫 Open Tickets",      value="`" + str(open_count) + "`",                                 inline=True)
    embed.add_field(name="📋 Open Applications", value="`" + str(apps_count) + "`",                                 inline=True)
    embed.set_footer(text="Requested by " + ctx.author.display_name)
    await ctx.send(embed=embed)


# ─────────────────────────────────────────────────────────────────────────────
# --- RULES SYSTEM ---
# ─────────────────────────────────────────────────────────────────────────────

class RulesEditModal(discord.ui.Modal, title="✏️ دەستکاری قانوونەکان | Edit Rules"):
    text_en = discord.ui.TextInput(
        label="🇬🇧 English Rules Text",
        placeholder="Write the English rules here...",
        style=discord.TextStyle.paragraph,
        max_length=2000,
        required=False,
    )
    text_ku = discord.ui.TextInput(
        label="🇮🇶 Kurdish Rules | دەقی قانوونی کوردی",
        placeholder="قانوونەکانی کوردی لێرە بنووسە...",
        style=discord.TextStyle.paragraph,
        max_length=2000,
        required=False,
    )

    def __init__(self, message_id: int, channel_id: int, guild_name: str,
                 icon_url: str = None, current_en: str = "", current_ku: str = ""):
        super().__init__()
        self.message_id  = message_id
        self.channel_id  = channel_id
        self.guild_name  = guild_name
        self.icon_url    = icon_url
        self.text_en.default = current_en
        self.text_ku.default = current_ku

    async def on_submit(self, interaction: discord.Interaction):
        gid = str(interaction.guild.id) if interaction.guild else None
        en  = self.text_en.value.strip()
        ku  = self.text_ku.value.strip()
        if gid:
            rules_settings[gid] = {"text_en": en, "text_ku": ku}
            save_rules_settings()
        embed = build_rules_embed(self.guild_name, en, ku, self.icon_url)
        ch = interaction.guild.get_channel(self.channel_id) if interaction.guild else None
        if ch:
            try:
                msg = await ch.fetch_message(self.message_id)
                await msg.edit(embed=embed)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                pass
        await interaction.response.send_message(
            "✅ قانوونەکان نوێکرانەوە! | Rules updated successfully! 📜",
            ephemeral=True,
        )

    async def on_error(self, interaction: discord.Interaction, error: Exception):
        try:
            await interaction.response.send_message(
                "❌ هەڵەیەک ڕوویدا. | An error occurred.", ephemeral=True
            )
        except Exception:
            pass


class RulesPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="✏️ Edit Text | دەقی بگۆڕە",
        style=discord.ButtonStyle.secondary,
        custom_id="rules:edit",
        row=0,
    )
    async def edit_text(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message(
                "❌ تەنها ئەدمین دەتوانێت قانوونەکان دەستکاری بکات. | Only administrators can edit rules.",
                ephemeral=True,
            )
        gid = str(interaction.guild.id) if interaction.guild else ""
        s   = rules_settings.get(gid, {})
        modal = RulesEditModal(
            message_id=interaction.message.id,
            channel_id=interaction.channel_id,
            guild_name=interaction.guild.name,
            icon_url=_guild_icon_url(interaction.guild),
            current_en=s.get("text_en", ""),
            current_ku=s.get("text_ku", ""),
        )
        await interaction.response.send_modal(modal)

    @discord.ui.button(
        label="🌐 Choose Language | زمان هەڵبژێرە",
        style=discord.ButtonStyle.primary,
        custom_id="rules:language",
        row=0,
    )
    async def choose_language(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message(
                "❌ تەنها ئەدمین دەتوانێت زمان بگۆڕێت. | Only administrators can change language.",
                ephemeral=True,
            )
        view = LanguageSelectView(
            panel_message_id=interaction.message.id,
            panel_channel_id=interaction.channel_id,
            guild_name=interaction.guild.name,
            icon_url=_guild_icon_url(interaction.guild),
            mode="rules",
        )
        await interaction.response.send_message(
            "🌐 **زمانێک هەڵبژێرە | Choose language:**",
            view=view,
            ephemeral=True,
        )


@bot.command(name="rule", aliases=["rules", "setrules", "rulepanel"])
@commands.has_permissions(administrator=True)
async def rule_cmd(ctx, channel: discord.TextChannel = None):
    if ctx.guild is None:
        return await ctx.send("Server only. | تەنها لە سێرڤەر.")
    target = channel or ctx.channel
    gid    = str(ctx.guild.id)
    s      = rules_settings.get(gid, {})
    embed  = build_rules_embed(
        ctx.guild.name,
        s.get("text_en", ""),
        s.get("text_ku", ""),
        _guild_icon_url(ctx.guild),
    )
    await target.send(embed=embed, view=RulesPanelView())
    if target != ctx.channel:
        await ctx.send(
            "✅ پانێلی قانوون نێردرا بۆ " + target.mention + " | Rules panel sent to " + target.mention + ".",
            delete_after=10,
        )
    try:
        await ctx.message.delete()
    except (discord.Forbidden, discord.HTTPException):
        pass

@rule_cmd.error
async def rule_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ مووچەی Manage Server پێویستە. | You need Manage Server permission.")
    elif isinstance(error, commands.ChannelNotFound):
        await ctx.send("❌ کەناڵ نەدۆزرایەوە. | Channel not found.")


# ─────────────────────────────────────────────────────────────────────────────
# --- TAG SYSTEM ---
# ─────────────────────────────────────────────────────────────────────────────

class SetTagModal(discord.ui.Modal, title="🏷️ دروستکردنی تاگ | Create / Edit Tag"):
    tag_name = discord.ui.TextInput(
        label="ناوی تاگ | Tag Name",
        placeholder="ناوی تاگ | e.g.  rules  •  discord  •  welcome",
        max_length=50,
        style=discord.TextStyle.short,
    )
    response_text = discord.ui.TextInput(
        label="وەڵامی تاگ | Tag Response",
        placeholder="The message the bot sends when this tag is triggered...",
        max_length=1950,
        style=discord.TextStyle.paragraph,
    )

    def __init__(self, prefill_name: str = ""):
        super().__init__()
        if prefill_name:
            self.tag_name.default = prefill_name

    async def on_submit(self, interaction: discord.Interaction):
        if not interaction.guild:
            return await interaction.response.send_message("Server only.", ephemeral=True)
        name = self.tag_name.value.strip()
        resp = self.response_text.value.strip()
        if not name:
            return await interaction.response.send_message(
                "❌ ناوی تاگ نابێت بەتاڵ بێت. | Tag name cannot be empty.", ephemeral=True
            )
        if not resp:
            return await interaction.response.send_message(
                "❌ وەڵام نابێت بەتاڵ بێت. | Response cannot be empty.", ephemeral=True
            )
        save_tag(interaction.guild.id, name, resp, interaction.user.id)
        e = discord.Embed(
            color=0x57F287,
            title="✅ تاگ خەزن کرا! | Tag Saved!",
            timestamp=datetime.datetime.utcnow(),
        )
        e.add_field(name="🏷️ ناوی تاگ | Tag Name", value="`" + name + "`", inline=True)
        e.add_field(
            name="💬 چۆن بەکاری بێنن | How to use",
            value="type `" + name + "` or `!tag " + name + "`",
            inline=False,
        )
        e.add_field(
            name="📝 وەڵام | Response",
            value=resp[:300] + ("…" if len(resp) > 300 else ""),
            inline=False,
        )
        if interaction.guild.icon:
            e.set_thumbnail(url=interaction.guild.icon.url)
        e.set_footer(text="Created by " + interaction.user.display_name)
        await interaction.response.send_message(embed=e, ephemeral=True)

    async def on_error(self, interaction: discord.Interaction, error: Exception):
        try:
            await interaction.response.send_message(
                "❌ هەڵەیەک ڕوویدا. | An error occurred.", ephemeral=True
            )
        except Exception:
            pass


class _TagSetupButtonView(discord.ui.View):
    """Ephemeral view shown by !settag — one button that opens SetTagModal."""
    def __init__(self, author_id: int, prefill: str = ""):
        super().__init__(timeout=60)
        self.author_id = author_id
        self.prefill   = prefill

    @discord.ui.button(label="✏️ Open Tag Form | فۆرمی تاگ کەرەوە", style=discord.ButtonStyle.primary)
    async def open_form(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            return await interaction.response.send_message(
                "❌ تەنها ئەو کەسە دەتوانێت. | Only the command user.", ephemeral=True
            )
        await interaction.response.send_modal(SetTagModal(prefill_name=self.prefill))
        self.stop()

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True


@bot.command(name="settag", aliases=["createtag", "addtag", "edittag"])
@commands.has_permissions(manage_guild=True)
async def settag_cmd(ctx, *, tag_name: str = ""):
    if ctx.guild is None:
        return await ctx.send("Server only. | تەنها لە سێرڤەر.")
    try:
        await ctx.message.delete()
    except (discord.Forbidden, discord.HTTPException):
        pass
    prefill = tag_name.strip()[:50]
    e = discord.Embed(
        color=0x5865F2,
        title="🏷️ دروستکردنی تاگی نوێ | Create / Edit Tag",
        description=(
            "دوگمەی خوارەوە دابگرە بۆ کردنەوەی فۆرمەکە.\n"
            "Click the button below to open the tag form.\n\n"
            "تاگ تەنها لە ئەم سێرڤەرەدا کاردەکات.\n"
            "The tag will only work in this server."
        ),
        timestamp=datetime.datetime.utcnow(),
    )
    if ctx.guild.icon:
        e.set_thumbnail(url=ctx.guild.icon.url)
    e.set_footer(text="Requested by " + ctx.author.display_name)
    await ctx.send(embed=e, view=_TagSetupButtonView(ctx.author.id, prefill))

@settag_cmd.error
async def settag_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ مووچەی Manage Server پێویستە. | You need Manage Server permission.")


@bot.command(name="tag", aliases=["gettag", "showtag"])
async def tag_cmd(ctx, *, tag_name: str = ""):
    if ctx.guild is None:
        return await ctx.send("Server only. | تەنها لە سێرڤەر.")
    name  = tag_name.strip().lower()
    if not name:
        return await ctx.invoke(taglist_cmd)
    entry = tags_data.get(str(ctx.guild.id), {}).get(name)
    if not entry:
        return await ctx.send(
            "❌ تاگی `" + tag_name + "` نەدۆزرایەوە. | Tag `" + tag_name
            + "` not found. Use `!taglist` to see all tags.",
            delete_after=10,
        )
    await ctx.send(entry["response"])


@bot.command(name="taglist", aliases=["tags", "listtags", "showtags"])
async def taglist_cmd(ctx):
    if ctx.guild is None:
        return await ctx.send("Server only.")
    guild_tags = tags_data.get(str(ctx.guild.id), {})
    if not guild_tags:
        return await ctx.send(
            "❌ هیچ تاگێک نەدۆزرایەوە. | No tags found.\nAdmins can add tags with `!settag`."
        )

    lines   = []
    for key, val in sorted(guild_tags.items()):
        preview = val["response"].replace("\n", " ")[:60]
        if len(val["response"]) > 60:
            preview += "…"
        lines.append("**`" + val["name"] + "`** — " + preview)

    chunks  = []
    current = []
    length  = 0
    for line in lines:
        if length + len(line) > 900:
            chunks.append("\n".join(current))
            current = [line]
            length  = len(line)
        else:
            current.append(line)
            length += len(line)
    if current:
        chunks.append("\n".join(current))

    for i, chunk in enumerate(chunks):
        suffix = " (" + str(i + 1) + "/" + str(len(chunks)) + ")" if len(chunks) > 1 else ""
        e = discord.Embed(
            color=0x5865F2,
            title="🏷️ تاگەکانی " + ctx.guild.name + suffix,
            description=chunk,
            timestamp=datetime.datetime.utcnow(),
        )
        e.set_footer(
            text=str(len(guild_tags)) + " tag(s) · type: tag <name>  or  !tag <name>"
        )
        if ctx.guild.icon:
            e.set_thumbnail(url=ctx.guild.icon.url)
        await ctx.send(embed=e)


@bot.command(name="deltag", aliases=["removetag", "deletetag", "untag"])
@commands.has_permissions(manage_guild=True)
async def deltag_cmd(ctx, *, tag_name: str = ""):
    if ctx.guild is None:
        return await ctx.send("Server only.")
    name = tag_name.strip()
    if not name:
        return await ctx.send(
            "❌ ناوی تاگ بنووسە. | Provide a tag name: `!deltag <name>`"
        )
    removed = delete_tag(ctx.guild.id, name)
    if removed:
        e = discord.Embed(
            color=0xED4245,
            title="🗑️ تاگ سڕایەوە | Tag Deleted",
            description="تاگی **`" + name + "`** سڕایەوە.\nTag **`" + name + "`** has been removed.",
            timestamp=datetime.datetime.utcnow(),
        )
        e.set_footer(text="Deleted by " + ctx.author.display_name)
        await ctx.send(embed=e)
    else:
        await ctx.send(
            "❌ تاگی `" + name + "` نەدۆزرایەوە. | Tag `" + name
            + "` not found. Use `!taglist` to see all tags."
        )

@deltag_cmd.error
async def deltag_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ مووچەی Manage Server پێویستە. | You need Manage Server permission.")

# ─────────────────────────────────────────────────────────────────────────────
# --- GIVEAWAY SYSTEM ---
# ─────────────────────────────────────────────────────────────────────────────

def format_duration(seconds: int) -> str:
    d, rem = divmod(seconds, 86400)
    h, rem = divmod(rem, 3600)
    m, s   = divmod(rem, 60)
    parts = []
    if d: parts.append(f"{d}d")
    if h: parts.append(f"{h}h")
    if m: parts.append(f"{m}m")
    if s or not parts: parts.append(f"{s}s")
    return " ".join(parts)


# ─────────────────────────────────────────────────────────────────────────────
# --- GIVEAWAY SYSTEM ---
# ─────────────────────────────────────────────────────────────────────────────

GIVEAWAY_EMOJI = "🌟"


def _build_giveaway_embed(
    prize: str,
    host: discord.Member,
    winners_count: int,
    end_time: datetime.datetime,
    ended: bool = False,
    winners=None,
) -> discord.Embed:
    color = 0xFFD700
    if ended:
        title = "🎉 بەخشین کۆتایی هات! | Giveaway Ended!"
        desc = f"**خەڵات | Prize:** {prize}\n\n"
        if winners:
            mentions = " ".join(w.mention for w in winners)
            desc += f"🏆 **بەختەوار | Winner(s):** {mentions}"
        else:
            desc += "😢 هیچ بەشداریێک نەبوو — بەختەوار نییە | No valid entries — no winner."
    else:
        title = "🌟 G I V E A W A Y | بەخشین 🌟"
        desc = (
            f"**خەڵات | Prize:** {prize}\n\n"
            f"React with {GIVEAWAY_EMOJI} to enter! | بکرتە لەسەر {GIVEAWAY_EMOJI} بۆ بەشداری!\n\n"
            f"**کۆتایی | Ends:** <t:{int(end_time.timestamp())}:R>\n"
            f"**بەختەوار | Winners:** {winners_count}"
        )
    embed = discord.Embed(title=title, description=desc, color=color)
    embed.set_footer(
        text=f"لەلایەن | Hosted by {host.display_name}  •  "
             f"{'Ended' if ended else 'Ends'}: {end_time.strftime('%m/%d/%y %I:%M %p UTC')}"
    )
    embed.timestamp = end_time
    return embed


async def _end_giveaway(message_id: int, channel: discord.TextChannel):
    data = active_giveaways.pop(message_id, None)
    if not data:
        return
    try:
        msg = await channel.fetch_message(message_id)
    except discord.NotFound:
        return
    entrants = []
    for reaction in msg.reactions:
        if str(reaction.emoji) == GIVEAWAY_EMOJI:
            async for user in reaction.users():
                if not user.bot:
                    entrants.append(user)
            break
    winner_count = data["winners_count"]
    winners = random.sample(entrants, min(winner_count, len(entrants))) if entrants else []
    ended_embed = _build_giveaway_embed(
        data["prize"], data["host"], winner_count, data["end_time"], ended=True, winners=winners
    )
    await msg.edit(embed=ended_embed)
    if winners:
        winner_mentions = " ".join(w.mention for w in winners)
        await channel.send(
            f"🎊 دەستخۆش {winner_mentions}! تۆ **{data['prize']}** بەردیت!\n"
            f"🎊 Congratulations {winner_mentions}! You won **{data['prize']}**!\n"
            f"> [Jump to giveaway | بازدە بۆ بەخشینەکە]({msg.jump_url})"
        )
    else:
        await channel.send(
            f"😢 هیچ بەشداریێکی دروستی نەبوو بۆ **{data['prize']}**. بەختەوار هەڵنەبژێرا.\n"
            f"😢 No valid entries for **{data['prize']}**. No winner was selected."
        )


async def _launch_giveaway(channel, prize, host, winner_count, seconds):
    """Background task: posts giveaway embed and waits for it to end."""
    end_time = datetime.datetime.utcnow() + datetime.timedelta(seconds=seconds)
    embed = _build_giveaway_embed(prize, host, winner_count, end_time)
    giveaway_msg = await channel.send(embed=embed)
    await giveaway_msg.add_reaction(GIVEAWAY_EMOJI)
    active_giveaways[giveaway_msg.id] = {
        "prize":         prize,
        "host":          host,
        "winners_count": winner_count,
        "end_time":      end_time,
        "channel_id":    channel.id,
        "message_id":    giveaway_msg.id,
    }
    await asyncio.sleep(seconds)
    await _end_giveaway(giveaway_msg.id, channel)


class GiveawayModal(discord.ui.Modal, title="🎉 بەخشینی نوێ | New Giveaway"):
    prize = discord.ui.TextInput(
        label="خەڵات | Prize",
        placeholder="e.g. Discord Nitro, 5000 coins, Steam key...",
        max_length=200,
    )
    duration_input = discord.ui.TextInput(
        label="ماوە | Duration  (10m / 2h / 1d)",
        placeholder="10m = 10 minutes · 2h = 2 hours · 1d = 1 day",
        max_length=10,
    )

    def __init__(self, winner_count: int):
        super().__init__()
        self._winner_count = winner_count

    async def on_submit(self, interaction: discord.Interaction):
        seconds = parse_duration(self.duration_input.value.strip())
        if seconds is None or seconds < 10:
            return await interaction.response.send_message(
                "❌ ماوەی نادروست | Invalid duration. Use `10m`, `2h`, `1d` (min 10s).",
                ephemeral=True,
            )
        await interaction.response.send_message(
            f"✅ بەخشینەکە دەستپێکرا! {self._winner_count} بەختەوار | Giveaway started! {self._winner_count} winner(s).",
            ephemeral=True,
        )
        asyncio.create_task(
            _launch_giveaway(
                interaction.channel,
                self.prize.value.strip(),
                interaction.user,
                self._winner_count,
                seconds,
            )
        )

    async def on_error(self, interaction: discord.Interaction, error: Exception):
        try:
            if interaction.response.is_done():
                await interaction.followup.send(f"❌ هەڵە | Error: {error}", ephemeral=True)
            else:
                await interaction.response.send_message(f"❌ هەڵە | Error: {error}", ephemeral=True)
        except Exception:
            pass


class GiveawayWinnersSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label=f"{i} بەختەوار | Winner{'s' if i>1 else ''}", value=str(i), emoji="🏆")
            for i in range(1, 11)
        ]
        super().__init__(
            placeholder="🎯 ژمارەی بەختەوار هەڵبژێرە | Pick number of winners...",
            min_values=1,
            max_values=1,
            options=options,
            row=0,
        )

    async def callback(self, interaction: discord.Interaction):
        count = int(self.values[0])
        self.view.winner_count = count
        # Update the placeholder to show selection
        self.placeholder = f"🏆 {count} بەختەوار | {count} winner(s) selected"
        # Enable the start button
        for item in self.view.children:
            if hasattr(item, 'custom_id') and item.custom_id == "gw_start_btn":
                item.disabled = False
        await interaction.response.edit_message(view=self.view)


class GiveawayCreateView(discord.ui.View):
    def __init__(self, author_id: int):
        super().__init__(timeout=120)
        self._author_id = author_id
        self.winner_count = 1
        self.add_item(GiveawayWinnersSelect())

    @discord.ui.button(
        label="🎉 دروستکردنی بەخشین | Create Giveaway",
        style=discord.ButtonStyle.success,
        custom_id="gw_start_btn",
        row=1,
    )
    async def create_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self._author_id:
            return await interaction.response.send_message(
                "❌ تەنها ئەو کەسە دەتوانێت کلیک بکات | Only the command author can use this.",
                ephemeral=True,
            )
        await interaction.response.send_modal(GiveawayModal(self.winner_count))
        self.stop()


@bot.command(name="gcreate", aliases=["gstart"])
@commands.has_permissions(manage_guild=True)
async def gcreate_cmd(ctx):
    """Start a giveaway using an interactive form."""
    if ctx.guild is None:
        return await ctx.send("Server only. | تەنها لە سێرڤەر.")
    try:
        await ctx.message.delete()
    except discord.Forbidden:
        pass
    embed = discord.Embed(
        color=0xFFD700,
        title="🎉 دروستکردنی بەخشین | Create a Giveaway",
        description=(
            "**۱.** لە لیستی خوارەوە ژمارەی بەختەوار هەڵبژێرە.\n"
            "**۲.** دەگمەی **Create Giveaway** دابگرە.\n"
            "**۳.** خەڵات و ماوە پڕبکەرەوە.\n\n"
            "**1.** Pick the number of winners from the list below.\n"
            "**2.** Click **Create Giveaway**.\n"
            "**3.** Fill in the prize and duration."
        ),
    )
    embed.set_footer(text=f"Requested by {ctx.author.display_name}")
    await ctx.send(embed=embed, view=GiveawayCreateView(ctx.author.id))


@bot.command(name="greroll")
@commands.has_permissions(manage_guild=True)
async def greroll(ctx, message_id: int = None):
    """Reroll a giveaway winner. | بەختەوارێکی نوێ هەڵبژێرە. Usage: $greroll <message_id>"""
    if not message_id:
        await ctx.send("❌ ناسنامەی پەیامی بەخشینەکە بدە | Provide the giveaway message ID. `!greroll <message_id>`", delete_after=10)
        return
    try:
        msg = await ctx.channel.fetch_message(message_id)
    except discord.NotFound:
        await ctx.send("❌ پەیامەکە نەدۆزرایەوە لەم کەناڵە | Message not found in this channel.", delete_after=10)
        return
    entrants = []
    for reaction in msg.reactions:
        if str(reaction.emoji) == GIVEAWAY_EMOJI:
            async for user in reaction.users():
                if not user.bot:
                    entrants.append(user)
            break
    if not entrants:
        await ctx.send("😢 هیچ بەشداریێکی دروستی نییە | No valid entries to reroll.", delete_after=10)
        return
    winner = random.choice(entrants)
    await ctx.send(
        f"🎊 بەختەوارەکەی نوێ: {winner.mention}! دەستخۆش!\n"
        f"🎊 New winner: {winner.mention}! Congratulations!\n"
        f"> [Jump to giveaway | بازدە بۆ بەخشینەکە]({msg.jump_url})"
    )


@bot.command(name="gend")
@commands.has_permissions(manage_guild=True)
async def gend(ctx, message_id: int = None):
    """Force-end an active giveaway. | بەخشینێک زووتر کۆتایی پێبهێنە. Usage: $gend <message_id>"""
    if not message_id:
        await ctx.send("❌ ناسنامەی پەیامی بەخشینەکە بدە | Provide the giveaway message ID. `!gend <message_id>`", delete_after=10)
        return
    if message_id not in active_giveaways:
        await ctx.send("❌ هیچ بەخشینی چالاکی نەدۆزرایەوە بە ئەو ناسنامەیە | No active giveaway found with that ID.", delete_after=10)
        return
    data = active_giveaways[message_id]
    channel = bot.get_channel(data["channel_id"])
    if channel:
        await _end_giveaway(message_id, channel)
    await ctx.send("✅ کۆتایی هێنرا بەخشینەکە | Giveaway ended early.", delete_after=5)


@bot.command(name="glist")
@commands.has_permissions(manage_guild=True)
async def glist(ctx):
    """List all active giveaways. | بەخشینە چالاکەکان نیشان بدە."""
    server_giveaways = {
        mid: data for mid, data in active_giveaways.items()
        if data.get("channel_id") and bot.get_channel(data["channel_id"]) and
        bot.get_channel(data["channel_id"]).guild.id == ctx.guild.id
    }
    if not server_giveaways:
        await ctx.send("📋 هیچ بەخشینی چالاکی نییە ئێستا | No active giveaways right now.")
        return
    embed = discord.Embed(
        title="🎉 بەخشینە چالاکەکان | Active Giveaways",
        color=0xF5A623,
        timestamp=datetime.datetime.utcnow(),
    )
    for msg_id, data in server_giveaways.items():
        embed.add_field(
            name=f"🌟 {data['prize']}",
            value=(
                f"🏆 بەختەوار | Winners: `{data['winners_count']}`\n"
                f"⏳ کۆتایی | Ends: <t:{int(data['end_time'].timestamp())}:R>\n"
                f"🔑 Message ID: `{msg_id}`"
            ),
            inline=False,
        )
    embed.set_footer(text=f"لەلایەن | Requested by {ctx.author.display_name}")
    await ctx.send(embed=embed)


@gcreate_cmd.error
@greroll.error
@gend.error
async def _giveaway_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ پێویستت بە مووچەی **Manage Server** هەیە | You need **Manage Server** permission.", delete_after=10)
    else:
        await ctx.send(f"❌ هەڵە | Error: {error}", delete_after=10)


# ─────────────────────────────────────────────────────────────────────────────
# --- BOMB NUMBER GAME ---
# ─────────────────────────────────────────────────────────────────────────────

BOOM_MESSAGES = [
    "💥 **BOOOOOM!** تۆ بۆمبەکەت دۆزیەوە! بەختەوارتر بە داهاتوودا | You found the bomb! Better luck next time, kaboom king 👑",
    "🧨 **KA-BOOOOM!** ئەوە بۆمبەکە بوو! | That was the bomb! You just blew up the whole server 😂",
    "💣 **BOOM!** بەڵێ... ئەوە بەتایبەتی بۆمبەکە بوو. | Yep... that was definitely the bomb. F in the chat 🙏",
    "💥 **TEQÎN HATE DÎTIN!** ژمارەی هەڵەت هەڵبژارد | You picked the wrong number, soldier 💀",
    "🔥 **BOOM!** بۆمبەکە ئەوێبوو و باشی کرت دایت | The bomb was RIGHT THERE and you still pressed it 😭",
    "💣 **KABOOM!** تۆ خۆت لەخۆت گوڕدی. بۆمبەکە سڵاوت دەدات | You played yourself. The bomb says hi 👋💥",
    "💥 **BOOM!** ئەوەی هەڵبژاردیت بۆمبەکەت بوو بە تەواوی 🪦",
    "🧨 **BOOM!** ژمارەی {bomb} ناویت تێیدا نووسرابوو 😂",
]

SAFE_MESSAGES = [
    "✅ **سەلامەتە! | Safe!** فوو... {number} بۆمب نەبوو. بەختەوار بوویت 😅",
    "😮‍💨 **سەلامەتە! | Safe!** نزیک بوو... {number} پاکە! بەردەوام بە!",
    "🟢 **سەلامەتە! | Safe!** {number} سەلامەتە. بەڵام بۆمبەکە هێشتا لەوێیە 👀",
    "😅 **ووه!** {number} مایەوە! {remaining} ژمارەی تر...",
    "✨ **بۆمب نییە ئێرە! | No bomb here!** {number} سەلامەتە. زیادە متمانە مەبە 😏",
]

WIN_MESSAGES = [
    "🏆 **بردیت! | YOU WIN!** تۆ لە بۆمبی ژمارەی {bomb} فرییت! بەتوانا! 🎉",
    "🎉 **بەختەوار! | WINNER!** هەموو ژمارەکانت بە سەلامەتی تێپەڕاند! بۆمبەکە {bomb} بوو!",
    "👑 **شامپیۆن! | CHAMPION!** هەموو ژمارەکانت دابەزاند و مایتەوە! بۆمبەکە {bomb} بوو!",
    "🥇 **ناباوەڕ! | INCREDIBLE!** تۆ یاری بۆمب بردیت! شاراوە لە {bomb} بوو. GG EZ! 😎",
]


def build_bomb_grid(safe_picks, remaining):
    grid = ""
    for n in range(1, 11):
        if n in safe_picks:
            grid += f"~~`{n}`~~ "
        elif n in remaining:
            grid += f"`{n}` "
    return grid.strip()


@bot.command(name="td")
async def truth_or_dare(ctx):
    """Start a 1v1 Truth or Dare game. | یارییەکی ١ بەرامبەر ١ راستی یان جوریمەی دەستپێ بکە."""
    cid = ctx.channel.id

    if cid in td_sessions:
        await ctx.send(
            "⚠️ هەر یارییەکی Truth or Dare چالاک هەیە لەم کەناڵەدا! | "
            "There\'s already an active Truth or Dare game in this channel! Wait for it to finish.",
            delete_after=10
        )
        return

    session = TDSession(ctx.author.id, cid)
    td_sessions[cid] = session

    view  = TDLobbyView(cid, ctx.author.id)
    embed = _td_lobby_embed(ctx.author, "waiting")
    lobby_msg = await ctx.send(embed=embed, view=view)
    session.lobby_msg = lobby_msg

    try:
        await ctx.message.delete()
    except Exception:
        pass

# ─── $tdstop — Force stop a Truth or Dare game ────────────────────────────────
@bot.command(name="tdstop")
@commands.has_permissions(manage_messages=True)
async def td_stop(ctx):
    """Force-stop a Truth or Dare game in this channel. | یارییەکی Truth or Dare لەم کەناڵەدا بوەستێنە."""
    cid = ctx.channel.id
    if cid not in td_sessions:
        await ctx.send(
            "❌ هیچ یارییەکی چالاکی Truth or Dare نییە لەم کەناڵەدا. | "
            "No active Truth or Dare game in this channel.",
            delete_after=8
        )
        return
    td_sessions.pop(cid, None)
    embed = discord.Embed(
        title="🛑 یاری هەڵوەشایەوە | Game Stopped",
        description=(
            f"یارییەکی Truth or Dare بە هێزی لەلایەن {ctx.author.mention} وەستاندرا.\n"
            f"The Truth or Dare game was force-stopped by {ctx.author.mention}."
        ),
        color=0xEF4444,
    )
    await ctx.send(embed=embed)
    try:
        await ctx.message.delete()
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────────────
# --- AMONG THE SHADOWS ($shadow) — Social Deduction Game ---
# Min 4 players · Max 10 players
# Roles: Shadow 🕷️ | Detective 🔍 | Medic 💉 | Civilian 👤
# ─────────────────────────────────────────────────────────────────────────────

SHADOW_ROLES = {
    "SHADOW": {
        "name": "Shadow | سێبەر",
        "emoji": "🕷️",
        "color": 0x1A1A2E,
        "desc_en": "You are a **Shadow**. Each night, choose a player to **eliminate**. Blend in during the day and avoid being voted out!",
        "desc_ku": "تۆ **سێبەرێک**ی. هەر شەوێک یەک یاریزان **دەرببە**. ڕۆژانە خۆت بشارەوە و هەوڵبدە دەنگ لەبەرامبەرت نەدرێت!",
        "team": "shadows",
    },
    "DETECTIVE": {
        "name": "Detective | کارئاگا",
        "emoji": "🔍",
        "color": 0x1E40AF,
        "desc_en": "You are the **Detective**. Each night, investigate one player to learn if they are a Shadow.",
        "desc_ku": "تۆ **کارئاگا**یی. هەر شەوێک یەک یاریزان لێبکۆڵەرەوە تا بزانیت سێبەرن یان نا.",
        "team": "town",
    },
    "MEDIC": {
        "name": "Medic | پزیشک",
        "emoji": "💉",
        "color": 0x166534,
        "desc_en": "You are the **Medic**. Each night, protect one player from elimination. You can protect yourself once per game.",
        "desc_ku": "تۆ **پزیشک**ی. هەر شەوێک یەک یاریزان بپارێزە. دەتوانیت خۆت یەک جار بپارێزیت لە یاری.",
        "team": "town",
    },
    "CIVILIAN": {
        "name": "Civilian | باژێرگەر",
        "emoji": "👤",
        "color": 0x78716C,
        "desc_en": "You are a **Civilian**. No special power — but your vote counts! Find and eliminate the Shadows.",
        "desc_ku": "تۆ **باژێرگەر**ی. هیچ تایبەتمەندییەکی تایبەتت نییە، بەڵام دەنگەکەت گرنگە! سێبەرەکان بدۆزەرەوە.",
        "team": "town",
    },
}

shadow_sessions = {}   # channel_id -> ShadowSession


class ShadowSession:
    def __init__(self, host_id: int, channel_id: int, guild_id: int):
        self.host_id      = host_id
        self.channel_id   = channel_id
        self.guild_id     = guild_id
        self.state        = "lobby"      # lobby|night|day_discussion|day_vote|ended
        self.players      = {}           # uid -> {"alive": bool}
        self.role_map     = {}           # uid -> role key
        self.phase        = 0
        self.night_actions = {}          # role_key -> target_uid
        self.votes        = {}           # voter_uid -> target_uid
        self.elim_log     = []           # [{"uid", "phase", "by"}]
        self.medic_self_used = False
        self.lobby_msg    = None

    def alive_players(self):
        return [uid for uid, p in self.players.items() if p["alive"]]

    def shadows_alive(self):
        return [uid for uid in self.alive_players() if self.role_map.get(uid) == "SHADOW"]

    def town_alive(self):
        return [uid for uid in self.alive_players() if self.role_map.get(uid) != "SHADOW"]

    def check_win(self):
        s = len(self.shadows_alive())
        t = len(self.town_alive())
        if s == 0:
            return "town"
        if s >= t:
            return "shadows"
        return None

    def assign_roles(self):
        pids = list(self.players.keys())
        random.shuffle(pids)
        n = len(pids)
        shadow_count = 1 if n <= 6 else 2
        i = 0
        for _ in range(shadow_count):
            self.role_map[pids[i]] = "SHADOW"; i += 1
        self.role_map[pids[i]] = "DETECTIVE"; i += 1
        self.role_map[pids[i]] = "MEDIC";     i += 1
        while i < n:
            self.role_map[pids[i]] = "CIVILIAN"; i += 1


# ── Embed builders ────────────────────────────────────────────────────────────

def _sh_lobby_embed(session: ShadowSession, enabled: bool) -> discord.Embed:
    player_list = "\n".join(f"• <@{uid}>" for uid in session.players) or "*هیچ یاریزانێک هێشتا نییە | No players yet...*"
    count = len(session.players)
    embed = discord.Embed(
        title="🌑 لەنێو سێبەرەکان | Among the Shadows",
        description=(
            "> *لەم شارەدا تاریکی لەنێو بێگوناهەکان شاردەوەت...*\n"
            "> *In this town, darkness hides amongst the innocent...*\n\n"
            "یارییەکی کۆمەڵایەتی بۆ **خاپووریکردن، لێکۆڵینەوە و مانەوە.**\n"
            "A social deduction game of **deception, deduction & survival.**\n\n"
            "**ڕۆڵەکان | Roles:**\n"
            "🕷️ **سێبەر | Shadow** — شەوانە یاریزان دەکوژێت\n"
            "🔍 **کارئاگا | Detective** — هەر شەوێک یەک یاریزان لێدەکۆڵێتەوە\n"
            "💉 **پزیشک | Medic** — هەر شەوێک یەک یاریزان دەپارێزێت\n"
            "👤 **باژێرگەر | Civilian** — ڕۆژانە دەنگ دەدات بۆ دەرکردنی گومانلێکراوان\n\n"
            f"**یاریزانان ({count}/10) | Players ({count}/10):**\n{player_list}"
        ),
        color=0x0F0F1A,
    )
    embed.add_field(name="📌 کەمترین یاریزان | Min Players", value="4", inline=True)
    embed.add_field(name="👑 میواندار | Host", value=f"<@{session.host_id}>", inline=True)
    embed.set_footer(text="بەشداربە بزووە ← میوانداری دەست بکات کە ٤+ یاریزان هاتن | Press Join → Host starts when 4+ players ready")
    embed.timestamp = datetime.datetime.utcnow()
    return embed


def _sh_night_embed(phase: int) -> discord.Embed:
    embed = discord.Embed(
        title=f"🌑 شەوی {phase} دەهاتە خوارەوە | Night {phase} Falls...",
        description=(
            "> *شارەکە بێدەنگ دەبێت. شتێک لە تاریکییەکەدا دەجوڵێت...*\n"
            "> *The town goes quiet. Something stirs in the dark...*\n\n"
            "**پەیامی تایبەتەکانت بپشکنە! | Check your DMs!** ڕۆڵە تایبەتەکان دەبێت ئێستا کار بکەن:\n"
            "🕷️ سێبەر | Shadow → ئەوی هەڵبژێرە کە دەرببەیت | Choose who to eliminate\n"
            "🔍 کارئاگا | Detective → یەکێک لێبکۆڵەرەوە | Investigate someone\n"
            "💉 پزیشک | Medic → یەکێک بپارێزە | Protect someone\n\n"
            "*باژێرگەرەکان چاوەڕوان دەبن... | Civilians wait patiently...*"
        ),
        color=0x0F0F1A,
    )
    embed.set_footer(text="قۆناغی شەو — ٩٠ چرکە | Night phase — 90 seconds")
    embed.timestamp = datetime.datetime.utcnow()
    return embed


def _sh_day_embed(phase: int, events: str) -> discord.Embed:
    embed = discord.Embed(
        title=f"☀️ ڕۆژی {phase} — شار شیان دەبێتەوە | Day {phase} — The Town Awakens",
        description=(
            f"> *بەیانی بوو، شار چاودێری ئەو شەوەی دەکات...*\n"
            f"> *As the sun rises, the town gathers to share what they know...*\n\n"
            f"**بۆچوونەکانی شەوی ڕابردوو | Last Night's Events:**\n{events}\n\n"
            f"**قۆناغی گفتوگۆ | Discussion Phase:** ٦٠ چرکەتان هەیە بۆ گفتوگۆ | 60 seconds to discuss.\n"
            f"دواتر دەنگدان دەستپێدەکات! | Then voting begins!"
        ),
        color=0xF59E0B,
    )
    embed.set_footer(text="ئێستا گفتوگۆ بکە! دەنگدان دەستپێدەکات زوو | Discuss now! Voting starts soon.")
    embed.timestamp = datetime.datetime.utcnow()
    return embed


def _sh_vote_embed(phase: int, alive: list) -> discord.Embed:
    player_list = "\n".join(f"• <@{uid}>" for uid in alive)
    embed = discord.Embed(
        title=f"🗳️ ڕۆژی {phase} — دەنگ بدە بۆ دەرکردن | Day {phase} — Vote to Eliminate",
        description=(
            "> *شار دەبێت بڕیار بدات. یەکێک دەرکرابێت.*\n"
            "> *The town must decide. One will be cast out.*\n\n"
            "هەر یاریزانی زیندوو **یەک دەنگی** هەیە | Each alive player gets **one vote**.\n"
            "زۆرترین دەنگ = دەرکراو | Most votes = eliminated.\n"
            "ئەگەر یەکسان بوو، **کەس دەرناکرێت** | Tie = **no one** eliminated.\n\n"
            f"**یاریزانانی زیندوو | Alive Players:**\n{player_list}"
        ),
        color=0xDC2626,
    )
    embed.set_footer(text="لیستەکە بەکاربهێنە بۆ دەنگدان | Use the dropdown to vote • 60 seconds")
    embed.timestamp = datetime.datetime.utcnow()
    return embed


def _sh_win_embed(winner: str, session: ShadowSession) -> discord.Embed:
    is_town = winner == "town"
    shadows_were = ", ".join(f"<@{uid}>" for uid, r in session.role_map.items() if r == "SHADOW") or "کەس | None"
    log_lines = "\n".join(f"• <@{e['uid']}> — شەو/ڕۆژ {e['phase']} ({e['by']})" for e in session.elim_log) or "هیچکەس دەرنەکرا | No one was eliminated."
    embed = discord.Embed(
        title="☀️ شار بردی! | The Town Wins!" if is_town else "🕷️ سێبەرەکان بردیان! | The Shadows Win!",
        description=(
            ("> *ڕووناکی گەڕایەوە. سێبەرەکان شکستیان خوارد!*\n> *Light has returned. The shadows are defeated!*\n\nشار هەموو سێبەرەکانی دۆزیەوە!\nThe town successfully rooted out all the Shadows!")
            if is_town else
            ("> *تاریکی هەموو شتی لەخۆ گرت. سێبەرەکان سەروەریان کرد.*\n> *Darkness consumes all. The Shadows reign.*\n\nسێبەرەکان شار خستەژێر دەستیان!\nThe Shadows have taken over the town!")
        ),
        color=0x22C55E if is_town else 0x1A1A2E,
    )
    embed.add_field(name="🕷️ سێبەرەکان | Shadows Were", value=shadows_were, inline=False)
    embed.add_field(name="📜 لۆگی دەرکراوان | Elimination Log", value=log_lines, inline=False)
    embed.set_footer(text="سوپاس بۆ یاریکردن! | Thanks for playing! Use $shadow for a new game.")
    embed.timestamp = datetime.datetime.utcnow()
    return embed


# ── Night DM Views ─────────────────────────────────────────────────────────────

class ShadowKillView(discord.ui.View):
    def __init__(self, session: ShadowSession, targets: list):
        super().__init__(timeout=90)
        self.session = session
        options = [discord.SelectOption(label=f"یاریزان ...{uid[-4:]} | Player ...{uid[-4:]}", value=uid) for uid in targets]
        sel = discord.ui.Select(placeholder="🕷️ قوربانییەکە هەڵبژێرە | Choose victim...", options=options, custom_id="sh_kill")
        sel.callback = self._cb
        self.add_item(sel)

    async def _cb(self, interaction: discord.Interaction):
        if self.session.state != "night":
            await interaction.response.send_message("❌ ئێستا شەو نییە | Not night phase.", ephemeral=True)
            return
        self.session.night_actions["SHADOW"] = interaction.data["values"][0]
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(
            embed=discord.Embed(title="🕷️ ئامانج تەسبیت کرا | Target Locked", description="هەڵبژاردنەکەت تۆمار کرا. چاوەڕوانی بەیانی بکە | Your choice has been recorded. Wait for morning...", color=0x1A1A2E),
            view=self,
        )


class ShadowInvestigateView(discord.ui.View):
    def __init__(self, session: ShadowSession, targets: list):
        super().__init__(timeout=90)
        self.session = session
        options = [discord.SelectOption(label=f"یاریزان ...{uid[-4:]} | Player ...{uid[-4:]}", value=uid) for uid in targets]
        sel = discord.ui.Select(placeholder="🔍 یەکێک هەڵبژێرە بۆ لێکۆڵینەوە | Choose to investigate...", options=options, custom_id="sh_invest")
        sel.callback = self._cb
        self.add_item(sel)

    async def _cb(self, interaction: discord.Interaction):
        if self.session.state != "night":
            await interaction.response.send_message("❌ ئێستا شەو نییە | Not night phase.", ephemeral=True)
            return
        self.session.night_actions["DETECTIVE"] = interaction.data["values"][0]
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(
            embed=discord.Embed(title="🔍 لێکۆڵینەوە...", description="ئەنجامەکان لە بەیانیدا دەگەیشتنەت | You'll receive results at dawn.", color=0x1E40AF),
            view=self,
        )


class ShadowProtectView(discord.ui.View):
    def __init__(self, session: ShadowSession, targets: list):
        super().__init__(timeout=90)
        self.session = session
        options = [discord.SelectOption(label=f"یاریزان ...{uid[-4:]} | Player ...{uid[-4:]}", value=uid) for uid in targets]
        sel = discord.ui.Select(placeholder="💉 یەکێک هەڵبژێرە بۆ پاراستن | Choose to protect...", options=options, custom_id="sh_protect")
        sel.callback = self._cb
        self.add_item(sel)

    async def _cb(self, interaction: discord.Interaction):
        if self.session.state != "night":
            await interaction.response.send_message("❌ ئێستا شەو نییە | Not night phase.", ephemeral=True)
            return
        uid = interaction.data["values"][0]
        if uid == str(interaction.user.id):
            self.session.medic_self_used = True
        self.session.night_actions["MEDIC"] = uid
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(
            embed=discord.Embed(title="💉 پاراستن دیاری کرا | Protection Set", description="ئەو شەوە لەژێر چاودێرییەتدایە | They're under your watch tonight.", color=0x166534),
            view=self,
        )


class ShadowVoteView(discord.ui.View):
    def __init__(self, session: ShadowSession, voter_id: int, targets: list):
        super().__init__(timeout=60)
        self.session  = session
        self.voter_id = voter_id
        options = [discord.SelectOption(label=f"یاریزان ...{uid[-4:]} | Player ...{uid[-4:]}", value=uid) for uid in targets]
        sel = discord.ui.Select(placeholder="🗳️ ئەوی هەڵبژێرە کە دەرببەیت | Choose who to eliminate...", options=options, custom_id="sh_vote")
        sel.callback = self._cb
        self.add_item(sel)

    async def _cb(self, interaction: discord.Interaction):
        if self.session.state != "day_vote":
            await interaction.response.send_message("❌ دەنگدان چالاک نییە | Voting is not active.", ephemeral=True)
            return
        uid = str(interaction.user.id)
        if not self.session.players.get(uid, {}).get("alive"):
            await interaction.response.send_message("❌ تۆ دەرکرایت، دەنگت نییە | You are eliminated and cannot vote.", ephemeral=True)
            return
        self.session.votes[uid] = interaction.data["values"][0]
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(
            embed=discord.Embed(title="🗳️ دەنگەکەت دراو | Vote Cast", description="دەنگەکەت تۆمار کرا | Your vote has been recorded.", color=0xDC2626),
            view=self,
        )


# ── Lobby View ─────────────────────────────────────────────────────────────────

class ShadowLobbyView(discord.ui.View):
    def __init__(self, session: ShadowSession):
        super().__init__(timeout=300)
        self.session = session

    def _enough(self):
        return len(self.session.players) >= 4

    @discord.ui.button(label="🌑 بەشداربە | Join Game", style=discord.ButtonStyle.secondary, custom_id="shadow_join")
    async def join_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        s = self.session
        if s.state != "lobby":
            await interaction.response.send_message("❌ لۆبی چالاک نییە | No active lobby.", ephemeral=True); return
        uid = str(interaction.user.id)
        if uid in s.players:
            await interaction.response.send_message("✅ پێشتر بەشداربووی | You're already in!", ephemeral=True); return
        if len(s.players) >= 10:
            await interaction.response.send_message("❌ یاری پڕ بووە | Game is full!", ephemeral=True); return
        s.players[uid] = {"alive": True}
        self.start_btn.disabled = not self._enough()
        await interaction.response.edit_message(embed=_sh_lobby_embed(s, self._enough()), view=self)

    @discord.ui.button(label="🚪 دەربچوون | Leave", style=discord.ButtonStyle.danger, custom_id="shadow_leave")
    async def leave_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        s = self.session
        if s.state != "lobby":
            await interaction.response.send_message("❌ لۆبی نییە | No lobby to leave.", ephemeral=True); return
        uid = str(interaction.user.id)
        if uid not in s.players:
            await interaction.response.send_message("❌ تۆ لەم یاریەدا نیت | You're not in this game.", ephemeral=True); return
        if interaction.user.id == s.host_id:
            await interaction.response.send_message("❌ میوانداری نەتوانیت بچیت | Host can't leave. Cancel instead.", ephemeral=True); return
        del s.players[uid]
        self.start_btn.disabled = not self._enough()
        await interaction.response.edit_message(embed=_sh_lobby_embed(s, self._enough()), view=self)

    @discord.ui.button(label="▶️ دەستپێبکە | Start Game", style=discord.ButtonStyle.success, custom_id="shadow_start", disabled=True)
    async def start_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        s = self.session
        if s.state != "lobby":
            await interaction.response.send_message("❌ لۆبی نییە | No lobby.", ephemeral=True); return
        if interaction.user.id != s.host_id:
            await interaction.response.send_message("❌ تەنها میوانداری دەتوانێت دەستپێبکات | Only the host can start.", ephemeral=True); return
        if len(s.players) < 4:
            await interaction.response.send_message("❌ لانیکەم ٤ یاریزان پێویستە | Need at least 4 players!", ephemeral=True); return

        s.assign_roles()
        s.state = "night"
        s.phase = 1

        for child in self.children:
            child.disabled = True
        started_embed = _sh_lobby_embed(s, True)
        started_embed.description = "✅ یاری دەستپێکرد! پەیامی تایبەتەکانت بپشکنە بۆ ڕۆڵەکەت.\n✅ Game started! Check your DMs for your role."
        started_embed.color = 0x22C55E
        await interaction.response.edit_message(embed=started_embed, view=self)

        # DM roles
        for uid, role_key in s.role_map.items():
            rd = SHADOW_ROLES[role_key]
            try:
                member = await interaction.guild.fetch_member(int(uid))
                role_embed = discord.Embed(
                    title=f"{rd['emoji']} ڕۆڵەکەت | Your Role: {rd['name']}",
                    description=f"**کوردی:**\n{rd['desc_ku']}\n\n**English:**\n{rd['desc_en']}",
                    color=rd["color"],
                )
                role_embed.set_footer(text="ڕۆڵەکەت نهێنی بگرە! | Keep your role secret!")
                await member.send(embed=role_embed)
            except Exception:
                pass

        await interaction.channel.send(embed=_sh_night_embed(1))
        await _sh_send_night_dms(s, interaction.guild)
        bot.loop.create_task(_sh_night_timer(s, interaction.channel, interaction.guild))

    async def on_timeout(self):
        shadow_sessions.pop(self.session.channel_id, None)


# ── Night DM sender ────────────────────────────────────────────────────────────

async def _sh_send_night_dms(session: ShadowSession, guild: discord.Guild):
    for uid in session.alive_players():
        role_key = session.role_map.get(uid)
        try:
            member = await guild.fetch_member(int(uid))
            user   = member.user
            alive  = session.alive_players()

            if role_key == "SHADOW":
                targets = [t for t in alive if t != uid]
                if not targets:
                    continue
                shadows_other = [f"<@{s}>" for s in session.shadows_alive() if s != uid]
                embed = discord.Embed(
                    title="🕷️ سێبەر — ئامانجەکەت هەڵبژێرە | Shadow — Choose Your Target",
                    description=(
                        f"شەوی {session.phase}: یەک یاریزان هەڵبژێرە بۆ **دەرکردن | eliminate**.\n"
                        f"سێبەرانی تر | Fellow shadows: {', '.join(shadows_other) if shadows_other else '*تەنها یی | You are alone.*'}"
                    ),
                    color=0x1A1A2E,
                )
                await user.send(embed=embed, view=ShadowKillView(session, targets))

            elif role_key == "DETECTIVE":
                targets = [t for t in alive if t != uid]
                if not targets:
                    continue
                embed = discord.Embed(
                    title="🔍 کارئاگا — لێبکۆڵەرەوە | Detective — Investigate",
                    description=f"شەوی {session.phase}: یەک یاریزان هەڵبژێرە بۆ **لێکۆڵینەوە | investigate**. بزانیت سێبەرن یان نا.",
                    color=0x1E40AF,
                )
                await user.send(embed=embed, view=ShadowInvestigateView(session, targets))

            elif role_key == "MEDIC":
                targets = [t for t in alive if t != uid] if session.medic_self_used else alive
                if not targets:
                    continue
                self_note = "\n*(دەتوانیت خۆت یەک جار بپارێزیت | You may protect yourself once.)*" if not session.medic_self_used else ""
                embed = discord.Embed(
                    title="💉 پزیشک — یەکێک بپارێزە | Medic — Protect Someone",
                    description=f"شەوی {session.phase}: یەک یاریزان هەڵبژێرە بۆ **پاراستن | protect** ئەو شەوە.{self_note}",
                    color=0x166534,
                )
                await user.send(embed=embed, view=ShadowProtectView(session, targets))

            else:
                embed = discord.Embed(
                    title="👤 باژێرگەر — چاوەڕوان بە | Civilian — Rest...",
                    description=f"شەوی {session.phase}: هیچ تایبەتمەندییەکی تایبەتت نییە. چاوەڕوانی بەیانی بکە و ڕۆژانە سێبەرەکان بدۆزەرەوە!\nNight {session.phase}: You have no special ability. Wait for morning and find the Shadows!",
                    color=0x78716C,
                )
                await user.send(embed=embed)
        except Exception:
            pass


# ── Night timer & resolution ───────────────────────────────────────────────────

async def _sh_night_timer(session: ShadowSession, channel, guild: discord.Guild):
    await asyncio.sleep(90)
    if session.state == "night":
        await _sh_resolve_night(session, channel, guild)


async def _sh_resolve_night(session: ShadowSession, channel, guild: discord.Guild):
    kill     = session.night_actions.get("SHADOW")
    protect  = session.night_actions.get("MEDIC")
    invest   = session.night_actions.get("DETECTIVE")
    events   = ""

    if protect and protect == kill:
        events += "💉 *یەک کەس لە کاتی گونجاودا پارێزرا... | Someone was protected in the nick of time...*\n"

    if kill and kill != protect:
        session.players[kill]["alive"] = False
        session.elim_log.append({"uid": kill, "phase": session.phase, "by": "Shadow | سێبەر"})
        events += f"🪦 **<@{kill}>** بەیانی دۆزرایەوە کەکرا... | was found eliminated at dawn...\n"
    elif not kill:
        events += "😌 *شەوەکە ئارام تێپەڕی. کەس دەرنەکرا. | The night passed peacefully. No one was eliminated.*\n"

    if invest:
        role_key = session.role_map.get(invest)
        is_shadow = role_key == "SHADOW"
        det_id = next((uid for uid, r in session.role_map.items() if r == "DETECTIVE"), None)
        if det_id:
            try:
                det_member = await guild.fetch_member(int(det_id))
                color = 0xEF4444 if is_shadow else 0x22C55E
                label = "🕷️ **سێبەرە! | A SHADOW!**" if is_shadow else "✅ **سێبەر نییە | Not a Shadow.**"
                await det_member.send(embed=discord.Embed(
                    title="🔍 ئەنجامی لێکۆڵینەوە | Investigation Result",
                    description=f"یاریزان `...{invest[-4:]}` {label}",
                    color=color,
                ))
            except Exception:
                pass

    session.night_actions = {}
    session.state = "day_discussion"
    session.phase += 1

    win = session.check_win()
    if win:
        await _sh_end_game(session, channel, win)
        return

    await _sh_start_day(session, channel, guild, events or "*هیچ ڕووی نەدا شەوی ڕابردوو | Nothing happened last night.*")


async def _sh_start_day(session: ShadowSession, channel, guild: discord.Guild, events: str):
    alive_mentions = " ".join(f"<@{uid}>" for uid in session.alive_players())
    await channel.send(content=alive_mentions, embed=_sh_day_embed(session.phase, events))
    await asyncio.sleep(60)
    if session.state != "ended":
        await _sh_start_voting(session, channel, guild)


async def _sh_start_voting(session: ShadowSession, channel, guild: discord.Guild):
    if session.state == "ended":
        return
    session.state = "day_vote"
    session.votes = {}
    alive = session.alive_players()
    await channel.send(embed=_sh_vote_embed(session.phase, alive))

    for voter_id in alive:
        targets = [t for t in alive if t != voter_id]
        if not targets:
            continue
        try:
            member = await guild.fetch_member(int(voter_id))
            vote_embed = discord.Embed(
                title="🗳️ دەنگەکەت بدە | Cast Your Vote",
                description="ئەوی هەڵبژێرە کە بەباوەڕت سێبەرە | Choose who you think is a Shadow!",
                color=0xDC2626,
            )
            await member.send(embed=vote_embed, view=ShadowVoteView(session, voter_id, targets))
        except Exception:
            pass

    await asyncio.sleep(60)
    if session.state != "ended":
        await _sh_resolve_votes(session, channel, guild)


async def _sh_resolve_votes(session: ShadowSession, channel, guild: discord.Guild):
    if session.state == "ended":
        return
    tally = {}
    for target in session.votes.values():
        tally[target] = tally.get(target, 0) + 1

    eliminated = None
    max_votes   = 0
    tie         = False
    for uid, count in tally.items():
        if count > max_votes:
            max_votes = count; eliminated = uid; tie = False
        elif count == max_votes:
            tie = True

    if tie or not eliminated:
        await channel.send(embed=discord.Embed(
            title="🤝 یەکسانە! | It's a Tie!",
            description="> *شار نەیتوانی یەک بڕیار بدات. ئەمڕۆ کەس دەرنەکرا.*\n> *The town couldn't agree. No one is eliminated today.*\n\nشەو نزیکدەبێتەوە... | The night approaches...",
            color=0x6B7280,
        ))
    else:
        session.players[eliminated]["alive"] = False
        session.elim_log.append({"uid": eliminated, "phase": session.phase, "by": "Town Vote | دەنگی شار"})
        role_key = session.role_map.get(eliminated, "CIVILIAN")
        rd = SHADOW_ROLES[role_key]
        await channel.send(embed=discord.Embed(
            title="⚖️ شار قسەی کرد | The Town Has Spoken",
            description=f"> *خەڵک سەری بۆ ئەوەی هاتن...*\n\n<@{eliminated}> دەرکرا.\nThey were a **{rd['emoji']} {rd['name']}**.",
            color=0xDC2626,
        ))

    win = session.check_win()
    if win:
        await _sh_end_game(session, channel, win)
        return

    session.state = "night"
    await channel.send(embed=_sh_night_embed(session.phase + 1))
    await _sh_send_night_dms(session, guild)
    bot.loop.create_task(_sh_night_timer(session, channel, guild))


async def _sh_end_game(session: ShadowSession, channel, winner: str):
    session.state = "ended"
    shadow_sessions.pop(session.channel_id, None)
    await channel.send(embed=_sh_win_embed(winner, session))


# ── Commands ───────────────────────────────────────────────────────────────────

@bot.command(name="shadow")
async def shadow_cmd(ctx):
    """Start an Among the Shadows game (4-10 players). | یارییەکی لەنێو سێبەرەکان (٤-١٠ یاریزان)."""
    cid = ctx.channel.id
    if cid in shadow_sessions:
        await ctx.send(
            "⚠️ هەر یارییەکی لەنێو سێبەرەکان چالاکە لەم کەناڵەدا | "
            "There's already an active Among the Shadows game here!",
            delete_after=8
        )
        return

    session = ShadowSession(ctx.author.id, cid, ctx.guild.id)
    session.players[str(ctx.author.id)] = {"alive": True}
    shadow_sessions[cid] = session

    view = ShadowLobbyView(session)
    msg  = await ctx.send(embed=_sh_lobby_embed(session, False), view=view)
    session.lobby_msg = msg
    try:
        await ctx.message.delete()
    except Exception:
        pass


@bot.command(name="shadowstop")
@commands.has_permissions(manage_messages=True)
async def shadow_stop(ctx):
    """Force-stop an Among the Shadows game. | یارییەکی لەنێو سێبەرەکان بوەستێنە."""
    cid = ctx.channel.id
    if cid not in shadow_sessions:
        await ctx.send("❌ هیچ یارییەکی چالاکی لەنێو سێبەرەکان نییە لەم کەناڵەدا | No active Among the Shadows game here.", delete_after=8)
        return
    shadow_sessions.pop(cid, None)
    embed = discord.Embed(
        title="🛑 یاری هەڵوەشایەوە | Game Stopped",
        description=f"یارییەکی لەنێو سێبەرەکان بە هێزی لەلایەن {ctx.author.mention} وەستاندرا.\nThe Among the Shadows game was force-stopped by {ctx.author.mention}.",
        color=0xEF4444,
    )
    await ctx.send(embed=embed)
    try:
        await ctx.message.delete()
    except Exception:
        pass

# ─────────────────────────────────────────────────────────────────────────────
# --- RUSSIAN ROULETTE: LAST ONE STANDING ($roulette) ---
# ─────────────────────────────────────────────────────────────────────────────

RR_SUSPENSE = [
    "🎰 سیلیندەرەکە دەسوڕێتەوە... | The cylinder spins...",
    "😰 مەرمیلکەکە دەکێشرێتەوە... | The hammer pulls back...",
    "🤫 ژوورەکە تەواو بێدەنگ دەبێت... | The room goes dead silent...",
    "💀 دانەیەک ئارەق لە ڕووخساریان دادەڕژێت... | A bead of sweat rolls down their face...",
    "🫀 دڵیان بەتیزی دەلێت... | Their heart is pounding...",
    "🌀 کلیک... کلیک... کلیک... | Click... click... click...",
    "😶 چاویان دادەخەن... | They close their eyes...",
    "🎲 چارەنووس بڕیاری دەدات... | Fate decides...",
    "🕯️ مووچاکە دەلەرزێت... | The candle flickers...",
    "⏳ کات هێواش دەبێتەوە... | Time slows down...",
]

RR_SURVIVED = [
    "💨 **کلیک.** هیچ. هەواڵێکی سووک دەردەکەن. هێشتا زیندوون. | **CLICK.** Nothing. They exhale slowly. Still alive.",
    "😮‍💨 **کلیک.** مەرمیلکەی بەتاڵ. کۆمەڵەکە ئەلقەیان دەبێت. | **CLICK.** Empty chamber. The crowd gasps.",
    "🫡 **کلیک.** خەتا کرد. خودا دلۆڤانی بوو... ئەمجار. | **CLICK.** A miss. The gods were merciful... this time.",
    "😅 **کلیک.** بێدەنگی. مانەوی — بە زۆر. | **CLICK.** Silence. They survived — barely.",
    "🤍 **کلیک.** مەرمیلکەکە لەسەر هیچ دەکەوێت. گیانێکی خۆشبەخت. | **CLICK.** The hammer falls on nothing. Lucky soul.",
    "🫶 **کلیک.** بەتاڵ. قاچیان هێندەک لەبار دەبێت لە ئارامیەوە. | **CLICK.** Empty. Their knees nearly buckle with relief.",
]

RR_ELIMINATED = [
    "💥 **بانگ!!** مەرمیلکەکە پڕ بوو. دەریان کرد. | **BANG!!** The chamber was loaded. They're out.",
    "🔥 **بانگ!!** چوون. هەر بەو شێوەیە. | **BANG!!** Gone. Just like that.",
    "😵 **بانگ!!** گولولەکە نیشانەکەی دۆزیەوە. دەریان کرد. | **BANG!!** The bullet found its mark. Eliminated.",
    "💀 **بانگ!!** ئەمشەو بەخشینی نییە. تەواو بوون. | **BANG!!** No mercy tonight. They're done.",
    "⚡ **بانگ!!** مەترسیەکە لەدایان گەیشت. | **BANG!!** The odds finally caught up with them.",
    "🩸 **بانگ!!** ئەوەی ماوەتەوە کەمتر بووە... | **BANG!!** And then there were fewer...",
]

RR_WIN_MSGS = [
    "لە دوژمنی و ژیانی دووپاتەوە چوو. | walked through hell and came out the other side.",
    "ڕووبەڕووی مەرگ بوو و ئاخری چاوی پووچ کرد. | stared death in the face and blinked last.",
    "دوایین کەسی نەفەسەکێشەرە. ڕێز. | is the last one breathing. Respect.",
    "لەسەر هەموو کێشەیەک مانەوی. بەلاتوانرا. | survived every pull. Unbelievable.",
    "یان خۆشبەختترینە یان جەسورترین. هەر شێوەیەک — براوە. | is either the luckiest or the bravest. Either way — winner.",
]

roulette_sessions = {}   # channel_id -> RouletteGame


class RouletteGame:
    def __init__(self, host_id: int, channel_id: int):
        self.host_id      = host_id
        self.channel_id   = channel_id
        self.state        = "lobby"      # lobby | playing | ended
        self.players      = []           # ordered list of str user ids
        self.alive        = set()        # alive str user ids
        self.current_idx  = 0
        self.round        = 1
        self.chamber      = 0
        self.bullet_pos   = 0
        self.pulls        = 0
        self.stats        = {}           # uid -> {"survived": N, "pulls": N}
        self.pull_lock    = False        # prevents double-processing a pull

    def alive_players(self):
        return [uid for uid in self.players if uid in self.alive]

    def current_player(self):
        alive = self.alive_players()
        if not alive:
            return None
        return alive[self.current_idx % len(alive)]

    def advance_turn(self):
        alive = self.alive_players()
        if alive:
            self.current_idx = (self.current_idx + 1) % len(alive)

    def spin_cylinder(self):
        self.bullet_pos = random.randint(0, 5)
        self.chamber    = 0
        self.pulls      = 0

    def pull_trigger(self):
        hit = (self.chamber == self.bullet_pos)
        self.chamber = (self.chamber + 1) % 6
        self.pulls  += 1
        if self.pulls % 6 == 0:
            self.spin_cylinder()
        return hit

    def chamber_display(self):
        checked = self.pulls % 6
        return " ".join("⬛" if i < checked else "⬜" for i in range(6))


def _rr_lobby_embed(game: RouletteGame) -> discord.Embed:
    player_list = "\n".join(f"{i+1}. <@{uid}>" for i, uid in enumerate(game.players)) or "*هیچ یاریزانێک هێشتا نییە | No players yet...*"
    enough = len(game.players) >= 2
    embed = discord.Embed(
        title="🔫 ڕووسی ڕووڵێت: دوایین کەسی مانەوە | Russian Roulette: Last One Standing",
        description=(
            "> *یەک چەک. یەک گولولە. چەند کەسی شێتی ئامادەی کێشانی ماشەیە.*\n"
            "> *One gun. One bullet. Multiple fools willing to pull the trigger.*\n\n"
            "**چۆن کار دەکات | How it works:**\n"
            "• یاریزانان لە خوارەوەی خۆشکلاوی دانیشتووەتەوە و نۆبەت بەنۆبەت ماشە دەکێشن | Players sit in a circle and take turns pulling the trigger\n"
            "• ڕیڤۆڵڤەرەکە **٦ مەرمیلکەی** هەیە — یەکێکیان گولولە هەیە | The revolver has **6 chambers** — one has a bullet\n"
            "• **کلیک** = مانەوە. **بانگ** = دەرکردن | **CLICK** = survived. **BANG** = eliminated\n"
            "• سیلیندەرەکە دوای هەر ٦ کێشان دەسوڕێتەوە | The cylinder re-spins every full rotation\n"
            "• دوایین کەسی زیندووی ببرێت 🏆 | Last one alive wins 🏆\n\n"
            f"**یاریزانان ({len(game.players)}/8) | Players ({len(game.players)}/8):**\n{player_list}"
        ),
        color=0x1A1A1A,
    )
    embed.add_field(name="👑 میوانداری | Host", value=f"<@{game.host_id}>", inline=True)
    embed.add_field(name="⚙️ کەمترین | Min", value="2", inline=True)
    embed.set_footer(text="ئامادەیە! میوانداری دەتوانێت دەستپێبکات | Ready! Host can start." if enough else "چاوەڕوانی یاریزانی زیاتر... | Waiting for more players...")
    embed.timestamp = datetime.datetime.utcnow()
    return embed


def _rr_turn_embed(game: RouletteGame, current_id: str) -> discord.Embed:
    alive = game.alive_players()
    remaining = 6 - (game.pulls % 6)
    alive_list = "\n".join(f"• <@{uid}>" for uid in alive)
    embed = discord.Embed(
        title=f"🔫 قۆناغی {game.round} — نۆبەتی تۆیە | Round {game.round} — It's your turn",
        description=(
            "> *ڕیڤۆڵڤەرەکە لەسەر میزەکەدا دەسوڕێت...*\n"
            "> *The revolver slides across the table...*\n\n"
            f"<@{current_id}>، نۆبەتی تۆیە. **ماشەی بکێشە | Pull the trigger.**\n\n"
            f"**مەرمیلکەکان | Cylinder:** {game.chamber_display()}\n"
            f"**مەرمیلکەی ماوە ئەم سوڕانەدا | Chambers left:** {remaining}/6\n\n"
            f"**هێشتا زیندوون ({len(alive)}) | Still alive ({len(alive)}):**\n{alive_list}"
        ),
        color=0xDC2626,
    )
    embed.set_footer(text="٣٠ چرکەت هەیە — ئەگەر نەکێشیت خۆکارانە دەکێشرێت | 30 seconds to pull or you're auto-pulled!")
    embed.timestamp = datetime.datetime.utcnow()
    return embed


def _rr_win_embed(winner_id: str, game: RouletteGame) -> discord.Embed:
    log_lines = "\n".join(
        f"• <@{uid}> — {game.stats.get(uid, {}).get('survived', 0)} کێشانی سەلامەتی | pull(s) survived"
        for uid in game.players if uid not in game.alive
    ) or "*کەس دەرنەکرا؟! | No one was eliminated?!*"
    win_msg = random.choice(RR_WIN_MSGS)
    embed = discord.Embed(
        title="🏆 براوەمان هەیە! | We Have a Winner!",
        description=(
            f"<@{winner_id}> {win_msg}\n\n"
            f"**ئامارەکانی | Stats for** <@{winner_id}>: {game.stats.get(winner_id, {}).get('survived', 0)} کێشانی سەلامەتی | successful pull(s)\n\n"
            f"**ڕیزی دەرکراوان | Eliminated order:**\n{log_lines}"
        ),
        color=0xFFD700,
    )
    embed.set_footer(text="!roulette بەکاربهێنە بۆ یارییەکی نوێ | Use $roulette to start a new game.")
    embed.timestamp = datetime.datetime.utcnow()
    return embed


# ── Pull Trigger View ──────────────────────────────────────────────────────────

class RoulettePullView(discord.ui.View):
    def __init__(self, game: RouletteGame, channel):
        super().__init__(timeout=30)
        self.game    = game
        self.channel = channel

    @discord.ui.button(label="🔫 ماشە بکێشە | Pull the Trigger", style=discord.ButtonStyle.danger, custom_id="rr_pull")
    async def pull_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        uid = str(interaction.user.id)
        g   = self.game
        if g.state != "playing":
            await interaction.response.send_message("❌ یاری چالاک نییە | No active game.", ephemeral=True); return
        if uid != g.current_player():
            await interaction.response.send_message("❌ نۆبەتی تۆ نییە! | It's not your turn!", ephemeral=True); return
        if g.pull_lock:
            await interaction.response.send_message("❌ هێشتا کار دەکات... | Processing...", ephemeral=True); return
        g.pull_lock = True
        self.stop()
        for child in self.children:
            child.disabled = True
        try:
            await interaction.response.edit_message(view=self)
        except Exception:
            pass
        await _rr_process_pull(g, self.channel, uid)

    async def on_timeout(self):
        g = self.game
        if g.state != "playing" or g.pull_lock:
            return
        g.pull_lock = True
        uid = g.current_player()
        if uid is None:
            return
        try:
            await self.channel.send(content=f"⏰ <@{uid}> زیاتر کاتی بوو... چەکەکە خۆکارانە دەکێشرێت! | took too long... the gun goes off automatically!")
        except Exception:
            pass
        await _rr_process_pull(g, self.channel, uid)


# ── Lobby View ─────────────────────────────────────────────────────────────────

class RouletteLobbyView(discord.ui.View):
    def __init__(self, game: RouletteGame):
        super().__init__(timeout=180)
        self.game = game

    def _rebuild_start_btn(self):
        for child in self.children:
            if hasattr(child, "custom_id") and child.custom_id == "rr_start":
                child.disabled = len(self.game.players) < 2

    @discord.ui.button(label="🔫 بەشداربە | Join Game", style=discord.ButtonStyle.danger, custom_id="rr_join")
    async def join_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        g   = self.game
        uid = str(interaction.user.id)
        if g.state != "lobby":
            await interaction.response.send_message("❌ لۆبی چالاک نییە | No active lobby.", ephemeral=True); return
        if uid in g.players:
            await interaction.response.send_message("✅ پێشتر بەشداربووی | You're already in!", ephemeral=True); return
        if len(g.players) >= 8:
            await interaction.response.send_message("❌ یاری پڕ بووە (٨ زۆرترین) | Game is full (8 max)!", ephemeral=True); return
        g.players.append(uid)
        g.alive.add(uid)
        self._rebuild_start_btn()
        await interaction.response.edit_message(embed=_rr_lobby_embed(g), view=self)

    @discord.ui.button(label="🚪 دەربچوون | Leave", style=discord.ButtonStyle.secondary, custom_id="rr_leave")
    async def leave_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        g   = self.game
        uid = str(interaction.user.id)
        if g.state != "lobby":
            await interaction.response.send_message("❌ لۆبی نییە | No lobby to leave.", ephemeral=True); return
        if uid not in g.players:
            await interaction.response.send_message("❌ تۆ لەم یاریەدا نیت | You're not in this game.", ephemeral=True); return
        if int(uid) == g.host_id:
            await interaction.response.send_message("❌ میوانداری نەتوانیت بچێت | Host can't leave. Use $roulettestop.", ephemeral=True); return
        g.players.remove(uid)
        g.alive.discard(uid)
        self._rebuild_start_btn()
        await interaction.response.edit_message(embed=_rr_lobby_embed(g), view=self)

    @discord.ui.button(label="▶️ دەستپێبکە | Start", style=discord.ButtonStyle.success, custom_id="rr_start", disabled=True)
    async def start_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        g   = self.game
        uid = str(interaction.user.id)
        if g.state != "lobby":
            await interaction.response.send_message("❌ لۆبی نییە | No lobby.", ephemeral=True); return
        if int(uid) != g.host_id:
            await interaction.response.send_message("❌ تەنها میوانداری دەتوانێت دەستپێبکات | Only the host can start.", ephemeral=True); return
        if len(g.players) < 2:
            await interaction.response.send_message("❌ لانیکەم ٢ یاریزان پێویستە | Need at least 2 players!", ephemeral=True); return

        g.state = "playing"
        random.shuffle(g.players)
        g.alive = set(g.players)
        g.spin_cylinder()

        for child in self.children:
            child.disabled = True
        started_embed = _rr_lobby_embed(g)
        started_embed.description = "💥 یاری دەستپێدەکات! خۆشبەختی... پێویستتتە. | Game starting! Good luck... you'll need it."
        started_embed.color = 0xDC2626
        await interaction.response.edit_message(embed=started_embed, view=self)

        await asyncio.sleep(1.5)

        order_text = "\n".join(f"{i+1}. <@{uid}>" for i, uid in enumerate(g.players))
        begin_embed = discord.Embed(
            title="🔫 یاری دەستپێکرد | The Game Begins",
            description=(
                f"> *{len(g.players)} یاریزان. یەک گولولە. کێ دەگەڕێتەوە ماڵ؟ | {len(g.players)} players. One bullet. Who goes home?*\n\n"
                f"**ڕیزی نۆبەت | Turn order:**\n{order_text}\n\n"
                "سیلیندەرەکە سوڕاوەتەوە. هیچکەس نازانێت گولولەکە لەکوێیە.\n"
                "The cylinder has been spun. No one knows where the bullet is.\n"
                "**قۆناغی ١ ئێستا دەستپێدەکات | Round 1 starts now.**"
            ),
            color=0x1A1A1A,
        )
        await interaction.channel.send(embed=begin_embed)
        await asyncio.sleep(2)
        await _rr_run_turn(g, interaction.channel)

    async def on_timeout(self):
        roulette_sessions.pop(self.game.channel_id, None)


# ── Turn runner ────────────────────────────────────────────────────────────────

async def _rr_run_turn(game: RouletteGame, channel):
    if game.state != "playing":
        return
    game.pull_lock = False
    current_id = game.current_player()
    if current_id is None:
        return
    view  = RoulettePullView(game, channel)
    embed = _rr_turn_embed(game, current_id)
    await channel.send(content=f"<@{current_id}>", embed=embed, view=view)


async def _rr_process_pull(game: RouletteGame, channel, uid: str):
    suspense_msg = await channel.send(random.choice(RR_SUSPENSE))
    await asyncio.sleep(2.2)

    if uid not in game.stats:
        game.stats[uid] = {"survived": 0, "pulls": 0}
    game.stats[uid]["pulls"] += 1

    eliminated = game.pull_trigger()

    if eliminated:
        game.alive.discard(uid)
        await suspense_msg.edit(content=random.choice(RR_ELIMINATED) + f"\n> <@{uid}> دەریکرا | has been eliminated.")
        await asyncio.sleep(1.5)

        alive = game.alive_players()
        if len(alive) == 1:
            game.state = "ended"
            roulette_sessions.pop(game.channel_id, None)
            await asyncio.sleep(0.8)
            await channel.send(embed=_rr_win_embed(alive[0], game))
            return
        if len(alive) == 0:
            game.state = "ended"
            roulette_sessions.pop(game.channel_id, None)
            await channel.send(embed=discord.Embed(
                title="💀 هەموویان چوون... | Everyone's gone...",
                description="هیچ مانەوەیەک نییە. بە ڕاستی کاووس بوو. | No survivors. Truly chaotic.",
                color=0x1A1A1A,
            ))
            return
        await asyncio.sleep(0.8)
    else:
        game.stats[uid]["survived"] += 1
        await suspense_msg.edit(content=random.choice(RR_SURVIVED))
        await asyncio.sleep(1.2)
        game.advance_turn()

    alive = game.alive_players()
    if alive and game.current_idx % len(alive) == 0 and not eliminated:
        game.round += 1

    await _rr_run_turn(game, channel)


# ── Commands ───────────────────────────────────────────────────────────────────

@bot.command(name="roulette")
async def roulette_cmd(ctx):
    """Start a Russian Roulette game (2-8 players). | یارییەکی ڕووسی ڕووڵێت دەستپێبکە (٢-٨ یاریزان)."""
    cid = ctx.channel.id
    if cid in roulette_sessions:
        await ctx.send(
            "⚠️ هەر یارییەکی ڕووسی ڕووڵێت چالاکە لەم کەناڵەدا! | "
            "There's already an active Russian Roulette game in this channel!",
            delete_after=8
        )
        return

    game = RouletteGame(ctx.author.id, cid)
    game.players.append(str(ctx.author.id))
    game.alive.add(str(ctx.author.id))
    roulette_sessions[cid] = game

    view = RouletteLobbyView(game)
    await ctx.send(embed=_rr_lobby_embed(game), view=view)
    try:
        await ctx.message.delete()
    except Exception:
        pass


@bot.command(name="roulettestop")
@commands.has_permissions(manage_messages=True)
async def roulette_stop(ctx):
    """Force-stop a Russian Roulette game. | یارییەکی ڕووسی ڕووڵێت بوەستێنە."""
    cid = ctx.channel.id
    if cid not in roulette_sessions:
        await ctx.send("❌ هیچ یارییەکی چالاکی ڕووسی ڕووڵێت نییە لەم کەناڵەدا | No active Russian Roulette game here.", delete_after=8)
        return
    roulette_sessions.pop(cid, None)
    embed = discord.Embed(
        title="🛑 یاری هەڵوەشایەوە | Game Stopped",
        description=f"یارییەکی ڕووسی ڕووڵێت بە هێزی لەلایەن {ctx.author.mention} وەستاندرا.\nThe Russian Roulette game was force-stopped by {ctx.author.mention}.",
        color=0xEF4444,
    )
    await ctx.send(embed=embed)
    try:
        await ctx.message.delete()
    except Exception:
        pass



# ═══════════════════════ MODERATION COMMANDS ═══════════════════════

@bot.command(name="promote")
@commands.has_permissions(manage_roles=True)
async def promote_cmd(ctx, member: discord.Member, *, role: discord.Role):
    if role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
        return await ctx.send("❌ ناتوانیت رۆڵێک بدەیت کە یەکسانە یان بەرزتر لە رۆڵی خۆتە. | You cannot assign a role equal to or higher than your own.")
    if role >= ctx.guild.me.top_role:
        return await ctx.send("❌ ئەو رۆڵە بەرزتر لە رۆڵی منە. | That role is higher than mine.")
    try:
        await member.add_roles(role, reason=f"Promoted by {ctx.author}")
        embed = discord.Embed(
            color=0xF59E0B,
            title="🌟 پرۆمۆت | Promotion",
            description=(
                f"پیرۆزە بە {member.mention}! بە ڕەسمی بە رۆڵی **{role.name}** گەیشت.\n"
                f"Congratulations {member.mention}! You have been promoted to **{role.name}**.\n\n"
                f"**پرۆمۆتکرا بە | Promoted by:** {ctx.author.mention}"
            )
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_footer(text=f"{ctx.guild.name} · Staff Team")
        await ctx.send(embed=embed)
    except discord.Forbidden:
        await ctx.send("❌ مووچەم نییە ئەو رۆڵە زیاد بکەم. | I don't have permission to add that role.")

@promote_cmd.error
async def promote_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ مووچەی بەڕێوەبردنی رۆڵەکان پێویستە. | You need the Manage Roles permission.")
    elif isinstance(error, (commands.MemberNotFound, commands.RoleNotFound, commands.MissingRequiredArgument)):
        await ctx.send("بەکارهێنان: `!promote @ئەندام <ناوی رۆڵ>` | Usage: `!promote @member <role name>`")


@bot.command(name="demote")
@commands.has_permissions(manage_roles=True)
async def demote_cmd(ctx, member: discord.Member, *, role: discord.Role):
    if role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
        return await ctx.send("❌ ناتوانیت رۆڵێک لابدەیت کە یەکسانە یان بەرزتر لە رۆڵی خۆتە. | You cannot remove a role equal to or higher than your own.")
    if role not in member.roles:
        return await ctx.send(f"❌ {member.mention} رۆڵی **{role.name}** نییە. | {member.mention} does not have the **{role.name}** role.")
    try:
        await member.remove_roles(role, reason=f"Demoted by {ctx.author}")
        embed = discord.Embed(
            color=0xED4245,
            title="📉 دیمۆت | Demotion",
            description=(
                f"{member.mention} رۆڵی **{role.name}** لێ لادرا.\n"
                f"{member.mention} has been demoted from **{role.name}**.\n\n"
                f"**دیمۆتکرا بە | Demoted by:** {ctx.author.mention}"
            )
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_footer(text=f"{ctx.guild.name} · Staff Team")
        await ctx.send(embed=embed)
    except discord.Forbidden:
        await ctx.send("❌ مووچەم نییە ئەو رۆڵە لابدەم. | I don't have permission to remove that role.")

@demote_cmd.error
async def demote_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ مووچەی بەڕێوەبردنی رۆڵەکان پێویستە. | You need the Manage Roles permission.")
    elif isinstance(error, (commands.MemberNotFound, commands.RoleNotFound, commands.MissingRequiredArgument)):
        await ctx.send("بەکارهێنان: `!demote @ئەندام <ناوی رۆڵ>` | Usage: `!demote @member <role name>`")


@bot.command(name="giverole")
@commands.has_permissions(manage_roles=True)
async def giverole_cmd(ctx, member: discord.Member, *, role: discord.Role):
    if role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
        return await ctx.send("❌ ناتوانیت رۆڵێک بدەیت کە یەکسانە یان بەرزتر لە رۆڵی خۆتە. | You cannot assign a role equal to or higher than your own.")
    if role >= ctx.guild.me.top_role:
        return await ctx.send("❌ ئەو رۆڵە بەرزتر لە رۆڵی منە. | That role is higher than mine.")
    if role in member.roles:
        return await ctx.send(f"❌ {member.mention} پێشتر ئەو رۆڵەیەتی. | {member.mention} already has that role.")
    try:
        await member.add_roles(role, reason=f"Role given by {ctx.author}")
        embed = discord.Embed(
            color=0x57F287,
            title="✅ رۆڵ درا | Role Given",
            description=(
                f"رۆڵی **{role.name}** درا بە {member.mention}.\n"
                f"Role **{role.name}** has been given to {member.mention}.\n\n"
                f"**لەلایەن | By:** {ctx.author.mention}"
            )
        )
        embed.set_footer(text=f"{ctx.guild.name} · Role Management")
        await ctx.send(embed=embed)
    except discord.Forbidden:
        await ctx.send("❌ مووچەم نییە ئەو رۆڵە زیاد بکەم. | I don't have permission to add that role.")

@giverole_cmd.error
async def giverole_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ مووچەی بەڕێوەبردنی رۆڵەکان پێویستە. | You need the Manage Roles permission.")
    elif isinstance(error, (commands.MemberNotFound, commands.RoleNotFound, commands.MissingRequiredArgument)):
        await ctx.send("بەکارهێنان: `!giverole @ئەندام <ناوی رۆڵ>` | Usage: `!giverole @member <role name>`")


@bot.command(name="takerole")
@commands.has_permissions(manage_roles=True)
async def takerole_cmd(ctx, member: discord.Member, *, role: discord.Role):
    if role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
        return await ctx.send("❌ ناتوانیت رۆڵێک لابدەیت کە یەکسانە یان بەرزتر لە رۆڵی خۆتە. | You cannot remove a role equal to or higher than your own.")
    if role not in member.roles:
        return await ctx.send(f"❌ {member.mention} ئەو رۆڵەی نییە. | {member.mention} does not have that role.")
    try:
        await member.remove_roles(role, reason=f"Role taken by {ctx.author}")
        embed = discord.Embed(
            color=0xED4245,
            title="❌ رۆڵ لادرا | Role Removed",
            description=(
                f"رۆڵی **{role.name}** لە {member.mention} لادرا.\n"
                f"Role **{role.name}** has been removed from {member.mention}.\n\n"
                f"**لەلایەن | By:** {ctx.author.mention}"
            )
        )
        embed.set_footer(text=f"{ctx.guild.name} · Role Management")
        await ctx.send(embed=embed)
    except discord.Forbidden:
        await ctx.send("❌ مووچەم نییە ئەو رۆڵە لابدەم. | I don't have permission to remove that role.")

@takerole_cmd.error
async def takerole_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ مووچەی بەڕێوەبردنی رۆڵەکان پێویستە. | You need the Manage Roles permission.")
    elif isinstance(error, (commands.MemberNotFound, commands.RoleNotFound, commands.MissingRequiredArgument)):
        await ctx.send("بەکارهێنان: `!takerole @ئەندام <ناوی رۆڵ>` | Usage: `!takerole @member <role name>`")


@bot.command(name="stafflist", aliases=["staff_list", "staffs"])
async def stafflist_cmd(ctx):
    if ctx.guild is None:
        return await ctx.send("Server only. | تەنها لە سێرڤەر.")
    staff_roles_keywords = ["staff", "admin", "mod", "owner", "manager", "helper", "ستاف", "ئادمین", "مۆد", "موڵکدار", "بەڕێوەبەر"]
    staff_entries = []
    seen_ids = set()
    for role in ctx.guild.roles:
        if any(kw in role.name.lower() for kw in staff_roles_keywords):
            for member in role.members:
                if member.id not in seen_ids:
                    seen_ids.add(member.id)
                    status_emoji = {
                        discord.Status.online: "🟢",
                        discord.Status.idle: "🟡",
                        discord.Status.dnd: "🔴",
                        discord.Status.offline: "⚫",
                    }.get(member.status, "⚫")
                    staff_entries.append(f"{status_emoji} **{member.display_name}** — {role.name}")
    if not staff_entries:
        return await ctx.send(
            "❌ هیچ ستافێک نەدۆزرایەوە. دڵنیابە رۆڵەکانت ناوی (staff, admin, mod...) تێدا هەیە.\n"
            "❌ No staff found. Make sure your roles contain (staff, admin, mod...) in their name."
        )
    embed = discord.Embed(
        color=0x5865F2,
        title=f"👥 لیستی ستاف | Staff List — {ctx.guild.name}",
        description="\n".join(staff_entries)
    )
    embed.set_footer(text=f"کۆی ستاف: {len(staff_entries)} | Total staff: {len(staff_entries)}")
    if ctx.guild.icon:
        embed.set_thumbnail(url=ctx.guild.icon.url)
    await ctx.send(embed=embed)


@bot.command(name="anti_link", aliases=["antilink", "antilinkfilter"])
@commands.has_permissions(manage_guild=True)
async def anti_link_cmd(ctx):
    if ctx.guild is None:
        return await ctx.send("Server only. | تەنها لە سێرڤەر.")
    gid = str(ctx.guild.id)
    current = anti_link_guilds.get(gid, False)
    anti_link_guilds[gid] = not current
    status = not current
    if status:
        embed = discord.Embed(
            color=0x57F287,
            title="🔗 فیلتەری لینک چالاككرا | Anti-Link Enabled",
            description=(
                "فیلتەری لینک چالاک کرا بۆ ئەم سێرڤەرە.\n"
                "Anti-link filter has been **enabled** for this server.\n\n"
                "ئەندامانی ئاسایی ناتوانن لینک بنێرن. ئەوانەی کە مووچەی Manage Messages هەیانە دەتوانن.\n"
                "Regular members cannot send links. Staff with Manage Messages permission can."
            )
        )
    else:
        embed = discord.Embed(
            color=0xED4245,
            title="🔗 فیلتەری لینک ناچالاككرا | Anti-Link Disabled",
            description=(
                "فیلتەری لینک ناچالاک کرا بۆ ئەم سێرڤەرە.\n"
                "Anti-link filter has been **disabled** for this server."
            )
        )
    embed.set_footer(text=f"لەلایەن | By: {ctx.author.display_name}")
    await ctx.send(embed=embed)

@anti_link_cmd.error
async def anti_link_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ مووچەی بەڕێوەبردنی سێرڤەر پێویستە. | You need the Manage Server permission.")


# ═══════════════ SETUP STAFF DAILY ═══════════════

class StaffDailyRoleSelect(discord.ui.RoleSelect):
    def __init__(self):
        super().__init__(
            placeholder="هەڵبژێرە رۆڵەکانی ستاف | Pick staff roles to ping...",
            min_values=1,
            max_values=10,
            custom_id="staff_daily_role_select",
        )

    async def callback(self, interaction: discord.Interaction):
        gid = str(interaction.guild_id)
        role_ids = [r.id for r in self.values]
        save_staff_daily_roles(gid, role_ids)
        role_mentions = ", ".join(r.mention for r in self.values)
        ch_id = staff_daily_channels.get(gid)
        ch_mention = f"<#{ch_id}>" if ch_id else "❌ Not set — use `!staff setchannel`"
        embed = discord.Embed(
            color=0x57F287,
            title="✅ دەیلی ستاف دانراو | Staff Daily Configured",
            description=(
                f"**ڕۆڵەکانی پینگکراو:**\n{role_mentions}\n\n"
                f"**کەناڵ:** {ch_mention}\n\n"
                "هەموو ڕۆژێک لە کاتژمێڕ **٩ ئێوارە** دەیلی دەنێردرێت."
            ),
        )
        embed.set_footer(text=f"Set by {interaction.user.display_name}")
        self.view.stop()
        await interaction.response.edit_message(embed=embed, view=None)


class StaffDailySetupView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=120)
        self.add_item(StaffDailyRoleSelect())


@bot.command(name="setupstaffdaily", aliases=["setstaffdaily", "staffdailysetup"])
@commands.has_permissions(administrator=True)
async def setupstaffdaily_cmd(ctx):
    """Interactive setup: pick which roles get pinged by the staff daily."""
    if ctx.guild is None:
        return await ctx.send("Server only. | تەنها لە سێرڤەر.")
    gid = str(ctx.guild.id)
    ch_id = staff_daily_channels.get(gid)
    ch_mention = f"<#{ch_id}>" if ch_id else "❌ Not set — use `!staff setchannel`"
    existing_ids = staff_daily_roles_map.get(gid, [])
    existing_text = (", ".join(f"<@&{r}>" for r in existing_ids)
                     if existing_ids else "هیچ | None")
    embed = discord.Embed(
        color=0x5865F2,
        title="⚙️ دانانی دەیلی ستاف | Staff Daily Setup",
        description=(
            f"**کەناڵی ئێستا | Current Channel:** {ch_mention}\n"
            f"**رۆڵەکانی ئێستا | Current Roles:** {existing_text}\n\n"
            "لەخوارەوە رۆڵەکانی ستافت هەڵبژێرە کە دەتەوێت ڕۆژانە پینگ بکرێن.\n"
            "Pick the staff roles below that should be pinged every day at 9 PM UTC."
        ),
    )
    embed.set_footer(text=f"{ctx.guild.name} · Staff Daily Setup")
    await ctx.send(embed=embed, view=StaffDailySetupView())


@setupstaffdaily_cmd.error
async def setupstaffdaily_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ مووچەی Manage Server پێویستە. | You need Manage Server permission.")


@bot.group(name="staff", invoke_without_command=True)
async def staff_group(ctx):
    pass

@staff_group.command(name="daily")
async def staff_daily(ctx):
    """Send the staff daily message with role pings to the configured channel (or here if none set)."""
    if ctx.guild is None:
        return await ctx.send("Server only. | تەنها لە سێرڤەر.")
    gid = str(ctx.guild.id)
    role_ids = staff_daily_roles_map.get(gid, [])
    if not role_ids:
        return await ctx.send(
            "❌ هیچ رۆڵێک دانەنراوە.\n"
            "بەکارببە: `!setupstaffdaily`"
        )
    pings = " ".join(f"<@&{rid}>" for rid in role_ids)
    ch_id = staff_daily_channels.get(gid)
    target_channel = (ctx.guild.get_channel(int(ch_id)) if ch_id else None) or ctx.channel
    await _send_staff_daily(ctx.guild, target_channel, pings)
    if target_channel != ctx.channel:
        await ctx.send(f"✅ دەیلی ستاف نێردرا بۆ {target_channel.mention}")


@staff_group.command(name="setchannel")
@commands.has_permissions(manage_guild=True)
async def staff_set_channel(ctx, channel: discord.TextChannel = None):
    """Set the channel for automatic 9 PM staff daily pings."""
    if ctx.guild is None:
        return await ctx.send("Server only. | تەنها لە سێرڤەر.")
    target = channel or ctx.channel
    staff_daily_channels[str(ctx.guild.id)] = target.id
    save_staff_daily_channels()
    embed = discord.Embed(
        color=0x57F287,
        title="✅ کەناڵی دەیلی دانراو | Daily Channel Set",
        description=(
            f"هەموو رۆژێک لە کاتژمێر **٩ ئێوارە** دەیلیەکان دەنێردرێن بۆ {target.mention}.\n\n"
            f"بۆ تاقیکردنەوە: `!staff daily`"
        ),
    )
    embed.set_footer(text=f"Set by {ctx.author.display_name}")
    await ctx.send(embed=embed)



# ═══════════════ SETUP ISLAM / FRIDAY REMINDER ═══════════════


class IslamTextEditModal(discord.ui.Modal, title="✏️ دەستکاری دەقی جومعە | Edit Text"):
    text_ku = discord.ui.TextInput(
        label="🇮🇶 کوردی — Kurdish Text",
        placeholder="دەقی کوردی بنووسە...",
        style=discord.TextStyle.paragraph,
        max_length=1500,
        required=False,
    )
    text_en = discord.ui.TextInput(
        label="🇬🇧 English Text",
        placeholder="Write the English reminder text here...",
        style=discord.TextStyle.paragraph,
        max_length=1500,
        required=False,
    )

    def __init__(self, guild_id: int, current_en: str = "", current_ku: str = ""):
        super().__init__()
        self.guild_id = guild_id
        self.text_en.default = current_en
        self.text_ku.default = current_ku

    async def on_submit(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message(
                "❌ تەنها ەدمین دەتوانێت دەقەکە بگۆڕێت. | Only administrators can edit this text.",
                ephemeral=True,
            )
        save_islam_settings(
            self.guild_id,
            text_en=self.text_en.value.strip(),
            text_ku=self.text_ku.value.strip(),
        )
        await interaction.response.send_message(
            "✅ دەقی جومعە نوێکرایەوە! | Friday reminder text updated! 🕌",
            ephemeral=True,
        )

    async def on_error(self, interaction: discord.Interaction, error: Exception):
        try:
            await interaction.response.send_message(
                "❌ هەڵەیەک ڕوویدا. | An error occurred.", ephemeral=True
            )
        except Exception:
            pass


class IslamSetupView(discord.ui.View):
    """Persistent setup panel for the !islam Friday reminder — admin only."""

    def __init__(self):
        super().__init__(timeout=None)

    async def _admin_check(self, interaction: discord.Interaction) -> bool:
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "❌ تەنها ەدمین دەتوانێت ەمەی بەکار بینێت. | Only administrators can use this panel.",
                ephemeral=True,
            )
            return False
        return True

    @discord.ui.select(
        cls=discord.ui.ChannelSelect,
        placeholder="١️⃣ کەناڵی جومعە هەڵبژێرە | Select the Friday reminder channel",
        channel_types=[discord.ChannelType.text],
        custom_id="islam:channel_select",
        row=0,
    )
    async def channel_select(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
        if not await self._admin_check(interaction):
            return
        ch = select.values[0]
        save_islam_settings(interaction.guild_id, channel_id=ch.id)
        await interaction.response.send_message(
            f"✅ کەناڵی جومعە دانرا: {ch.mention} | Friday channel set to {ch.mention}.",
            ephemeral=True,
        )

    @discord.ui.select(
        cls=discord.ui.RoleSelect,
        placeholder="٢️⃣ ڕۆڵی جومعە هەڵبژێرە | Select the role to ping on Thursdays",
        custom_id="islam:role_select",
        row=1,
    )
    async def role_select(self, interaction: discord.Interaction, select: discord.ui.RoleSelect):
        if not await self._admin_check(interaction):
            return
        role = select.values[0]
        save_islam_settings(interaction.guild_id, role_id=role.id)
        await interaction.response.send_message(
            f"✅ ڕۆڵی جومعە دانرا: {role.mention} | Friday ping role set to {role.mention}.",
            ephemeral=True,
        )

    @discord.ui.button(
        label="✏️ دەستکاری دەق | Edit Text",
        style=discord.ButtonStyle.primary,
        custom_id="islam:edit_text",
        row=2,
    )
    async def edit_text_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._admin_check(interaction):
            return
        try:
            gid    = interaction.guild_id
            cfg    = islam_settings_map.get(str(gid), {})
            # Truncate stored text to the modal's max_length so Discord never rejects it
            tex_en = (cfg.get("text_en") or "")[:1500]
            tex_ku = (cfg.get("text_ku") or "")[:1500]
            await interaction.response.send_modal(
                IslamTextEditModal(gid, tex_en, tex_ku)
            )
        except Exception as exc:
            try:
                await interaction.response.send_message(
                    f"❌ هەڵەیەک ڕوویدا. | Error opening editor: `{exc}`",
                    ephemeral=True,
                )
            except Exception:
                pass

    @discord.ui.button(
        label="📤 ناردنی ەیستا | Send Now",
        style=discord.ButtonStyle.success,
        custom_id="islam:send_now",
        row=2,
    )
    async def send_now_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._admin_check(interaction):
            return
        try:
            gid = str(interaction.guild_id)
            cfg = islam_settings_map.get(gid, {})
            cid = cfg.get("channel_id")
            rid = cfg.get("role_id")
            if not cid or not rid:
                return await interaction.response.send_message(
                    "❌ پێشتر کەناڵ و ڕۆڵ دیاری بکە. | Set a channel and role first.",
                    ephemeral=True,
                )
            ch = interaction.guild.get_channel(int(cid))
            if not ch:
                return await interaction.response.send_message(
                    "❌ کەناڵ نەدۆزرایەوە. | Channel not found.", ephemeral=True
                )
            # Acknowledge the interaction FIRST (before any network work).
            # Then run the actual ping as a fire-and-forget background task so
            # we never hit the 3-second interaction deadline.
            await interaction.response.send_message(
                f"✅ پەیامی جومعە دەنێردرێت بۆ {ch.mention} | Sending Friday ping to {ch.mention}…",
                ephemeral=True,
            )
            asyncio.ensure_future(
                _send_islam_ping(interaction.guild, ch, f"<@&{rid}>")
            )
        except Exception as exc:
            try:
                await interaction.response.send_message(
                    f"❌ هەڵە ڕوویدا | An error occurred: `{exc}`", ephemeral=True
                )
            except Exception:
                pass

    async def on_error(
        self,
        interaction: discord.Interaction,
        error: Exception,
        item: discord.ui.Item,
    ) -> None:
        """Catch-all: make sure every unhandled exception produces a visible reply."""
        try:
            await interaction.response.send_message(
                f"❌ هەڵەیەک ڕوویدا. | An error occurred: `{error}`",
                ephemeral=True,
            )
        except Exception:
            try:
                await interaction.followup.send(
                    f"❌ هەڵەیەک ڕوویدا. | An error occurred: `{error}`",
                    ephemeral=True,
                )
            except Exception:
                pass

    @discord.ui.button(
        label="📊 دۆخ | Status",
        style=discord.ButtonStyle.secondary,
        custom_id="islam:status",
        row=3,
    )
    async def status_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._admin_check(interaction):
            return
        gid = str(interaction.guild_id)
        cfg = islam_settings_map.get(gid, {})
        cid = cfg.get("channel_id")
        rid = cfg.get("role_id")
        ten = cfg.get("text_en", "")
        tku = cfg.get("text_ku", "")
        embed = discord.Embed(
            color=0x2ECC71,
            title="🕌 دۆخی دامەزراندنی جومعە | Islam Setup Status",
            timestamp=datetime.datetime.utcnow(),
        )
        embed.add_field(name="📢 کەناڵ | Channel",  value=f"<#{cid}>" if cid else "❌ دانەنراوە | Not set", inline=True)
        embed.add_field(name="🔔 ڕۆڵ | Role",        value=f"<@&{rid}>" if rid else "❌ دانەنراوە | Not set", inline=True)
        embed.add_field(name="⏰ کات | Schedule",    value="هەموو پێنجشەممە 9 ەیوارە (عێراق) | Every Thursday 9 PM Iraq time", inline=False)
        embed.add_field(name="🇮🇶 کوردی | KU Text",  value=(tku[:200] + "…" if len(tku) > 200 else tku) or "_(empty)_", inline=False)
        embed.add_field(name="🇬🇧 ەینگڵیزی | EN Text", value=(ten[:200] + "…" if len(ten) > 200 else ten) or "_(empty)_", inline=False)
        embed.set_footer(text=interaction.guild.name)
        await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.command(name="islam", aliases=["setupislam", "islamsetup", "fridaysetup"])
@commands.has_permissions(administrator=True)
async def islam_cmd(ctx):
    """Open the Islam/Friday reminder setup panel — administrators only."""
    if ctx.guild is None:
        return await ctx.send("Server only. | تەنها لە سێرڤەر.")
    gid = str(ctx.guild.id)
    cfg = islam_settings_map.get(gid, {})
    cid = cfg.get("channel_id")
    rid = cfg.get("role_id")
    embed = discord.Embed(
        color=0x2ECC71,
        title="🕌 دامەزراندنی یادەوەری جومعە | Islam / Friday Reminder Setup",
        description=(
            "١️⃣ کەناڵ هەڵبژێرە کە پینگەکە دەنێردرێت تیایدا.\n"
            "٢️⃣ ڕۆڵ هەڵبژێرە کە دەنگ پێدەدرێت.\n"
            "٣️⃣ دەقەکە دەستکاری بکە (هەر دوو زمان).\n\n"
            "1️⃣ Select the channel where the reminder is sent.\n"
            "2️⃣ Select the role that gets pinged.\n"
            "3️⃣ Edit the message text (bilingual).\n\n"
            f"کەناڵی ەیستا | Current channel: {f'<#{cid}>' if cid else '❌ دانەنراوە | Not set'}\n"
            f"ڕۆڵی ەیستا | Current role: {f'<@&{rid}>' if rid else '❌ دانەنراوە | Not set'}\n\n"
            "⏰ هەموو شەوی پێنجشەممە کاتژمێر ১ ەیوارەی عێراق (UTC+3)\n"
            "⏰ Every Thursday at 9 PM Iraq time (UTC+3)"
        ),
        timestamp=datetime.datetime.utcnow(),
    )
    if ctx.guild.icon:
        embed.set_thumbnail(url=ctx.guild.icon.url)
    embed.set_footer(text=f"{ctx.guild.name} · Admins only")
    try:
        await ctx.message.delete()
    except (discord.Forbidden, discord.HTTPException):
        pass
    await ctx.send(embed=embed, view=IslamSetupView())


@islam_cmd.error
async def islam_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ تەنها ەدمین دەتوانێت ەمەی بەکار بینێت. | Only administrators can use this command.")


@bot.command(name="setislamchannel", aliases=["islamchannel", "islamsetchannel", "setfridaychannel"])
@commands.has_permissions(administrator=True)
async def setislamchannel_cmd(ctx, channel: discord.TextChannel = None):
    """Set the channel where the Islam/Friday reminder ping is sent.
    Usage: !setislamchannel #channel  (omit channel to use current channel)
    """
    if ctx.guild is None:
        return await ctx.send("Server only. | تەنها لە سێرڤەر.")
    target = channel or ctx.channel
    save_islam_settings(ctx.guild.id, channel_id=target.id)
    cfg = islam_settings_map.get(str(ctx.guild.id), {})
    rid  = cfg.get("role_id")
    e = discord.Embed(
        color=0x2ECC71,
        title="🕌 کەناڵی یادەوەری جومعە دانرا! | Islam Channel Set!",
        description=(
            f"پینگی جومعە دەنێردرێت بۆ {target.mention}.\n"
            f"Friday reminder will be sent to {target.mention}.\n\n"
            + (
                f"ڕۆڵی پینگ | Ping role: <@&{rid}>\n\n"
                if rid else
                "⚠️ هێشتا ڕۆڵ دانەنراوە. بە `!islam` دامەزرابکە.\n"
                "⚠️ No role set yet. Use `!islam` panel to set one.\n\n"
            )
            + "⏰ هەموو شەوی پێنجشەممە کاتژمێر ۹ ئێوارەی عێراق (UTC+3)\n"
            "⏰ Every Thursday at 9 PM Iraq time (UTC+3)"
        ),
    )
    e.set_footer(text=f"Set by {ctx.author.display_name} · {ctx.guild.name}")
    if ctx.guild.icon:
        e.set_thumbnail(url=ctx.guild.icon.url)
    try:
        await ctx.message.delete()
    except (discord.Forbidden, discord.HTTPException):
        pass
    await ctx.send(embed=e)


@setislamchannel_cmd.error
async def setislamchannel_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send(
            "❌ تەنها ئەدمین دەتوانێت ئەمەی بەکار بینێت. | Only administrators can use this command."
        )
    elif isinstance(error, commands.BadArgument):
        await ctx.send(
            "❌ کەناڵ نەدۆزرایەوە. | Channel not found.\n"
            "Usage: `!setislamchannel #channel` — or just `!setislamchannel` to use the current channel."
        )


@staff_group.command(name="removechannel")
@commands.has_permissions(manage_guild=True)
async def staff_remove_channel(ctx):
    """Remove the automatic daily ping channel."""
    if ctx.guild is None:
        return await ctx.send("Server only. | تەنها لە سێرڤەر.")
    gid = str(ctx.guild.id)
    if gid in staff_daily_channels:
        del staff_daily_channels[gid]
        save_staff_daily_channels()
        await ctx.send("✅ کەناڵی دەیلی لادرا. | Daily channel removed. Auto-pings stopped.")
    else:
        await ctx.send("❌ هیچ کەناڵێک دانەنرابوو. | No channel was set.")


# ═══════════════════════ REKLAM SYSTEM ═══════════════════════

# ─── Reklam Text Modal ───────────────────────────────────────────────────────
class ReklamTextModal(discord.ui.Modal, title="✏️ Edit Reklam Text | دەقی ریکلام"):
    text_input = discord.ui.TextInput(
        label="Edit Text  (use {user} to tag the requester)",
        placeholder="📣 {user} داوای ریکلامی کرد! | requested a reklam slot!",
        style=discord.TextStyle.paragraph,
        max_length=1000,
        required=True,
    )

    async def on_submit(self, interaction: discord.Interaction):
        save_reklam_text(interaction.guild.id, self.text_input.value)
        preview = self.text_input.value.replace("{user}", f"@{interaction.user.display_name}")
        embed = discord.Embed(
            color=0xF59E0B,
            title="✅ دەقی ریکلام نوێکرایەوە | Reklam Text Updated",
            description=(
                "دەقی ئاگادارکردنەوەی ریکلام بە سەرکەوتوویی نوێکرایەوە.\n"
                "The reklam notification text was successfully updated."
            ),
            timestamp=datetime.datetime.utcnow(),
        )
        embed.add_field(
            name="📝 دەقی نوێ | New Text",
            value=f"```{self.text_input.value[:900]}```",
            inline=False,
        )
        embed.add_field(
            name="👁️ پێشبینی | Preview",
            value=f"> {preview[:300]}",
            inline=False,
        )
        embed.add_field(
            name="💡 تێبینی | Note",
            value=(
                "`{user}` → دەگۆڕدرێت بە پینگی داواکار\n"
                "`{user}` → replaced with the requester's mention"
            ),
            inline=False,
        )
        embed.set_thumbnail(url=interaction.guild.icon.url if interaction.guild.icon else interaction.user.display_avatar.url)
        embed.set_footer(
            text=f"✏️ Edited by {interaction.user.display_name} · {interaction.guild.name}",
            icon_url=interaction.user.display_avatar.url,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


# ─── Invite Text Modal ───────────────────────────────────────────────────────
class InviteTextModal(discord.ui.Modal, title="✏️ Edit Invite Text | دەقی بانگهێشت"):
    text_input = discord.ui.TextInput(
        label="Edit Text",
        placeholder="🎉 Welcome {user}! Invited by {inviter} · {count} invites total",
        style=discord.TextStyle.paragraph,
        max_length=1000,
        required=True,
    )

    async def on_submit(self, interaction: discord.Interaction):
        save_invite_custom_text(interaction.guild.id, self.text_input.value)
        preview = (
            self.text_input.value
            .replace("{user}", f"@{interaction.user.display_name}")
            .replace("{inviter}", "@ServerOwner")
            .replace("{count}", "42")
        )
        embed = discord.Embed(
            color=0x5865F2,
            title="✅ دەقی بانگهێشت نوێکرایەوە | Invite Text Updated",
            description=(
                "دەقی بانگهێشتکردن بە سەرکەوتوویی نوێکرایەوە.\n"
                "The invite announcement text was successfully updated."
            ),
            timestamp=datetime.datetime.utcnow(),
        )
        embed.add_field(
            name="📝 دەقی نوێ | New Text",
            value=f"```{self.text_input.value[:900]}```",
            inline=False,
        )
        embed.add_field(
            name="👁️ پێشبینی | Preview",
            value=f"> {preview[:300]}",
            inline=False,
        )
        embed.add_field(
            name="🔖 پلەیسهۆڵدەرەکان | Placeholders",
            value=(
                "`{user}` → بانگهێشتکراو | new member mention\n"
                "`{inviter}` → کێ بانگهێشتی کرد | who invited them\n"
                "`{count}` → کۆی بانگهێشتەکان | total invites"
            ),
            inline=False,
        )
        embed.set_thumbnail(url=interaction.guild.icon.url if interaction.guild.icon else interaction.user.display_avatar.url)
        embed.set_footer(
            text=f"✏️ Edited by {interaction.user.display_name} · {interaction.guild.name}",
            icon_url=interaction.user.display_avatar.url,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


# ─── Invite Setup View ───────────────────────────────────────────────────────
class InviteSetupView(discord.ui.View):
    def __init__(self, guild_id: int):
        super().__init__(timeout=None)
        self.guild_id = guild_id

    @discord.ui.button(label="✏️ Edit Text", style=discord.ButtonStyle.primary)
    async def edit_text_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.manage_guild:
            return await interaction.response.send_message(
                "❌ مووچەی Manage Server پێویستە. | You need Manage Server permission.", ephemeral=True
            )
        modal = InviteTextModal()
        current = get_invite_custom_text(self.guild_id)
        if current:
            modal.text_input.default = current
        await interaction.response.send_modal(modal)


# ─── Reklam Setup View ───────────────────────────────────────────────────────
class ReklamSetupView(discord.ui.View):
    """Interactive setup for !setreklam — pick channel then role."""
    def __init__(self, ctx):
        super().__init__(timeout=120)
        self.ctx = ctx
        self.chosen_channel = None
        self.chosen_role = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("❌ تەنها ئەو کەسە دەتوانێت ئەمەی بەکار بێنێت. | Only the command user can use this.", ephemeral=True)
            return False
        return True

    @discord.ui.select(
        cls=discord.ui.ChannelSelect,
        placeholder="1️⃣ کەناڵی ریکلام هەڵبژێرە | Select the reklam channel",
        channel_types=[discord.ChannelType.text],
        row=0,
    )
    async def channel_select(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
        self.chosen_channel = select.values[0]
        self._update_confirm()
        await interaction.response.edit_message(view=self)

    @discord.ui.select(
        cls=discord.ui.RoleSelect,
        placeholder="2️⃣ رۆڵی ستاف هەڵبژێرە | Select the staff role to ping",
        row=1,
    )
    async def role_select(self, interaction: discord.Interaction, select: discord.ui.RoleSelect):
        self.chosen_role = select.values[0]
        self._update_confirm()
        await interaction.response.edit_message(view=self)

    def _update_confirm(self):
        for item in self.children:
            if getattr(item, 'custom_id', None) == "reklam_confirm":
                item.disabled = not (self.chosen_channel and self.chosen_role)

    @discord.ui.button(
        label="✅ دروستکردن | Confirm Setup",
        style=discord.ButtonStyle.success,
        disabled=True,
        row=2,
        custom_id="reklam_confirm",
    )
    async def confirm_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        save_reklam_settings(interaction.guild.id, self.chosen_channel.id, self.chosen_role.id)
        cfg = get_reklam_settings(interaction.guild.id)
        custom_text = cfg.get("text", "").strip() if cfg else ""
        for item in self.children:
            item.disabled = True
        embed = discord.Embed(
            color=0x57F287,
            title="✅ دامەزراندنی ریکلام تەواو بوو | Reklam Setup Complete",
            description=(
                "سیستەمی ریکلام بە سەرکەوتوویی دامەزراند.\n"
                "The reklam system has been successfully configured."
            ),
            timestamp=datetime.datetime.utcnow(),
        )
        embed.add_field(
            name="📢 کەناڵ | Channel",
            value=self.chosen_channel.mention,
            inline=True,
        )
        embed.add_field(
            name="👥 رۆڵ | Role",
            value=self.chosen_role.mention,
            inline=True,
        )
        embed.add_field(name="\u200b", value="\u200b", inline=True)
        if custom_text:
            embed.add_field(
                name="✏️ دەقی ئێستا | Current Text",
                value=f"```{custom_text[:300]}```",
                inline=False,
            )
        else:
            embed.add_field(
                name="✏️ دەقی ریکلام | Reklam Text",
                value=(
                    "دەقی تایبەت دانەنراوە — دەقی پێشکەوتووی بنەڕەتی بەکاردێت.\n"
                    "No custom text set — default embed will be used.\n"
                    "*(دەگمەی ✏️ Edit Text بەکاربێنە بۆ گۆڕین | Click ✏️ Edit Text to customize)*"
                ),
                inline=False,
            )
        embed.add_field(
            name="ℹ️ چۆنیەتی کارکردن | How It Works",
            value=(
                f"کاتێک کەسێک `reklam` بنووسێت ئاگادارکردنەوە دەنێردرێت بۆ {self.chosen_channel.mention} "
                f"بە پینگی {self.chosen_role.mention}.\n"
                f"When someone types `reklam`, a notification is sent to {self.chosen_channel.mention} "
                f"pinging {self.chosen_role.mention}."
            ),
            inline=False,
        )
        embed.set_thumbnail(url=interaction.guild.icon.url if interaction.guild.icon else None)
        embed.set_footer(
            text=f"⚙️ Set up by {interaction.user.display_name} · {interaction.guild.name}",
            icon_url=interaction.user.display_avatar.url,
        )
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(
        label="❌ هەڵوەشاندنەوە | Cancel",
        style=discord.ButtonStyle.danger,
        row=2,
    )
    async def cancel_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(
            embed=discord.Embed(color=0xED4245, title="❌ هەڵوەشاندرایەوە | Cancelled"),
            view=self,
        )
        self.stop()

    @discord.ui.button(
        label="✏️ Edit Text",
        style=discord.ButtonStyle.secondary,
        row=3,
    )
    async def edit_text_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Open a modal to set a custom reklam notification message. Use {user} to tag the requester."""
        modal = ReklamTextModal()
        current = get_reklam_settings(interaction.guild.id)
        if current and current.get("text"):
            modal.text_input.default = current["text"]
        await interaction.response.send_modal(modal)


@bot.command(name="setreklam", aliases=["reklamsetup", "setupreklam"])
@commands.has_permissions(manage_guild=True)
async def setreklam_cmd(ctx):
    """Interactive setup — choose the reklam notification channel and staff role."""
    if ctx.guild is None:
        return await ctx.send("Server only. | تەنها لە سێرڤەر.")

    cfg = get_reklam_settings(ctx.guild.id)
    current = ""
    if cfg:
        ch = ctx.guild.get_channel(cfg["channel_id"])
        rl = ctx.guild.get_role(cfg["role_id"])
        current = (
            f"\n\n**دانرایەی ئێستا | Current:** {ch.mention if ch else '`deleted`'} · {rl.mention if rl else '`deleted`'}"
        )

    embed = discord.Embed(
        color=0x5865F2,
        title="⚙️ دامەزراندنی ریکلام | Reklam Setup",
        description=(
            "**١** — کەناڵێک هەڵبژێرە کە ئاگادارکردنەوەکان دەنێردرێن بۆی.\n"
            "**2** — رۆڵی ستافێک هەڵبژێرە کە پینگ دەکرێت.\n"
            "**3** — دەگمەی **تەواوکردن** دابگرە.\n\n"
            "**1** — Select the channel where notifications go.\n"
            "**2** — Select the staff role to ping.\n"
            "**3** — Click **Confirm Setup**." + current
        ),
    )
    view = ReklamSetupView(ctx)
    await ctx.send(embed=embed, view=view)

@setreklam_cmd.error
async def setreklam_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ مووچەی Manage Server پێویستە. | You need Manage Server permission.")


@bot.command(name="removereklam", aliases=["delreklam", "unsetreklam", "reklamremove"])
@commands.has_permissions(manage_guild=True)
async def removereklam_cmd(ctx):
    """Remove the reklam channel/role configuration for this server."""
    if ctx.guild is None:
        return await ctx.send("Server only. | تەنها لە سێرڤەر.")

    cfg = get_reklam_settings(ctx.guild.id)
    if not cfg:
        return await ctx.send(
            "❌ هیچ دانرانێکی ریکلام نییە. | No reklam setup found for this server."
        )

    try:
        conn.execute("DELETE FROM reklam_settings WHERE guild_id=?", (ctx.guild.id,))
        conn.commit()
    except Exception as e:
        return await ctx.send(f"❌ هەڵە: `{e}`")

    embed = discord.Embed(
        color=0xED4245,
        title="🗑️ دانرانی ریکلام لابرا | Reklam Setup Removed",
        description=(
            "✅ دانرانی ریکلام بۆ ئەم سێرڤەرە لابرا.\n"
            "✅ The reklam configuration for this server has been removed.\n\n"
            "بۆ دانرانی دووبارە `!setreklam` بەکاربێنە.\n"
            "Use `!setreklam` to set it up again."
        ),
    )
    embed.set_footer(
        text=f"Removed by {ctx.author.display_name} | لەلایەن {ctx.author.display_name}",
        icon_url=ctx.author.display_avatar.url,
    )
    await ctx.send(embed=embed)

@removereklam_cmd.error
async def removereklam_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ مووچەی Manage Server پێویستە. | You need Manage Server permission.")


@bot.command(name="reklam", aliases=["reklamRequest", "reklam_request"])
async def reklam_cmd(ctx):
    """User requests a reklam — notifies staff in the configured channel."""
    if ctx.guild is None:
        return await ctx.send("Server only. | تەنها لە سێرڤەر.")

    _rk_key = (ctx.guild.id, ctx.author.id)
    _rk_last = reklam_cooldowns.get(_rk_key, 0)
    if time.time() - _rk_last < 30:
        _rk_left = int(30 - (time.time() - _rk_last))
        return await ctx.reply(
            f"⏳ تکایە **{_rk_left}** چرکە چاوەڕێ بە. | Please wait **{_rk_left}s**.",
            mention_author=False,
            delete_after=8,
        )
    reklam_cooldowns[_rk_key] = time.time()

    cfg = get_reklam_settings(ctx.guild.id)

    # ── staff notification — only send if staff channel ≠ command channel ──
    if cfg:
        ch = ctx.guild.get_channel(cfg["channel_id"])
        role = ctx.guild.get_role(cfg["role_id"])
        if ch and ch.id != ctx.channel.id:
            ping = role.mention if role else ""
            notify = discord.Embed(
                color=0xF59E0B,
                title="📣 داوای ریکلامی نوێ | New Reklam Request",
                description=(
                    f"👤 {ctx.author.mention} (`{ctx.author}`)\n"
                    f"📺 {ctx.channel.mention} · <t:{int(ctx.message.created_at.timestamp())}:R>\n\n"
                    "تکایە بچنە کەناڵەکەی و وەڵامی بدەنەوە.\n"
                    "Please go to their channel and help them."
                ),
                timestamp=datetime.datetime.utcnow(),
            )
            notify.set_thumbnail(url=ctx.author.display_avatar.url)
            notify.set_footer(text=ctx.guild.name)
            try:
                await ch.send(content=ping if ping else None, embed=notify)
            except (discord.Forbidden, discord.HTTPException):
                pass
        elif ch and ch.id == ctx.channel.id:
            # Same channel — append staff info as a compact follow-up field
            # so it reads as ONE conversation, not two separate bot messages.
            ping = role.mention if role else ""
            staff_embed = discord.Embed(
                color=0xF59E0B,
                title="📣 داوای ریکلامی نوێ | New Reklam Request",
                description=(
                    f"👤 {ctx.author.mention} (`{ctx.author}`)\n"
                    f"🕐 <t:{int(ctx.message.created_at.timestamp())}:R>\n\n"
                    "Please go to their channel and help them."
                ),
                timestamp=datetime.datetime.utcnow(),
            )
            staff_embed.set_thumbnail(url=ctx.author.display_avatar.url)
            staff_embed.set_footer(text=ctx.guild.name)
            try:
                await ch.send(content=ping if ping else None, embed=staff_embed)
            except (discord.Forbidden, discord.HTTPException):
                pass


# ═══════════════════════ STAFF DONE / ACTIVITY ═══════════════════════

class StaffDoneView(discord.ui.View):
    """Persistent Done button — survives restarts, never fails, always refreshes itself."""
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="✅ Done",
        style=discord.ButtonStyle.success,
        custom_id="staff_done_btn"
    )
    async def done_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Defer IMMEDIATELY — prevents Discord 3-second timeout "interaction failed"
        try:
            await interaction.response.defer(ephemeral=True)
        except Exception:
            pass

        # Log the press to DB
        try:
            log_staff_done(interaction.guild.id, interaction.user.id, interaction.user.display_name)
        except Exception:
            pass

        # Send ephemeral thank-you only visible to the presser
        try:
            await interaction.followup.send(
                f"### 🎉 {interaction.user.mention}\n"
                "**دەستت خۆش! باشی کردووت — سوپاس! 💪**\n"
                "ئومێدوارین بەردەوام بیت و مەیەوە بیجێبهێڵیت!\n\n"
                "**Hey, you did great — thank you! 💪**\n"
                "Keep it up and make sure you stay consistent!",
                ephemeral=True,
            )
        except Exception:
            pass

        # Delete the old panel message so a fresh one replaces it
        try:
            await interaction.message.delete()
        except Exception:
            pass

        # Post a brand-new panel with a fresh persistent button
        try:
            fresh_embed = discord.Embed(
                color=0x57F287,
                title="📣 دەیلی ستاف | Staff Daily",
                description=(
                    "سڵاو! 👋\n\n"
                    "**خۆشحاڵبووین بینینت چالاکیت دەکەیت! 🌟**\n"
                    "دڵنیا بە کە ئەمڕۆ ڕیکلامەکانت ئەنجام دەدەیت — مەیەوە بیجێبهێڵیت!\n\n"
                    "**Hey! Glad to see you doing your daily reklaams! 🌟**\n"
                    "Make sure you won't forget to do them today!\n\n"
                    "⬇️ کاتێک تەواوت کرد دەگمەی **Done** دابگرە.\n"
                    "⬇️ When you're done, press **Done** below."
                ),
            )
            if interaction.guild.icon:
                fresh_embed.set_thumbnail(url=interaction.guild.icon.url)
            fresh_embed.set_footer(text=f"{interaction.guild.name} · Staff Team")
            await interaction.channel.send(embed=fresh_embed, view=StaffDoneView())
        except Exception:
            pass

        # Post to the done-log channel if configured
        try:
            log_cid = get_done_log_channel(interaction.guild.id)
            if log_cid:
                log_ch = interaction.guild.get_channel(int(log_cid))
                if log_ch:
                    now_str = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
                    log_embed = discord.Embed(
                        color=0x57F287,
                        title="✅ ستافێک Done کرد | Staff Done",
                        description=(
                            f"👤 **{interaction.user.display_name}** ({interaction.user.mention})\n"
                            f"🕐 `{now_str}`\n"
                            f"📌 کەناڵ | Channel: {interaction.channel.mention}"
                        ),
                        timestamp=datetime.datetime.utcnow(),
                    )
                    log_embed.set_thumbnail(url=interaction.user.display_avatar.url)
                    log_embed.set_footer(text=interaction.guild.name)
                    await log_ch.send(embed=log_embed)
        except Exception:
            pass
@bot.command(name="staffdone", aliases=["donepanel"])
@commands.has_permissions(manage_guild=True)
async def staffdone_cmd(ctx):
    """Post the staff-done panel with a Done button."""
    if ctx.guild is None:
        return await ctx.send("Server only. | تەنها لە سێرڤەر.")

    embed = discord.Embed(
        color=0x57F287,
        title="📣 دەیلی ستاف | Staff Daily",
        description=(
            "سڵاو! 👋\n\n"
            "**خۆشحاڵبووین بینینت چالاکیت دەکەیت! 🌟**\n"
            "دڵنیا بە کە ئەمڕۆ ڕیکلامەکانت ئەنجام دەدەیت — مەیەوە بیجێبهێڵیت!\n\n"
            "**Hey! Glad to see you doing your daily reklaams! 🌟**\n"
            "Make sure you won't forget to do them today!\n\n"
            "⬇️ کاتێک تەواوت کرد دەگمەی **Done** دابگرە.\n"
            "⬇️ When you're done, press **Done** below."
        ),
    )
    embed.set_footer(text=f"{ctx.guild.name} · Staff Team")
    if ctx.guild.icon:
        embed.set_thumbnail(url=ctx.guild.icon.url)

    await ctx.send(embed=embed, view=StaffDoneView())

@staffdone_cmd.error
async def staffdone_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ مووچەی Manage Server پێویستە. | You need Manage Server permission.")


@bot.command(name="setdonelog", aliases=["setdonelogchannel"])
@commands.has_permissions(manage_guild=True)
async def setdonelog_cmd(ctx, channel: discord.TextChannel = None):
    """Set the channel where Done-button activity is logged."""
    if ctx.guild is None:
        return await ctx.send("Server only. | تەنها لە سێرڤەر.")
    target = channel or ctx.channel
    save_done_log_channel(ctx.guild.id, target.id)
    embed = discord.Embed(
        color=0x57F287,
        title="✅ Done Log Channel Set | کەناڵی لۆگی Done دیاری کرا",
        description=(
            f"📌 {target.mention}\n\n"
            "ئێستا هەر کەسێک دەگمەی **Done** دابگرێت، لۆگەکە لەم کەناڵەدا دەردەکەوێت.\n"
            "Now every time someone clicks **Done**, a log will appear in this channel."
        ),
    )
    embed.set_footer(text=ctx.guild.name)
    await ctx.send(embed=embed)

@setdonelog_cmd.error
async def setdonelog_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ مووچەی Manage Server پێویستە. | You need Manage Server permission.")
    elif isinstance(error, commands.BadArgument):
        await ctx.send("❌ کەناڵی دروست نەدیتووم. | Invalid channel.")


@bot.command(name="staffdonelog", aliases=["doneloglist", "donelog"])
@commands.has_permissions(manage_guild=True)
async def staffdonelog_cmd(ctx, period: str = "today"):
    """Show the done log. Period: today (default), week, all."""
    if ctx.guild is None:
        return await ctx.send("Server only. | تەنها لە سێرڤەر.")

    now = datetime.datetime.utcnow()
    if period.lower() in ("week", "w"):
        week_start = (now - datetime.timedelta(days=now.weekday())).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        since_iso = week_start.isoformat()
        period_label = "ئەم هەفتەیە | This Week"
    elif period.lower() in ("all", "a"):
        since_iso = "2000-01-01T00:00:00"
        period_label = "هەموو کات | All Time"
    else:
        since_iso = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        period_label = "ئەمڕۆ | Today"

    rows = get_staff_done_since(ctx.guild.id, since_iso)

    if not rows:
        embed = discord.Embed(
            color=0xED4245,
            title=f"📋 لۆگی Done — {period_label}",
            description=(
                "**هیچ تۆمارێک نییە.**\n"
                "No records found for this period."
            ),
        )
        embed.set_footer(text=f"UTC · {ctx.guild.name}")
        return await ctx.send(embed=embed)

    lines = []
    for i, r in enumerate(rows, 1):
        member = ctx.guild.get_member(r["user_id"])
        mention = member.mention if member else f"**{r['display_name']}**"
        t = r["done_at"][:16].replace("T", " ")
        lines.append(f"`{i}.` {mention} — `{t} UTC`")

    description = "\n".join(lines)
    # Discord embed description cap is 4096 chars — trim gracefully
    if len(description) > 4000:
        description = description[:3990] + "\n*…و زیاتر | …and more*"

    embed = discord.Embed(
        color=0x5865F2,
        title=f"📋 لۆگی Done — {period_label}",
        description=description,
    )
    embed.set_footer(
        text=f"کۆی تۆمارەکان: {len(rows)} | Total entries: {len(rows)} · {ctx.guild.name}"
    )
    if ctx.guild.icon:
        embed.set_thumbnail(url=ctx.guild.icon.url)
    await ctx.send(embed=embed)

@staffdonelog_cmd.error
async def staffdonelog_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ مووچەی Manage Server پێویستە. | You need Manage Server permission.")


@bot.command(name="dailyactive", aliases=["staffdailyactive", "activedaily"])
@commands.has_permissions(manage_guild=True)
async def staffdailyactive_cmd(ctx):
    """Show which staff members clicked Done today."""
    if ctx.guild is None:
        return await ctx.send("Server only. | تەنها لە سێرڤەر.")

    today_start = datetime.datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    rows = get_staff_done_since(ctx.guild.id, today_start)

    if not rows:
        embed = discord.Embed(
            color=0xED4245,
            title="📊 ستافی چالاکی ئەمڕۆ | Today's Active Staff",
            description=(
                "**هیچ ستافێک ئەمڕۆ دەگمەی Done نەداگرتووە.**\n"
                "No staff member has clicked Done today yet."
            ),
        )
        embed.set_footer(text=f"UTC · {ctx.guild.name}")
        return await ctx.send(embed=embed)

    seen = {}
    for r in rows:
        uid = r["user_id"]
        if uid not in seen:
            seen[uid] = {"name": r["display_name"], "first": r["done_at"], "count": 0}
        seen[uid]["count"] += 1

    lines = []
    for i, (uid, info) in enumerate(seen.items(), 1):
        member = ctx.guild.get_member(uid)
        mention = member.mention if member else f"**{info['name']}**"
        t = info["first"][:16].replace("T", " ")
        lines.append(f"`{i}.` {mention} — ✅ x{info['count']} · `{t} UTC`")

    embed = discord.Embed(
        color=0x57F287,
        title=f"📊 ستافی چالاکی ئەمڕۆ | Today's Active Staff — {ctx.guild.name}",
        description="\n".join(lines),
    )
    embed.set_footer(text=f"کۆی: {len(seen)} ستاف | Total: {len(seen)} staff · UTC today")
    if ctx.guild.icon:
        embed.set_thumbnail(url=ctx.guild.icon.url)
    await ctx.send(embed=embed)

@staffdailyactive_cmd.error
async def staffdailyactive_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ مووچەی Manage Server پێویستە. | You need Manage Server permission.")


@bot.command(name="staffweekly", aliases=["staffweeklyactive", "activeweekly"])
@commands.has_permissions(manage_guild=True)
async def staffweeklyactive_cmd(ctx):
    """Show which staff members clicked Done this week (Mon–today UTC)."""
    if ctx.guild is None:
        return await ctx.send("Server only. | تەنها لە سێرڤەر.")

    now = datetime.datetime.utcnow()
    week_start = (now - datetime.timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    rows = get_staff_done_since(ctx.guild.id, week_start.isoformat())

    if not rows:
        embed = discord.Embed(
            color=0xED4245,
            title="📊 ستافی چالاکی ئەم هەفتەیە | This Week's Active Staff",
            description=(
                "**هیچ ستافێک ئەم هەفتەیە دەگمەی Done نەداگرتووە.**\n"
                "No staff member has clicked Done this week yet."
            ),
        )
        embed.set_footer(text=f"UTC · {ctx.guild.name}")
        return await ctx.send(embed=embed)

    seen = {}
    for r in rows:
        uid = r["user_id"]
        if uid not in seen:
            seen[uid] = {"name": r["display_name"], "count": 0, "days": set()}
        seen[uid]["count"] += 1
        seen[uid]["days"].add(r["done_at"][:10])

    lines = []
    for i, (uid, info) in enumerate(seen.items(), 1):
        member = ctx.guild.get_member(uid)
        mention = member.mention if member else f"**{info['name']}**"
        day_count = len(info["days"])
        lines.append(f"`{i}.` {mention} — ✅ x{info['count']} · 📅 {day_count} رۆژ | {day_count} day(s)")

    week_label = week_start.strftime("%b %d")
    embed = discord.Embed(
        color=0x5865F2,
        title=f"📊 ستافی چالاکی ئەم هەفتەیە | This Week's Active Staff — {ctx.guild.name}",
        description="\n".join(lines),
    )
    embed.set_footer(text=f"کۆی: {len(seen)} ستاف | Total: {len(seen)} staff · Week from {week_label} UTC")
    if ctx.guild.icon:
        embed.set_thumbnail(url=ctx.guild.icon.url)
    await ctx.send(embed=embed)

@staffweeklyactive_cmd.error
async def staffweeklyactive_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ مووچەی Manage Server پێویستە. | You need Manage Server permission.")



# ═══════════════════════ STAFF ANN / WARN ═══════════════════════

@bot.command(name="staffann")
@commands.has_permissions(manage_messages=True)
async def staffann_cmd(ctx, *, text: str = None):
    if ctx.guild is None:
        return await ctx.send("Server only. | تەنها لە سێرڤەر.")
    if not text:
        return await ctx.send("بەکارهێنان: `!staffann <پەیام>` | Usage: `!staffann <message>`")
    staff_kw = ["staff", "admin", "mod", "owner", "manager", "helper",
                "ستاف", "ئادمین", "مۆد", "موڵکدار", "بەڕێوەبەر"]
    pings = " ".join(
        r.mention for r in ctx.guild.roles
        if any(kw in r.name.lower() for kw in staff_kw) and r.name != "@everyone"
    )
    embed = discord.Embed(
        color=0xF59E0B,
        title="📢 ئاگادارکردنەوەی ستاف | Staff Announcement",
        description=text,
        timestamp=datetime.datetime.utcnow(),
    )
    embed.set_footer(text=f"لەلایەن | By: {ctx.author.display_name}", icon_url=ctx.author.display_avatar.url)
    try:
        await ctx.message.delete()
    except Exception:
        pass
    await ctx.send(content=pings if pings else None, embed=embed)

@staffann_cmd.error
async def staffann_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ مووچەی Manage Messages پێویستە. | You need Manage Messages permission.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("بەکارهێنان: `!staffann <پەیام>` | Usage: `!staffann <message>`")


@bot.command(name="staffwarn")
@commands.has_permissions(manage_messages=True)
async def staffwarn_cmd(ctx, member: discord.Member = None, *, reason: str = "No reason provided | هیچ هۆکارێک نەدراوە"):
    if ctx.guild is None:
        return await ctx.send("Server only. | تەنها لە سێرڤەر.")
    if member is None:
        return await ctx.send("بەکارهێنان: `!staffwarn @ئەندام [هۆکار]` | Usage: `!staffwarn @member [reason]`")
    if member.bot:
        return await ctx.send("❌ ناتوانیت بۆتێک ئاگادار بکەیتەوە. | You can't warn a bot.")
    with get_db() as _conn:
        row = _conn.execute(
            "SELECT count FROM warnings WHERE guild_id=? AND user_id=?",
            (ctx.guild.id, member.id)
        ).fetchone()
        new_count = (row["count"] if row else 0) + 1
        _conn.execute(
            "INSERT INTO warnings (guild_id, user_id, count) VALUES (?,?,?) "
            "ON CONFLICT(guild_id,user_id) DO UPDATE SET count=excluded.count",
            (ctx.guild.id, member.id, new_count)
        )
        _conn.commit()
    staff_kw = ["staff", "admin", "mod", "owner", "manager", "helper",
                "ستاف", "ئادمین", "مۆد", "موڵکدار", "بەڕێوەبەر"]
    pings = " ".join(
        r.mention for r in ctx.guild.roles
        if any(kw in r.name.lower() for kw in staff_kw) and r.name != "@everyone"
    )
    embed = discord.Embed(
        color=0xED4245,
        title="⚠️ ئاگاداری ستاف | Staff Warning",
        description=(
            f"**ئەندام | Member:** {member.mention}\n"
            f"**هۆکار | Reason:** {reason}\n"
            f"**کۆی ئاگاداریەکان | Total Warnings:** `{new_count}`\n"
            f"**لەلایەن | By:** {ctx.author.mention}"
        ),
        timestamp=datetime.datetime.utcnow(),
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.set_footer(text=f"{ctx.guild.name}")
    try:
        await member.send(embed=embed)
    except Exception:
        pass
    await ctx.send(content=pings if pings else None, embed=embed)

@staffwarn_cmd.error
async def staffwarn_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ مووچەی Manage Messages پێویستە. | You need Manage Messages permission.")
    elif isinstance(error, commands.MemberNotFound):
        await ctx.send("❌ ئەندام نەدۆزرایەوە. | Member not found.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("بەکارهێنان: `!staffwarn @ئەندام [هۆکار]` | Usage: `!staffwarn @member [reason]`")


# ═══════════════════════ TRIVIA BATTLE SYSTEM ═══════════════════════

_trivia_sessions = {}
_trivia_scores_cache = {}

async def _fetch_trivia_questions(amount=5, difficulty="medium"):
    url = f"https://opentdb.com/api.php?amount={amount}&difficulty={difficulty}&type=multiple"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("response_code") == 0:
                        return data["results"]
    except Exception:
        pass
    return []

def _decode_trivia(text):
    return html_module.unescape(text)


class TriviaJoinView(discord.ui.View):
    def __init__(self, host_id, channel_id):
        super().__init__(timeout=30)
        self.host_id = host_id
        self.channel_id = channel_id
        self.players = {host_id}

    @discord.ui.button(label="✅ بەشداربوون | Join", style=discord.ButtonStyle.success)
    async def join_btn(self, interaction, button):
        if self.channel_id not in _trivia_sessions:
            await interaction.response.send_message("❌ یاری بەردەوام نییە. | No active game.", ephemeral=True)
            return
        uid = interaction.user.id
        if uid in self.players:
            await interaction.response.send_message("✅ پێشتر بەشداربووی. | Already joined!", ephemeral=True)
        else:
            self.players.add(uid)
            await interaction.response.send_message(
                f"✅ بەشداربووی! کۆی یاریزانان: **{len(self.players)}** | Joined! Players: **{len(self.players)}**",
                ephemeral=True
            )

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True


class TriviaAnswerView(discord.ui.View):
    def __init__(self, correct, choices, channel_id, players):
        super().__init__(timeout=20)
        self.correct = correct
        self.channel_id = channel_id
        self.players = players
        self.answered = {}
        for label in choices:
            btn = discord.ui.Button(label=label[:80], style=discord.ButtonStyle.primary)
            btn.callback = self._make_callback(label)
            self.add_item(btn)

    def _make_callback(self, label):
        async def callback(interaction):
            uid = interaction.user.id
            if uid not in self.players:
                await interaction.response.send_message("❌ تۆ بەشی ئەم یاریە نیتی. | You're not in this game.", ephemeral=True)
                return
            if uid in self.answered:
                await interaction.response.send_message("✅ پێشتر وەڵامت داوە. | Already answered!", ephemeral=True)
                return
            self.answered[uid] = label
            is_correct = (label == self.correct)
            if is_correct:
                _trivia_scores_cache.setdefault(self.channel_id, {})
                _trivia_scores_cache[self.channel_id][uid] = _trivia_scores_cache[self.channel_id].get(uid, 0) + 1
            await interaction.response.send_message(
                "✅ وەڵامی دروست! | Correct! +1" if is_correct else "❌ هەڵە! | Wrong!",
                ephemeral=True
            )
            if len(self.answered) >= len(self.players):
                self.stop()
        return callback

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        self.stop()


@bot.command(name="trivia", aliases=["triva"])
async def trivia_cmd(ctx, difficulty="medium"):
    if ctx.channel.id in _trivia_sessions:
        return await ctx.send(
            "⚠️ یاری تریڤیا بەردەوامە لەم کەناڵەدا! | A trivia game is already running here!",
            delete_after=8
        )
    if difficulty not in ("easy", "medium", "hard"):
        difficulty = "medium"
    _trivia_sessions[ctx.channel.id] = {"state": "lobby"}
    _trivia_scores_cache[ctx.channel.id] = {}
    view = TriviaJoinView(ctx.author.id, ctx.channel.id)
    lobby_embed = discord.Embed(
        color=0x5865F2,
        title="🧠 تریڤیای چوارگەزینەیی | Multiple-Choice Trivia Battle!",
        description=(
            f"**کیشەی | Difficulty:** `{difficulty}`\n\n"
            "دوگمەی خوارەوە بدە بۆ بەشداربوون!\n"
            "Click the button below to join!\n\n"
            "⏳ یاری دەست دەکات لە **30** چرکە...\n"
            "⏳ Game starts in **30** seconds..."
        ),
    )
    lobby_embed.set_footer(text=f"میوانداری | Host: {ctx.author.display_name}")
    msg = await ctx.send(embed=lobby_embed, view=view)
    for secs_left in range(25, 0, -5):
        await asyncio.sleep(5)
        if ctx.channel.id not in _trivia_sessions:
            return
        try:
            lobby_embed.description = (
                f"**کیشەی | Difficulty:** `{difficulty}`\n\n"
                "دوگمەی خوارەوە بدە بۆ بەشداربوون! | Click the button below to join!\n\n"
                f"⏳ یاری دەست دەکات لە **{secs_left}** چرکە... | Game starts in **{secs_left}** seconds...\n\n"
                f"👥 یاریزانان | Players: **{len(view.players)}**"
            )
            await msg.edit(embed=lobby_embed)
        except Exception:
            pass
    await asyncio.sleep(5)
    if ctx.channel.id not in _trivia_sessions:
        return
    view.stop()
    players = view.players
    if len(players) < 1:
        _trivia_sessions.pop(ctx.channel.id, None)
        _trivia_scores_cache.pop(ctx.channel.id, None)
        return await ctx.send("❌ هیچ یاریزانێک بەشداری نەکرد. | No players joined.")
    questions = await _fetch_trivia_questions(amount=5, difficulty=difficulty)
    if not questions:
        _trivia_sessions.pop(ctx.channel.id, None)
        _trivia_scores_cache.pop(ctx.channel.id, None)
        return await ctx.send("❌ نەتوانرا پرسیارەکان بارکرێن. دووبارە هەوڵبدەرەوە. | Failed to load questions. Try again.")
    await ctx.send(
        f"🎮 یاری دەستدەکات بۆ **{len(players)}** یاریزان! | Game starting for **{len(players)}** player(s)!\n"
        + " ".join(f"<@{uid}>" for uid in players)
    )
    await asyncio.sleep(2)
    for i, q in enumerate(questions, 1):
        if ctx.channel.id not in _trivia_sessions:
            return
        question_text = _decode_trivia(q["question"])
        correct = _decode_trivia(q["correct_answer"])
        choices = [_decode_trivia(a) for a in q["incorrect_answers"]] + [correct]
        random.shuffle(choices)
        q_embed = discord.Embed(
            color=0xF59E0B,
            title=f"❓ پرسیار {i}/5 | Question {i}/5",
            description=f"**{question_text}**",
        )
        q_embed.set_footer(text=f"پۆل: {_decode_trivia(q['category'])} | {difficulty}")
        answer_view = TriviaAnswerView(correct, choices, ctx.channel.id, players)
        _q_msg = await ctx.send(embed=q_embed, view=answer_view)
        await answer_view.wait()
        try:
            await _q_msg.delete()
        except Exception:
            pass
    session_scores = _trivia_scores_cache.pop(ctx.channel.id, {})
    _trivia_sessions.pop(ctx.channel.id, None)
    if ctx.guild:
        with get_db() as _conn:
            for uid, score in session_scores.items():
                _conn.execute(
                    "INSERT INTO trivia_scores (guild_id, user_id, score) VALUES (?,?,?) "
                    "ON CONFLICT(guild_id,user_id) DO UPDATE SET score=score+excluded.score",
                    (ctx.guild.id, uid, score)
                )
            _conn.commit()
    if not session_scores:
        return await ctx.send("🎮 یاری کۆتایی هات! هیچکەس هیچ پرسیارێکی وەڵام نەدا. | Game over! Nobody scored.")
    sorted_scores = sorted(session_scores.items(), key=lambda x: x[1], reverse=True)
    winner_id, winner_score = sorted_scores[0]
    lines = [f"`{i}.` <@{uid}> — **{sc}** خاڵ | pts" for i, (uid, sc) in enumerate(sorted_scores, 1)]
    result_embed = discord.Embed(
        color=0x57F287,
        title="🏆 کۆتایی تریڤیا | Trivia Results",
        description="\n".join(lines),
    )
    result_embed.add_field(name="🥇 بەرنجبەر | Winner", value=f"<@{winner_id}> بە **{winner_score}** خاڵ | pts")
    await ctx.send(embed=result_embed)


@bot.command(name="triviastop")
@commands.has_permissions(manage_messages=True)
async def triviastop_cmd(ctx):
    if ctx.channel.id not in _trivia_sessions:
        return await ctx.send("❌ هیچ یاری تریڤیایەکی چالاک نییە لەم کەناڵەدا. | No active trivia game here.", delete_after=8)
    _trivia_sessions.pop(ctx.channel.id, None)
    _trivia_scores_cache.pop(ctx.channel.id, None)
    await ctx.send("🛑 یاری تریڤیا وەستاندرا. | Trivia game stopped.")

@triviastop_cmd.error
async def triviastop_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ مووچەی Manage Messages پێویستە. | You need Manage Messages permission.")


@bot.command(name="triviascore")
async def triviascore_cmd(ctx, member: discord.Member = None):
    if ctx.guild is None:
        return await ctx.send("Server only. | تەنها لە سێرڤەر.")
    target = member or ctx.author
    with get_db() as _conn:
        row = _conn.execute(
            "SELECT score FROM trivia_scores WHERE guild_id=? AND user_id=?",
            (ctx.guild.id, target.id)
        ).fetchone()
    score = row["score"] if row else 0
    embed = discord.Embed(
        color=0x5865F2,
        title="🧠 خاڵی تریڤیا | Trivia Score",
        description=f"{target.mention} — **{score}** خاڵ | pts"
    )
    await ctx.send(embed=embed)


@bot.command(name="trivialeaderboard", aliases=["trivialb", "triviatop"])
async def trivialeaderboard_cmd(ctx):
    if ctx.guild is None:
        return await ctx.send("Server only. | تەنها لە سێرڤەر.")
    with get_db() as _conn:
        rows = _conn.execute(
            "SELECT user_id, score FROM trivia_scores WHERE guild_id=? ORDER BY score DESC LIMIT 10",
            (ctx.guild.id,)
        ).fetchall()
    if not rows:
        return await ctx.send("❌ تا ئێستا هیچ یاریزانێک خاڵی نەکەوتووە. | No scores yet.")
    medals = ["🥇", "🥈", "🥉"]
    lines = []
    for i, row in enumerate(rows):
        medal = medals[i] if i < 3 else f"`{i+1}.`"
        member = ctx.guild.get_member(row["user_id"])
        name = member.display_name if member else f"User {row['user_id']}"
        lines.append(f"{medal} **{name}** — {row['score']} خاڵ | pts")
    embed = discord.Embed(
        color=0xF59E0B,
        title=f"🏆 لیستی تریڤیا | Trivia Leaderboard — {ctx.guild.name}",
        description="\n".join(lines),
    )
    embed.set_footer(text=f"Top {len(rows)} players")
    await ctx.send(embed=embed)


# ═══════════════════════ AUTO-ROLE SYSTEM ═══════════════════════

@bot.command(name="setautorole")
@commands.has_permissions(manage_roles=True)
async def setautorole_cmd(ctx, *, role_input: str = None):
    if ctx.guild is None:
        return await ctx.send("Server only. | تەنها لە سێرڤەر.")
    if not role_input:
        return await ctx.send("بەکارهێنان: `!setautorole @رۆڵ / ناوی رۆڵ / ID` | Usage: `!setautorole @role / role name / role ID`")
    role_input = role_input.strip()
    role = None
    mention_match = re.match(r'<@&(\d+)>', role_input)
    if mention_match:
        role = ctx.guild.get_role(int(mention_match.group(1)))
    if not role and role_input.isdigit():
        role = ctx.guild.get_role(int(role_input))
    if not role:
        role = discord.utils.find(lambda r: r.name.lower() == role_input.lower(), ctx.guild.roles)
    if not role:
        return await ctx.send(f"❌ رۆڵی **{role_input}** نەدۆزرایەوە. | Role **{role_input}** not found.")
    if role >= ctx.guild.me.top_role:
        return await ctx.send("❌ ئەو رۆڵە بەرزتر یان یەکسانە لە رۆڵی منە. | That role is >= mine.")
    with get_db() as _conn:
        _conn.execute(
            "INSERT INTO autorole_settings (guild_id, role_id) VALUES (?,?) "
            "ON CONFLICT(guild_id) DO UPDATE SET role_id=excluded.role_id",
            (ctx.guild.id, role.id)
        )
        _conn.commit()
    embed = discord.Embed(
        color=0x57F287,
        title="✅ ئۆتۆرۆڵ دانراو | Auto-Role Set",
        description=(
            f"رۆڵی **{role.name}** دادەنرێت بۆ هەموو ئەندامی نوێ بە شێوەی خۆکار.\n"
            f"Role **{role.name}** will be given to every new member automatically."
        ),
    )
    embed.set_footer(text=f"Set by {ctx.author.display_name}")
    await ctx.send(embed=embed)

@setautorole_cmd.error
async def setautorole_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ مووچەی Manage Roles پێویستە. | You need Manage Roles permission.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("بەکارهێنان: `!setautorole @رۆڵ / ناوی رۆڵ / ID`")


@bot.command(name="removeautorole")
@commands.has_permissions(manage_roles=True)
async def removeautorole_cmd(ctx):
    if ctx.guild is None:
        return await ctx.send("Server only. | تەنها لە سێرڤەر.")
    with get_db() as _conn:
        row = _conn.execute("SELECT role_id FROM autorole_settings WHERE guild_id=?", (ctx.guild.id,)).fetchone()
        if not row:
            return await ctx.send("❌ هیچ ئۆتۆرۆڵێک دانەنراوە. | No auto-role is set.")
        _conn.execute("DELETE FROM autorole_settings WHERE guild_id=?", (ctx.guild.id,))
        _conn.commit()
    await ctx.send("✅ ئۆتۆرۆڵ لادرا. | Auto-role has been removed.")

@removeautorole_cmd.error
async def removeautorole_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ مووچەی Manage Roles پێویستە. | You need Manage Roles permission.")


@bot.command(name="autorole")
async def autorole_cmd(ctx):
    if ctx.guild is None:
        return await ctx.send("Server only. | تەنها لە سێرڤەر.")
    with get_db() as _conn:
        row = _conn.execute("SELECT role_id FROM autorole_settings WHERE guild_id=?", (ctx.guild.id,)).fetchone()
    if not row:
        return await ctx.send("❌ هیچ ئۆتۆرۆڵێک دانەنراوە. | No auto-role is set.")
    role = ctx.guild.get_role(row["role_id"])
    if not role:
        return await ctx.send("⚠️ رۆڵەکە سڕدراوەتەوە. تکایە `!setautorole` دووبارە بەکاربهێنە. | The saved role was deleted. Use `!setautorole` again.")
    embed = discord.Embed(
        color=0x5865F2,
        title="🎭 ئۆتۆرۆڵی ئێستا | Current Auto-Role",
        description=f"{role.mention} (`{role.id}`)"
    )
    await ctx.send(embed=embed)


# ═══════════════════════ SETUP LINK / LINK SYSTEM ═══════════════════════

# ── Helpers ────────────────────────────────────────────────────────────────────

def _get_link_settings(guild_id: int):
    with get_db() as _conn:
        # migrate: add alignment column if missing
        try:
            _conn.execute("ALTER TABLE link_settings ADD COLUMN alignment TEXT DEFAULT 'left'")
            _conn.commit()
        except Exception:
            pass
        row = _conn.execute(
            "SELECT label, url, alignment FROM link_settings WHERE guild_id=?", (guild_id,)
        ).fetchone()
    return dict(row) if row else None

def _save_link_settings(guild_id: int, label: str, url: str, alignment: str = "left"):
    alignment = alignment.strip().lower()
    if alignment not in ("left", "center", "right"):
        alignment = "left"
    with get_db() as _conn:
        _conn.execute(
            "INSERT INTO link_settings (guild_id, label, url, alignment) VALUES (?,?,?,?) "
            "ON CONFLICT(guild_id) DO UPDATE SET label=excluded.label, url=excluded.url, alignment=excluded.alignment",
            (guild_id, label, url, alignment)
        )
        _conn.commit()

def _delete_link_settings(guild_id: int):
    with get_db() as _conn:
        _conn.execute("DELETE FROM link_settings WHERE guild_id=?", (guild_id,))
        _conn.commit()

def _build_link_panel_embed(guild, link):
    """Build the main !setuplink panel embed showing current settings."""
    if link:
        _purl = link['url']
        _pdisplay = f"<#{_purl}>" if _purl.isdigit() else _purl
        _align = (link.get('alignment') or 'left').capitalize()
        current = (
            f"**📝 ناو | Label:** `{link['label']}`\n"
            f"**🔗 لینک / Channel:** {_pdisplay}\n"
            f"**↔️ Alignment:** `{_align}`"
        )
    else:
        current = "❌ ھیچ لینکەک دانەنراوە. | No link set yet."
    embed = discord.Embed(
        color=0x5865F2,
        title="🔗 دامەزراندنی لینک | Link Setup",
        description=(
            "دوگمەکان بەکاربھەنە بۆ دانانی لینکەکەت.\n"
            "Use the buttons below to manage your server link.\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"{current}\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━"
        ),
    )
    embed.set_footer(
        text=f"{guild.name} · !link بنووسە بۆ پیشاندانی لینک | Type !link to show it",
        icon_url=guild.icon.url if guild.icon else None,
    )
    return embed


# ── Modal ──────────────────────────────────────────────────────────────────────

class LinkEditModal(discord.ui.Modal, title="🔗 دانانی لینک | Set Link"):
    """Modal with Label, URL, and Alignment fields — pre-filled with current values."""

    link_label = discord.ui.TextInput(
        label="ناو | Label",
        placeholder="بۆ نموونە: سێرڤەری ئێمە | e.g. Our Server",
        max_length=100,
        required=True,
    )
    link_url = discord.ui.TextInput(
        label="URL / Channel ID (https:// or digits)",
        placeholder="https://discord.gg/yourserver\nOR just paste a channel ID (digits only)",
        max_length=2000,
        style=discord.TextStyle.long,
        required=True,
    )
    link_alignment = discord.ui.TextInput(
        label="Alignment — ڕیزکردن (left / center / right)",
        placeholder="left   یان   center   یان   right",
        max_length=10,
        required=False,
        default="left",
    )

    def __init__(self, guild_id: int, view: "LinkSetupView"):
        super().__init__()
        self.guild_id = guild_id
        self.parent_view = view
        existing = _get_link_settings(guild_id)
        if existing:
            self.link_label.default     = existing["label"] or ""
            self.link_url.default       = existing["url"] or ""
            self.link_alignment.default = existing.get("alignment") or "left"

    async def on_submit(self, interaction: discord.Interaction):
        label     = self.link_label.value.strip()
        url       = self.link_url.value.strip()
        alignment = self.link_alignment.value.strip().lower() or "left"
        if alignment not in ("left", "center", "right"):
            alignment = "left"
        # Allow ANY text — URL, channel ID, or rich Discord-formatted text
        _save_link_settings(self.guild_id, label, url, alignment)
        link = _get_link_settings(self.guild_id)
        new_embed = _build_link_panel_embed(interaction.guild, link)
        await interaction.response.edit_message(embed=new_embed, view=self.parent_view)


# ── View ───────────────────────────────────────────────────────────────────────

class LinkSetupView(discord.ui.View):
    """Interactive panel for !setuplink with 3 buttons."""

    def __init__(self, guild_id: int):
        super().__init__(timeout=300)
        self.guild_id = guild_id

    @discord.ui.button(
        label="✏️ دانان / دەستکاریکردنی لینک | Set / Edit Link",
        style=discord.ButtonStyle.primary,
        row=0,
    )
    async def btn_edit(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not (interaction.user.guild_permissions.manage_guild or interaction.user == interaction.guild.owner):
            return await interaction.response.send_message("❌ مووچەی Manage Server پێویستە. | You need Manage Server permission.", ephemeral=True)
        try:
            await interaction.response.send_modal(LinkEditModal(self.guild_id, self))
        except Exception as e:
            try:
                await interaction.response.send_message(f"❌ هەڵە | Error: {e}", ephemeral=True)
            except Exception:
                await interaction.followup.send(f"❌ هەڵە | Error: {e}", ephemeral=True)
    @discord.ui.button(
        label="🔗 سەیرکردنی لینکی ئێستا | View Current Link",
        style=discord.ButtonStyle.secondary,
        row=1,
    )
    async def btn_view(self, interaction: discord.Interaction, button: discord.ui.Button):
        link = _get_link_settings(self.guild_id)
        if not link:
            await interaction.response.send_message(
                "❌ هیچ لینکێک دانەنراوە. دوگمەی Edit بدە بۆ دانانی. | No link set yet. Click Edit to set one.",
                ephemeral=True
            )
        else:
            _vurl = link['url']
            _vcontent = f"<#{_vurl}>" if _vurl.isdigit() else _vurl
            await interaction.response.send_message(_vcontent, ephemeral=True)

    @discord.ui.button(
        label="🗑️ سڕینەوەی لینک | Remove Link",
        style=discord.ButtonStyle.danger,
        row=2,
    )
    async def btn_remove(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not (interaction.user.guild_permissions.manage_guild or interaction.user == interaction.guild.owner):
            return await interaction.response.send_message("❌ مووچەی Manage Server پێویستە. | You need Manage Server permission.", ephemeral=True)
        link = _get_link_settings(self.guild_id)
        if not link:
            return await interaction.response.send_message(
                "❌ هیچ لینکێک دانەنراوە. | No link is set.", ephemeral=True
            )
        _delete_link_settings(self.guild_id)
        new_embed = _build_link_panel_embed(interaction.guild, None)
        await interaction.response.edit_message(embed=new_embed, view=self)
        await interaction.followup.send("✅ لینک سڕدرایەوە. | Link removed.", ephemeral=True)


# ── Commands ───────────────────────────────────────────────────────────────────

@bot.command(name="setuplink", aliases=["linksetup", "setlink"])
@commands.has_permissions(manage_guild=True)
async def setuplink_cmd(ctx):
    """Open the interactive link setup panel."""
    if ctx.guild is None:
        return await ctx.send("Server only. | تەنها لە سێرڤەر.")
    link  = _get_link_settings(ctx.guild.id)
    embed = _build_link_panel_embed(ctx.guild, link)
    await ctx.send(embed=embed, view=LinkSetupView(ctx.guild.id))

@setuplink_cmd.error
async def setuplink_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ مووچەی Manage Server پێویستە. | You need Manage Server permission.")


@bot.command(name="link")
async def link_cmd(ctx):
    if ctx.guild is None:
        return await ctx.send("سەروونێ تەنھا لە سێرڤەر | Server only.")
    link_row = _get_link_settings(ctx.guild.id)
    if not link_row:
        return await ctx.send("❌ هیچ لینکێک دانەنراوە. ئادمینەکان `!setuplink` بەکاربھێنن.")
    _url        = link_row["url"]
    _label      = link_row.get("label") or "🔗 Link"
    _alignment  = (link_row.get("alignment") or "left").lower()
    _is_url     = _url.startswith(("http://", "https://"))
    _is_channel = _url.isdigit()
    _is_freeform = not _is_url and not _is_channel

    # ── Free-form Discord-markdown text — send as raw message ─────────────────
    if _is_freeform:
        await ctx.send(_url)
        return

    guild = ctx.guild
    # Build rich server preview embed
    try:
        online = sum(1 for m in guild.members if m.status != discord.Status.offline and not m.bot)
    except Exception:
        online = 0
    total = guild.member_count or 0
    est   = guild.created_at.strftime("%B %Y")
    desc_parts = []
    if guild.description:
        desc_parts.append(guild.description)
    desc_parts.append(f"🟢 {online} Online  •  👥 {total} Members")
    desc_parts.append(f"Est. {est}")
    embed = discord.Embed(
        title=guild.name,
        description="\n".join(desc_parts),
        color=0x57F287,
    )
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    if guild.banner:
        embed.set_image(url=guild.banner.with_format("png").url)

    # ── apply alignment ───────────────────────────────────────────────────────
    _display_link = f"<#{_url}>" if _is_channel else _url
    _PAD2 = "\u3000" * 16

    if _alignment == "center":
        field_name  = f"\u3000\u3000\u3000\u3000\u3000 🔗 {_label} \u3000\u3000\u3000\u3000\u3000"
        field_value = f"\u3000\u3000\u3000\u3000\u3000 {_display_link} \u3000\u3000\u3000\u3000\u3000"
        embed.add_field(name=field_name, value=field_value, inline=False)
    elif _alignment == "right":
        field_name  = f"{_PAD2}🔗 {_label}"
        field_value = f"{_PAD2}{_display_link}"
        embed.add_field(name=field_name, value=field_value, inline=False)
    else:
        embed.add_field(name=f"🔗 {_label}", value=_display_link, inline=False)

    if _is_channel:
        await ctx.send(embed=embed)
    else:
        class _GoView(discord.ui.View):
            def __init__(self):
                super().__init__(timeout=None)
                self.add_item(discord.ui.Button(
                    label=f"👉 {_label}",
                    url=_url,
                    style=discord.ButtonStyle.link,
                ))
        await ctx.send(embed=embed, view=_GoView())


if not token:
    raise RuntimeError("No DISCORD_TOKEN found. Set it in your .env file or token.txt.")

bot.run(token, log_handler=handler, log_level=logging.DEBUG)
 