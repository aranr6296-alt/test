"""
╔══════════════════════════════════════════════════════╗
║          VELTRA MUSIC BOT  —  discord.py             ║
║   Play · Queue · Filters · Lyrics · 24/7 · DJ Role  ║
╚══════════════════════════════════════════════════════╝
"""

import discord
from discord.ext import commands, tasks
import asyncio
import yt_dlp
import os
import time
import math
import random
import sqlite3
import aiohttp
import logging
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

logging.basicConfig(level=logging.INFO)
handler = logging.FileHandler(filename="discord.log", encoding="utf-8", mode="w")

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.voice_states = True

bot = commands.Bot(command_prefix="$", intents=intents, help_command=None)
bot_start_time = time.time()

# ──────────────────────────────────────────────────────
#  THEME
# ──────────────────────────────────────────────────────
C_LUNA   = 0xB5179E
C_DARK   = 0x560BAD
C_GREEN  = 0x57F287
C_RED    = 0xED4245
C_YELLOW = 0xFEE75C
C_BLUE   = 0x4361EE

# ──────────────────────────────────────────────────────
#  DATABASE
# ──────────────────────────────────────────────────────
DB_FILE = "luna.db"

def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS guild_settings (
            guild_id   INTEGER PRIMARY KEY,
            dj_role_id INTEGER DEFAULT NULL,
            volume     INTEGER DEFAULT 100,
            loop_mode  TEXT    DEFAULT 'off',
            tfs        INTEGER DEFAULT 0,
            autoplay   INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS history (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id   INTEGER,
            title      TEXT,
            url        TEXT,
            duration   TEXT,
            requester  TEXT,
            played_at  TEXT DEFAULT (datetime('now'))
        );
    """)
    conn.commit()
    conn.close()

init_db()

def get_settings(guild_id: int) -> dict:
    conn = get_db()
    row = conn.execute("SELECT * FROM guild_settings WHERE guild_id=?", (guild_id,)).fetchone()
    if not row:
        conn.execute("INSERT OR IGNORE INTO guild_settings (guild_id) VALUES (?)", (guild_id,))
        conn.commit()
        row = conn.execute("SELECT * FROM guild_settings WHERE guild_id=?", (guild_id,)).fetchone()
    conn.close()
    return dict(row)

def save_settings(guild_id: int, **kw):
    get_settings(guild_id)
    sets = ", ".join(f"{k}=?" for k in kw)
    conn = get_db()
    conn.execute(f"UPDATE guild_settings SET {sets} WHERE guild_id=?", [*kw.values(), guild_id])
    conn.commit()
    conn.close()

def push_history(guild_id: int, title: str, url: str, duration: str, requester: str):
    conn = get_db()
    conn.execute(
        "INSERT INTO history (guild_id,title,url,duration,requester) VALUES (?,?,?,?,?)",
        (guild_id, title, url, duration, requester),
    )
    conn.execute(
        "DELETE FROM history WHERE guild_id=? AND id NOT IN "
        "(SELECT id FROM history WHERE guild_id=? ORDER BY id DESC LIMIT 50)",
        (guild_id, guild_id),
    )
    conn.commit()
    conn.close()

# ──────────────────────────────────────────────────────
#  AUDIO FILTERS
# ──────────────────────────────────────────────────────
FILTERS: dict[str, dict] = {
    "none":      {"label": "🎵 None",        "af": ""},
    "bassboost": {"label": "🔊 Bass Boost",  "af": "bass=g=10,dynaudnorm=f=200"},
    "nightcore": {"label": "🌙 Nightcore",   "af": "asetrate=44100*1.25,aresample=44100"},
    "vaporwave": {"label": "🌊 Vaporwave",   "af": "asetrate=44100*0.8,aresample=44100"},
    "8d":        {"label": "🎧 8D Audio",    "af": "apulsator=hz=0.08"},
    "karaoke":   {"label": "🎤 Karaoke",     "af": "stereotools=mlev=0.03125"},
    "tremolo":   {"label": "〰️ Tremolo",     "af": "tremolo=f=4:d=0.9"},
    "vibrato":   {"label": "🎸 Vibrato",     "af": "vibrato=f=6.5:d=0.9"},
    "superbass": {"label": "💥 Super Bass",  "af": "bass=g=20,dynaudnorm=f=200"},
    "soft":      {"label": "🕊️ Soft",        "af": "lowpass=f=300,volume=1.5"},
    "earrape":   {"label": "📢 Ear Rape",    "af": "acrusher=level_in=8:level_out=18:bits=8:mode=log:aa=1"},
    "pitch":     {"label": "🎵 Pitch Up",    "af": "asetrate=44100*1.15,aresample=44100"},
}

# ──────────────────────────────────────────────────────
#  SONG & PLAYER
# ──────────────────────────────────────────────────────
class Song:
    def __init__(self, data: dict, requester: discord.Member):
        self.title      = data.get("title", "Unknown")
        self.url        = data.get("webpage_url") or data.get("original_url") or data.get("url", "")
        self.stream_url = data.get("url", "")
        self.duration   = data.get("duration") or 0
        self.thumbnail  = data.get("thumbnail", "")
        self.uploader   = data.get("uploader") or data.get("channel", "Unknown")
        self.requester  = requester

    @property
    def dur_str(self) -> str:
        if not self.duration:
            return "🔴 LIVE"
        m, s = divmod(int(self.duration), 60)
        h, m = divmod(m, 60)
        return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"

    def progress_bar(self, elapsed: float, length: int = 13) -> str:
        if not self.duration:
            return "─" * length + " 🔴"
        pct  = min(elapsed / self.duration, 1.0)
        fill = int(pct * length)
        return "▬" * fill + "🔘" + "▬" * (length - fill)


class MusicPlayer:
    def __init__(self, guild_id: int):
        self.guild_id        = guild_id
        self.queue:          list[Song] = []
        self.current:        Song | None = None
        self.history:        list[Song] = []
        self.loop            = "off"        # off | track | queue
        self.volume          = 1.0
        self.filter          = "none"
        self.skip_votes:     set[int] = set()
        self.tfs             = False
        self.autoplay        = False
        self._start:         float | None = None
        self._paused_at:     float | None = None
        self._elapsed_pre:   float = 0.0
        self.np_msg:         discord.Message | None = None
        self._changing_filter: bool = False   # guard against setfilter race condition

    def elapsed(self) -> float:
        if self._start is None:
            return 0.0
        if self._paused_at is not None:
            return self._elapsed_pre
        return self._elapsed_pre + (time.time() - self._start)

    def reset_timer(self):
        self._start       = time.time()
        self._paused_at   = None
        self._elapsed_pre = 0.0


# guild_id → MusicPlayer
players: dict[int, MusicPlayer] = {}

def get_player(guild_id: int) -> MusicPlayer:
    if guild_id not in players:
        p = MusicPlayer(guild_id)
        s = get_settings(guild_id)
        p.volume   = s["volume"] / 100.0
        p.loop     = s["loop_mode"]
        p.tfs      = bool(s["tfs"])
        p.autoplay = bool(s["autoplay"])
        players[guild_id] = p
    return players[guild_id]

# ──────────────────────────────────────────────────────
#  YT-DLP
# ──────────────────────────────────────────────────────
_BASE_OPTS = {
    "format": "bestaudio/best",
    "quiet": True,
    "no_warnings": True,
    "socket_timeout": 20,
    "source_address": "0.0.0.0",
    # Use Android/iOS player client to bypass YouTube bot-detection on server IPs
    "extractor_args": {
        "youtube": {
            "player_client": ["android", "web"],
            "skip": ["dash", "hls"],
        }
    },
    "http_headers": {
        "User-Agent": (
            "Mozilla/5.0 (Linux; Android 11; Pixel 5) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Mobile Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
    },
}

async def _run_in_executor(fn):
    """Run a blocking function in a thread pool without blocking the event loop."""
    return await asyncio.get_running_loop().run_in_executor(None, fn)

async def yt_search(query: str) -> list[dict]:
    """Return up to 5 YouTube search results."""
    def _do():
        opts = {**_BASE_OPTS, "noplaylist": True, "default_search": "ytsearch5"}
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(f"ytsearch5:{query}", download=False)
            return info.get("entries", [info])
    return await _run_in_executor(_do)

async def yt_resolve(url: str) -> dict:
    """Resolve a single video URL to full info (including stream URL)."""
    def _do():
        opts = {**_BASE_OPTS, "noplaylist": True}
        with yt_dlp.YoutubeDL(opts) as ydl:
            return ydl.extract_info(url, download=False)
    return await _run_in_executor(_do)

async def yt_playlist(url: str) -> list[dict]:
    """Return flat playlist entries."""
    def _do():
        opts = {**_BASE_OPTS, "extract_flat": "in_playlist", "noplaylist": False}
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if "entries" in info:
                return [e for e in info["entries"] if e and e.get("id")]
            return [info]
    return await _run_in_executor(_do)

def _make_ffmpeg_source(stream_url: str, volume: float, audio_filter: str) -> discord.PCMVolumeTransformer:
    af = FILTERS.get(audio_filter, FILTERS["none"])["af"]
    options = "-vn" + (f" -af {af}" if af else "")
    src = discord.FFmpegPCMAudio(
        stream_url,
        before_options="-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
        options=options,
    )
    return discord.PCMVolumeTransformer(src, volume=volume)

# ──────────────────────────────────────────────────────
#  PLAYBACK ENGINE
# ──────────────────────────────────────────────────────
async def play_next(guild_id: int, channel: discord.abc.Messageable, vc: discord.VoiceClient):
    player = get_player(guild_id)

    # Decide next song
    if player.loop == "track" and player.current:
        song = player.current
    elif player.loop == "queue" and player.current:
        player.queue.append(player.current)
        song = player.queue.pop(0) if player.queue else None
    else:
        song = player.queue.pop(0) if player.queue else None

    if song is None:
        # Queue empty — save to history then wait before auto-disconnect
        if player.current:
            push_history(
                guild_id,
                player.current.title,
                player.current.url,
                player.current.dur_str,
                str(player.current.requester),
            )
        player.current = None
        player.np_msg  = None
        if not player.tfs:
            await asyncio.sleep(300)
            p2 = get_player(guild_id)
            if not p2.current and not p2.queue and vc.is_connected():
                await vc.disconnect()
                players.pop(guild_id, None)
                await channel.send(
                    embed=discord.Embed(
                        color=C_LUNA,
                        description="👋 Left the voice channel (idle for 5 minutes).",
                    )
                )
        return

    # Push finished song to history (only when not looping the same track)
    if player.current and player.current is not song:
        push_history(
            guild_id,
            player.current.title,
            player.current.url,
            player.current.dur_str,
            str(player.current.requester),
        )
        player.history.append(player.current)
        if len(player.history) > 20:
            player.history.pop(0)

    player.current = song
    player.skip_votes.clear()

    # Resolve stream URL for flat playlist entries
    if not song.stream_url or "googlevideo" not in song.stream_url:
        try:
            data = await yt_resolve(song.url)
            song.stream_url = data.get("url", "")
            song.thumbnail  = song.thumbnail or data.get("thumbnail", "")
            song.duration   = song.duration   or data.get("duration", 0)
            song.uploader   = song.uploader   or data.get("uploader") or data.get("channel", "Unknown")
        except Exception as e:
            await channel.send(embed=discord.Embed(
                color=C_RED,
                description=f"⚠️ Skipping **{song.title}** — couldn't resolve stream: {e}"
            ))
            await play_next(guild_id, channel, vc)
            return

    # Build FFmpeg source
    try:
        source = _make_ffmpeg_source(song.stream_url, player.volume, player.filter)
    except Exception as e:
        await channel.send(embed=discord.Embed(color=C_RED, description=f"⚠️ FFmpeg error: {e}"))
        await play_next(guild_id, channel, vc)
        return

    player.reset_timer()

    def after_cb(err):
        if err:
            print(f"[Veltra] Player error: {err}")
        # Skip if setfilter is restarting the source — avoids double-play race condition
        if get_player(guild_id)._changing_filter:
            return
        asyncio.run_coroutine_threadsafe(play_next(guild_id, channel, vc), bot.loop)

    vc.play(source, after=after_cb)

    # Send / update Now Playing embed
    embed = build_np_embed(player, vc)
    view  = NowPlayingView(player, vc)
    try:
        if player.np_msg:
            await player.np_msg.edit(embed=embed, view=view)
        else:
            player.np_msg = await channel.send(embed=embed, view=view)
    except (discord.NotFound, discord.HTTPException):
        player.np_msg = await channel.send(embed=embed, view=view)

# ──────────────────────────────────────────────────────
#  NOW PLAYING EMBED
# ──────────────────────────────────────────────────────
def _fmt_time(sec: float) -> str:
    m, s = divmod(int(sec), 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"

def build_np_embed(player: MusicPlayer, vc: discord.VoiceClient) -> discord.Embed:
    song    = player.current
    elapsed = player.elapsed()
    paused  = vc.is_paused() if vc else False

    e = discord.Embed(color=C_LUNA)
    e.set_author(name="🎵 Now Playing")
    e.title = song.title
    e.url   = song.url

    bar      = song.progress_bar(elapsed)
    time_str = f"`{_fmt_time(elapsed)}` {bar} `{song.dur_str}`"
    e.description = time_str

    loop_icon = {"off": "➡️ Off", "track": "🔂 Track", "queue": "🔁 Queue"}[player.loop]
    vol_icon  = "🔇" if player.volume == 0 else ("🔉" if player.volume < 0.5 else "🔊")
    flt_label = FILTERS.get(player.filter, FILTERS["none"])["label"]

    e.add_field(name="🎙️ Artist",      value=song.uploader,             inline=True)
    e.add_field(name="⏱️ Length",      value=song.dur_str,              inline=True)
    e.add_field(name=f"{vol_icon} Vol", value=f"{int(player.volume*100)}%", inline=True)
    e.add_field(name="🔁 Loop",        value=loop_icon,                 inline=True)
    e.add_field(name="🎛️ Filter",      value=flt_label,                 inline=True)
    e.add_field(name="📋 Queue",       value=str(len(player.queue)),    inline=True)
    e.add_field(name="👤 Requested by", value=song.requester.mention,   inline=False)

    if song.thumbnail:
        e.set_thumbnail(url=song.thumbnail)

    status = "⏸ Paused" if paused else "▶️ Playing"
    e.set_footer(text=f"Veltra Music  •  {status}  •  Use buttons to control")
    return e

# ──────────────────────────────────────────────────────
#  NOW PLAYING VIEW (BUTTONS)
# ──────────────────────────────────────────────────────
class NowPlayingView(discord.ui.View):
    def __init__(self, player: MusicPlayer, vc: discord.VoiceClient):
        super().__init__(timeout=None)
        self.player = player
        self.vc     = vc
        paused      = vc.is_paused() if vc else False

        row0 = [
            ("⏮️", "prev",  discord.ButtonStyle.secondary, 0),
            ("▶️" if paused else "⏸️", "pause", discord.ButtonStyle.primary, 0),
            ("⏭️", "skip",  discord.ButtonStyle.secondary, 0),
            ("⏹️", "stop",  discord.ButtonStyle.danger,    0),
        ]
        row1 = [
            ("🔂" if player.loop == "track" else "🔁" if player.loop == "queue" else "➡️",
             "loop", discord.ButtonStyle.secondary, 1),
            ("🔀", "shuffle", discord.ButtonStyle.secondary, 1),
            ("❤️", "grab",    discord.ButtonStyle.secondary, 1),
            ("📋", "queue",   discord.ButtonStyle.secondary, 1),
        ]
        for emoji, action, style, row in row0 + row1:
            self.add_item(_NPBtn(emoji, action, style, row))


class _NPBtn(discord.ui.Button):
    def __init__(self, emoji: str, action: str, style: discord.ButtonStyle, row: int):
        # Use guild-agnostic unique IDs by including a random suffix so buttons
        # across multiple guild messages don't collide in persistent views.
        super().__init__(
            emoji=emoji,
            style=style,
            custom_id=f"veltra_np_{action}_{random.randint(0, 9999999)}",
            row=row,
        )
        self.action = action

    async def callback(self, interaction: discord.Interaction):
        vc     = interaction.guild.voice_client
        player = get_player(interaction.guild.id)

        if not vc or not player.current:
            return await interaction.response.send_message(
                embed=discord.Embed(color=C_RED, description="❌ Nothing is playing!"), ephemeral=True
            )

        if self.action == "pause":
            if vc.is_paused():
                player._elapsed_pre = player.elapsed()
                player._start       = time.time()
                player._paused_at   = None
                vc.resume()
            else:
                player._elapsed_pre = player.elapsed()
                player._paused_at   = time.time()
                vc.pause()

        elif self.action == "skip":
            player.skip_votes.clear()
            vc.stop()

        elif self.action == "stop":
            player.queue.clear()
            player.loop = "off"
            vc.stop()
            await interaction.response.send_message(
                embed=discord.Embed(color=C_GREEN, description="⏹️ Stopped and cleared the queue."),
                ephemeral=True,
            )
            return

        elif self.action == "loop":
            modes       = ["off", "track", "queue"]
            player.loop = modes[(modes.index(player.loop) + 1) % 3]
            save_settings(interaction.guild.id, loop_mode=player.loop)

        elif self.action == "shuffle":
            random.shuffle(player.queue)
            await interaction.response.send_message(
                embed=discord.Embed(color=C_GREEN, description="🔀 Queue shuffled!"), ephemeral=True
            )
            return

        elif self.action == "grab":
            song = player.current
            e    = discord.Embed(color=C_LUNA, title="❤️ Saved Song",
                                 description=f"**[{song.title}]({song.url})**")
            e.add_field(name="Duration", value=song.dur_str, inline=True)
            e.add_field(name="Channel",  value=song.uploader, inline=True)
            if song.thumbnail:
                e.set_thumbnail(url=song.thumbnail)
            try:
                await interaction.user.send(embed=e)
                await interaction.response.send_message(
                    embed=discord.Embed(color=C_GREEN, description="❤️ Song info sent to your DMs!"),
                    ephemeral=True,
                )
            except discord.Forbidden:
                await interaction.response.send_message(
                    embed=discord.Embed(color=C_RED,
                                        description="❌ I can't DM you. Enable DMs from server members."),
                    ephemeral=True,
                )
            return

        elif self.action == "queue":
            q = player.queue
            if not q:
                return await interaction.response.send_message(
                    embed=discord.Embed(color=C_LUNA, title="📋 Queue",
                                        description="The queue is empty."),
                    ephemeral=True,
                )
            lines = [f"`{i+1}.` [{s.title}]({s.url}) `{s.dur_str}`" for i, s in enumerate(q[:10])]
            extra = f"\n*+{len(q)-10} more...*" if len(q) > 10 else ""
            e     = discord.Embed(color=C_LUNA, title=f"📋 Queue — {len(q)} song(s)",
                                  description="\n".join(lines) + extra)
            return await interaction.response.send_message(embed=e, ephemeral=True)

        elif self.action == "prev":
            if player.history:
                prev = player.history.pop()
                if player.current:
                    player.queue.insert(0, player.current)
                player.queue.insert(0, prev)
                vc.stop()
            else:
                return await interaction.response.send_message(
                    embed=discord.Embed(color=C_RED, description="❌ No previous song!"),
                    ephemeral=True,
                )

        # Refresh NP embed
        try:
            new_embed = build_np_embed(player, vc)
            new_view  = NowPlayingView(player, vc)
            await interaction.message.edit(embed=new_embed, view=new_view)
            await interaction.response.defer()
        except Exception:
            try:
                await interaction.response.defer()
            except Exception:
                pass

# ──────────────────────────────────────────────────────
#  HELPERS
# ──────────────────────────────────────────────────────
def err(desc: str) -> discord.Embed:
    return discord.Embed(color=C_RED, description=f"❌ {desc}")

def ok(desc: str) -> discord.Embed:
    return discord.Embed(color=C_GREEN, description=f"✅ {desc}")

async def _ensure_voice(ctx: commands.Context) -> discord.VoiceClient | None:
    if not ctx.author.voice:
        await ctx.send(embed=err("You must be in a voice channel!"))
        return None
    vc = ctx.voice_client
    if not vc:
        try:
            vc = await ctx.author.voice.channel.connect()
        except discord.ClientException as e:
            await ctx.send(embed=err(f"Could not connect to voice channel: {e}"))
            return None
        except asyncio.TimeoutError:
            await ctx.send(embed=err("Timed out connecting to voice channel."))
            return None
    elif ctx.author.voice.channel != vc.channel:
        await vc.move_to(ctx.author.voice.channel)
    return vc

async def _dj_check(ctx: commands.Context) -> bool:
    if ctx.author.guild_permissions.manage_guild:
        return True
    s     = get_settings(ctx.guild.id)
    dj_id = s.get("dj_role_id")
    if dj_id:
        role = ctx.guild.get_role(int(dj_id))
        if role and role in ctx.author.roles:
            return True
        name = role.name if role else str(dj_id)
        await ctx.send(embed=err(f"You need the **{name}** DJ role to use this command!"))
        return False
    return True

def _dur(seconds) -> str:
    if not seconds:
        return "?"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"

# ──────────────────────────────────────────────────────
#  COMMANDS — PLAYBACK
# ──────────────────────────────────────────────────────
@bot.command(aliases=["j"])
async def join(ctx: commands.Context):
    """Join your voice channel."""
    vc = await _ensure_voice(ctx)
    if vc:
        await ctx.send(embed=ok(f"Joined **{vc.channel.name}**!"))


@bot.command(aliases=["dc", "leave"])
async def disconnect(ctx: commands.Context):
    """Disconnect from voice."""
    if not ctx.voice_client:
        return await ctx.send(embed=err("I'm not in a voice channel!"))
    if not await _dj_check(ctx):
        return
    player = get_player(ctx.guild.id)
    player.queue.clear()
    ctx.voice_client.stop()
    await ctx.voice_client.disconnect()
    players.pop(ctx.guild.id, None)
    await ctx.send(embed=ok("Disconnected! 👋"))


@bot.command(aliases=["p"])
async def play(ctx: commands.Context, *, query: str):
    """Play a song or playlist from YouTube / URL."""
    vc = await _ensure_voice(ctx)
    if not vc:
        return

    player = get_player(ctx.guild.id)
    msg    = await ctx.send(embed=discord.Embed(color=C_LUNA, description=f"🔍 Searching for **{query}**..."))

    try:
        is_url = query.startswith(("http://", "https://"))

        if is_url and ("list=" in query or "playlist" in query.lower()):
            entries = await yt_playlist(query)
            if not entries:
                return await msg.edit(embed=err("Couldn't find anything in that playlist."))

            added = 0
            for entry in entries:
                data = {
                    "title":       entry.get("title") or "Unknown",
                    "url":         f"https://www.youtube.com/watch?v={entry['id']}",
                    "webpage_url": f"https://www.youtube.com/watch?v={entry['id']}",
                    "duration":    entry.get("duration", 0),
                    "thumbnail":   (entry.get("thumbnail") or
                                    (entry.get("thumbnails") or [{}])[-1].get("url", "")),
                    "uploader":    entry.get("uploader") or entry.get("channel", ""),
                }
                player.queue.append(Song(data, ctx.author))
                added += 1

            e = discord.Embed(color=C_LUNA, title="📋 Playlist Added!")
            e.add_field(name="Songs",        value=str(added),              inline=True)
            e.add_field(name="Queue length", value=str(len(player.queue)),  inline=True)
            await msg.edit(embed=e)

        elif is_url:
            data = await yt_resolve(query)
            song = Song(data, ctx.author)
            player.queue.append(song)
            if vc.is_playing() or vc.is_paused():
                e = discord.Embed(color=C_LUNA, title="➕ Added to Queue",
                                  description=f"**[{song.title}]({song.url})**")
                e.add_field(name="Duration", value=song.dur_str, inline=True)
                e.add_field(name="Position", value=f"#{len(player.queue)}", inline=True)
                if song.thumbnail:
                    e.set_thumbnail(url=song.thumbnail)
                await msg.edit(embed=e)
            else:
                await msg.delete()

        else:
            results = await yt_search(query)
            if not results:
                return await msg.edit(embed=err("No results found!"))
            data = results[0]
            song = Song(data, ctx.author)
            player.queue.append(song)
            if vc.is_playing() or vc.is_paused():
                e = discord.Embed(color=C_LUNA, title="➕ Added to Queue",
                                  description=f"**[{song.title}]({song.url})**")
                e.add_field(name="Duration", value=song.dur_str, inline=True)
                e.add_field(name="Position", value=f"#{len(player.queue)}", inline=True)
                if song.thumbnail:
                    e.set_thumbnail(url=song.thumbnail)
                await msg.edit(embed=e)
            else:
                await msg.delete()

    except Exception as ex:
        return await msg.edit(embed=err(f"Error: {ex}"))

    if not vc.is_playing() and not vc.is_paused():
        await play_next(ctx.guild.id, ctx.channel, vc)


@bot.command()
async def search(ctx: commands.Context, *, query: str):
    """Search YouTube and pick a result."""
    msg = await ctx.send(embed=discord.Embed(color=C_LUNA, description=f"🔍 Searching **{query}**..."))
    try:
        results = await yt_search(query)
    except Exception as ex:
        return await msg.edit(embed=err(str(ex)))

    results = results[:5]
    if not results:
        return await msg.edit(embed=err("No results found!"))

    lines = [
        f"`{i+1}.` [{r.get('title','?')}](https://youtu.be/{r.get('id','')}) `{_dur(r.get('duration',0))}`"
        for i, r in enumerate(results)
    ]
    e = discord.Embed(color=C_LUNA, title="🔍 Search Results", description="\n".join(lines))
    e.set_footer(text="Reply with a number (1-5) to pick  •  or 'cancel'")
    await msg.edit(embed=e)

    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel

    try:
        reply = await bot.wait_for("message", check=check, timeout=30)
    except asyncio.TimeoutError:
        return await msg.edit(embed=err("Selection timed out."))

    try:
        await reply.delete()
    except Exception:
        pass

    if reply.content.lower() == "cancel":
        return await msg.edit(embed=ok("Cancelled search."))

    try:
        idx = int(reply.content) - 1
        if idx < 0 or idx >= len(results):
            raise ValueError
    except ValueError:
        return await msg.edit(embed=err("Invalid selection."))

    vc = await _ensure_voice(ctx)
    if not vc:
        return

    player = get_player(ctx.guild.id)
    data   = results[idx]
    try:
        full = await yt_resolve(f"https://www.youtube.com/watch?v={data['id']}")
    except Exception as ex:
        return await msg.edit(embed=err(str(ex)))

    song = Song(full, ctx.author)
    player.queue.append(song)

    e2 = discord.Embed(color=C_LUNA, title="➕ Added to Queue",
                       description=f"**[{song.title}]({song.url})**")
    e2.add_field(name="Duration", value=song.dur_str, inline=True)
    if song.thumbnail:
        e2.set_thumbnail(url=song.thumbnail)
    await msg.edit(embed=e2)

    if not vc.is_playing() and not vc.is_paused():
        await play_next(ctx.guild.id, ctx.channel, vc)


@bot.command(aliases=["pa"])
async def pause(ctx: commands.Context):
    """Pause playback."""
    vc = ctx.voice_client
    if not vc or not vc.is_playing():
        return await ctx.send(embed=err("Nothing is playing!"))
    if not await _dj_check(ctx):
        return
    player = get_player(ctx.guild.id)
    player._elapsed_pre = player.elapsed()
    player._paused_at   = time.time()
    vc.pause()
    await ctx.send(embed=ok("Paused ⏸️"))


@bot.command(aliases=["res"])
async def resume(ctx: commands.Context):
    """Resume playback."""
    vc = ctx.voice_client
    if not vc or not vc.is_paused():
        return await ctx.send(embed=err("Nothing is paused!"))
    if not await _dj_check(ctx):
        return
    player = get_player(ctx.guild.id)
    player._elapsed_pre = player.elapsed()
    player._start       = time.time()
    player._paused_at   = None
    vc.resume()
    await ctx.send(embed=ok("Resumed ▶️"))


@bot.command(aliases=["s"])
async def skip(ctx: commands.Context):
    """Skip the current song (or vote skip)."""
    vc = ctx.voice_client
    if not vc or (not vc.is_playing() and not vc.is_paused()):
        return await ctx.send(embed=err("Nothing is playing!"))

    player = get_player(ctx.guild.id)
    is_dj  = ctx.author.guild_permissions.manage_guild
    s      = get_settings(ctx.guild.id)
    dj_id  = s.get("dj_role_id")
    has_dj = bool(dj_id)

    dj_role = ctx.guild.get_role(int(dj_id)) if dj_id else None
    if is_dj or (has_dj and dj_role and dj_role in ctx.author.roles):
        player.skip_votes.clear()
        vc.stop()
        return await ctx.send(embed=ok("⏭️ Skipped!"))

    # Vote skip — need > 50 % of voice members
    vc_members = [m for m in vc.channel.members if not m.bot]
    needed     = max(1, math.ceil(len(vc_members) * 0.5))
    player.skip_votes.add(ctx.author.id)
    votes = len(player.skip_votes)
    if votes >= needed:
        player.skip_votes.clear()
        vc.stop()
        await ctx.send(embed=ok(f"⏭️ Vote passed ({votes}/{needed})! Skipped."))
    else:
        await ctx.send(embed=discord.Embed(
            color=C_YELLOW,
            description=f"🗳️ Skip vote: **{votes}/{needed}** — need {needed - votes} more.",
        ))


@bot.command(aliases=["vs"])
async def voteskip(ctx: commands.Context):
    """Cast a skip vote."""
    await ctx.invoke(skip)


@bot.command()
async def stop(ctx: commands.Context):
    """Stop music and clear the queue."""
    if not await _dj_check(ctx):
        return
    vc = ctx.voice_client
    if not vc:
        return await ctx.send(embed=err("I'm not in a voice channel!"))
    player = get_player(ctx.guild.id)
    player.queue.clear()
    player.loop = "off"
    vc.stop()
    await ctx.send(embed=ok("⏹️ Stopped and cleared the queue."))


@bot.command(aliases=["np"])
async def nowplaying(ctx: commands.Context):
    """Show what's currently playing."""
    vc = ctx.voice_client
    if not vc:
        return await ctx.send(embed=err("I'm not in a voice channel!"))
    player = get_player(ctx.guild.id)
    if not player.current:
        return await ctx.send(embed=err("Nothing is playing!"))
    embed = build_np_embed(player, vc)
    view  = NowPlayingView(player, vc)
    player.np_msg = await ctx.send(embed=embed, view=view)


@bot.command(aliases=["replay", "restart"])
async def again(ctx: commands.Context):
    """Replay the current song from the beginning."""
    vc = ctx.voice_client
    if not vc or not vc.is_playing():
        return await ctx.send(embed=err("Nothing is playing!"))
    if not await _dj_check(ctx):
        return
    player = get_player(ctx.guild.id)
    if not player.current:
        return await ctx.send(embed=err("Nothing is playing!"))
    player.queue.insert(0, player.current)
    vc.stop()
    await ctx.send(embed=ok("🔁 Replaying current song!"))

# ──────────────────────────────────────────────────────
#  COMMANDS — QUEUE
# ──────────────────────────────────────────────────────
@bot.command(aliases=["q"])
async def queue(ctx: commands.Context, page: int = 1):
    """Show the music queue."""
    player = get_player(ctx.guild.id)

    if not player.current and not player.queue:
        return await ctx.send(embed=discord.Embed(
            color=C_LUNA, title="📋 Queue",
            description="The queue is empty. Use `$play` to add songs!",
        ))

    per_page = 10
    pages    = max(1, math.ceil(len(player.queue) / per_page))
    page     = max(1, min(page, pages))
    start    = (page - 1) * per_page
    chunk    = player.queue[start:start + per_page]

    desc = ""
    if player.current:
        desc += (f"**▶️ Now Playing:**\n"
                 f"[{player.current.title}]({player.current.url}) "
                 f"`{player.current.dur_str}` — {player.current.requester.mention}\n\n")
    if chunk:
        desc += "**📋 Up Next:**\n"
        for i, s in enumerate(chunk, start=start + 1):
            desc += f"`{i}.` [{s.title}]({s.url}) `{s.dur_str}` — {s.requester.mention}\n"

    total_dur = sum(s.duration or 0 for s in player.queue)
    e         = discord.Embed(color=C_LUNA, title=f"📋 Queue  —  {len(player.queue)} song(s)",
                              description=desc)
    loop_icon = {"off": "➡️ Off", "track": "🔂 Track", "queue": "🔁 Queue"}[player.loop]
    e.set_footer(text=f"Page {page}/{pages}  •  Total: {_fmt_time(total_dur)}  •  Loop: {loop_icon}")
    await ctx.send(embed=e)


@bot.command(aliases=["rm"])
async def remove(ctx: commands.Context, index: int):
    """Remove a song from the queue by position."""
    if not await _dj_check(ctx):
        return
    player = get_player(ctx.guild.id)
    if index < 1 or index > len(player.queue):
        return await ctx.send(embed=err(f"Invalid position! Queue has {len(player.queue)} songs."))
    removed = player.queue.pop(index - 1)
    await ctx.send(embed=ok(f"Removed **{removed.title}** from the queue."))


@bot.command()
async def clear(ctx: commands.Context):
    """Clear the entire queue (keeps current song)."""
    if not await _dj_check(ctx):
        return
    player = get_player(ctx.guild.id)
    player.queue.clear()
    await ctx.send(embed=ok("Queue cleared!"))


@bot.command(aliases=["sh"])
async def shuffle(ctx: commands.Context):
    """Shuffle the queue."""
    if not await _dj_check(ctx):
        return
    player = get_player(ctx.guild.id)
    if len(player.queue) < 2:
        return await ctx.send(embed=err("Need at least 2 songs in the queue to shuffle."))
    random.shuffle(player.queue)
    await ctx.send(embed=ok("🔀 Queue shuffled!"))


@bot.command()
async def move(ctx: commands.Context, frm: int, to: int):
    """Move a song in the queue: $move <from> <to>"""
    if not await _dj_check(ctx):
        return
    player = get_player(ctx.guild.id)
    q      = player.queue
    if not (1 <= frm <= len(q)) or not (1 <= to <= len(q)):
        return await ctx.send(embed=err(f"Positions must be between 1 and {len(q)}."))
    song = q.pop(frm - 1)
    q.insert(to - 1, song)
    await ctx.send(embed=ok(f"Moved **{song.title}** to position **{to}**."))


@bot.command()
async def skipto(ctx: commands.Context, index: int):
    """Skip to a specific position in the queue."""
    if not await _dj_check(ctx):
        return
    vc = ctx.voice_client
    if not vc:
        return await ctx.send(embed=err("Nothing is playing!"))
    player = get_player(ctx.guild.id)
    if index < 1 or index > len(player.queue):
        return await ctx.send(embed=err(f"Invalid position! Queue has {len(player.queue)} songs."))
    player.queue = player.queue[index - 1:]
    vc.stop()
    await ctx.send(embed=ok(f"⏭️ Skipped to position **{index}**!"))

# ──────────────────────────────────────────────────────
#  COMMANDS — SETTINGS
# ──────────────────────────────────────────────────────
@bot.command(aliases=["vol"])
async def volume(ctx: commands.Context, vol: int):
    """Set volume 0–200%: $volume 80"""
    if not await _dj_check(ctx):
        return
    if not 0 <= vol <= 200:
        return await ctx.send(embed=err("Volume must be between 0 and 200."))
    player = get_player(ctx.guild.id)
    player.volume = vol / 100.0
    save_settings(ctx.guild.id, volume=vol)
    vc = ctx.voice_client
    if vc and vc.source:
        vc.source.volume = player.volume
    icon = "🔇" if vol == 0 else ("🔉" if vol < 50 else "🔊")
    await ctx.send(embed=ok(f"{icon} Volume set to **{vol}%**"))


@bot.command()
async def loop(ctx: commands.Context, mode: str = None):
    """Set loop mode: off / track / queue"""
    if not await _dj_check(ctx):
        return
    player = get_player(ctx.guild.id)
    modes  = ["off", "track", "queue"]
    if mode is None:
        mode = modes[(modes.index(player.loop) + 1) % 3]
    mode = mode.lower()
    if mode not in modes:
        return await ctx.send(embed=err("Mode must be: `off`, `track`, or `queue`"))
    player.loop = mode
    save_settings(ctx.guild.id, loop_mode=mode)
    icon = {"off": "➡️", "track": "🔂", "queue": "🔁"}[mode]
    await ctx.send(embed=ok(f"{icon} Loop set to **{mode.capitalize()}**"))


@bot.command(aliases=["filter"])
async def setfilter(ctx: commands.Context, name: str = None):
    """Apply an audio filter: $filter bassboost"""
    if not await _dj_check(ctx):
        return
    if name is None:
        lines = [f"`{k}` — {v['label']}" for k, v in FILTERS.items()]
        e = discord.Embed(color=C_LUNA, title="🎛️ Audio Filters", description="\n".join(lines))
        e.set_footer(text="Usage: $filter <name>  |  $filter none  to reset")
        return await ctx.send(embed=e)

    name = name.lower()
    if name not in FILTERS:
        return await ctx.send(embed=err("Unknown filter! Use `$filter` to see the list."))

    player = get_player(ctx.guild.id)
    player.filter = name
    vc = ctx.voice_client

    if vc and (vc.is_playing() or vc.is_paused()) and player.current:
        was_paused = vc.is_paused()
        paused_pos = player.elapsed()

        # Set flag BEFORE stopping so after_cb ignores the stop
        player._changing_filter = True
        vc.stop()
        await asyncio.sleep(0.5)

        try:
            data = await yt_resolve(player.current.url)
            player.current.stream_url = data.get("url", player.current.stream_url)
        except Exception:
            pass

        source = _make_ffmpeg_source(player.current.stream_url, player.volume, name)
        player._elapsed_pre     = 0.0
        player._start           = time.time()
        player._paused_at       = None
        player._changing_filter = False   # clear flag before playing new source

        def after_cb(err_):
            asyncio.run_coroutine_threadsafe(
                play_next(ctx.guild.id, ctx.channel, vc), bot.loop
            )

        vc.play(source, after=after_cb)

        if was_paused:
            vc.pause()
            player._elapsed_pre = paused_pos
            player._paused_at   = time.time()

    label = FILTERS[name]["label"]
    await ctx.send(embed=ok(f"🎛️ Filter set to **{label}**"))


@bot.command(aliases=["filters"])
async def listfilters(ctx: commands.Context):
    """List all available audio filters."""
    lines = [f"`{k}` — {v['label']}" for k, v in FILTERS.items()]
    e = discord.Embed(color=C_LUNA, title="🎛️ Available Filters", description="\n".join(lines))
    e.set_footer(text="$filter <name>  to apply  |  $filter none  to reset")
    await ctx.send(embed=e)


@bot.command(name="247")
async def tfs(ctx: commands.Context):
    """Toggle 24/7 mode (bot stays in VC)."""
    if not await _dj_check(ctx):
        return
    player = get_player(ctx.guild.id)
    player.tfs = not player.tfs
    save_settings(ctx.guild.id, tfs=int(player.tfs))
    state = "enabled 🟢" if player.tfs else "disabled 🔴"
    await ctx.send(embed=ok(f"24/7 mode **{state}**"))


@bot.command()
async def autoplay(ctx: commands.Context):
    """Toggle autoplay (adds related songs when queue ends)."""
    if not await _dj_check(ctx):
        return
    player = get_player(ctx.guild.id)
    player.autoplay = not player.autoplay
    save_settings(ctx.guild.id, autoplay=int(player.autoplay))
    state = "enabled 🟢" if player.autoplay else "disabled 🔴"
    await ctx.send(embed=ok(f"Autoplay **{state}**"))


@bot.command(aliases=["setdj"])
@commands.has_permissions(manage_guild=True)
async def djrole(ctx: commands.Context, role: discord.Role = None):
    """Set or remove the DJ role: $djrole @DJ"""
    if role is None:
        save_settings(ctx.guild.id, dj_role_id=None)
        return await ctx.send(embed=ok("DJ role removed. Everyone can control music now."))
    save_settings(ctx.guild.id, dj_role_id=role.id)
    await ctx.send(embed=ok(f"DJ role set to {role.mention}. Only DJs and admins can control music."))

# ──────────────────────────────────────────────────────
#  COMMANDS — LYRICS
# ──────────────────────────────────────────────────────
@bot.command(aliases=["ly"])
async def lyrics(ctx: commands.Context, *, song_name: str = None):
    """Fetch lyrics for the current or specified song."""
    player = get_player(ctx.guild.id)
    if song_name is None:
        if not player.current:
            return await ctx.send(embed=err("Nothing is playing! Provide a song name: `$lyrics song name`"))
        song_name = player.current.title

    clean = song_name
    for pat in ["(official", "(lyrics", "(audio", "(video", "(hd", "(4k", "[", "]", "ft.", "feat."]:
        if pat in clean.lower():
            clean = clean[:clean.lower().index(pat)].strip()

    parts = clean.split(" - ", 1)
    if len(parts) == 2:
        artist, title_q = parts[0].strip(), parts[1].strip()
    else:
        artist, title_q = "", clean.strip()

    msg = await ctx.send(embed=discord.Embed(
        color=C_LUNA, description=f"🔍 Fetching lyrics for **{clean}**..."
    ))

    lyrics_text = None
    try:
        url = f"https://api.lyrics.ovh/v1/{artist or clean}/{title_q}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    lyrics_text = data.get("lyrics")
    except Exception:
        pass

    if not lyrics_text:
        try:
            url = f"https://api.lyrics.ovh/v1/{clean}/{clean}"
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        lyrics_text = data.get("lyrics")
        except Exception:
            pass

    if not lyrics_text:
        return await msg.edit(embed=err(
            f"Couldn't find lyrics for **{clean}**.\nTry: `$lyrics Artist - Song Title`"
        ))

    lyrics_text = lyrics_text.replace("\r\n", "\n").strip()
    chunks = [lyrics_text[i:i + 3800] for i in range(0, len(lyrics_text), 3800)]
    for i, chunk in enumerate(chunks):
        title = f"📜 {clean}" + (f" (Part {i+1})" if len(chunks) > 1 else "")
        e = discord.Embed(color=C_LUNA, title=title, description=chunk)
        e.set_footer(text="Powered by lyrics.ovh")
        if i == 0:
            await msg.edit(embed=e)
        else:
            await ctx.send(embed=e)

# ──────────────────────────────────────────────────────
#  COMMANDS — HISTORY & GRAB
# ──────────────────────────────────────────────────────
@bot.command()
async def history(ctx: commands.Context):
    """Show recently played songs."""
    conn = get_db()
    rows = conn.execute(
        "SELECT title, url, duration, requester, played_at FROM history "
        "WHERE guild_id=? ORDER BY id DESC LIMIT 10",
        (ctx.guild.id,),
    ).fetchall()
    conn.close()
    if not rows:
        return await ctx.send(embed=discord.Embed(
            color=C_LUNA, title="📜 History", description="No songs played yet!"
        ))
    lines = [f"`{i+1}.` [{r['title']}]({r['url']}) `{r['duration']}`" for i, r in enumerate(rows)]
    e = discord.Embed(color=C_LUNA, title="📜 Recently Played", description="\n".join(lines))
    await ctx.send(embed=e)


@bot.command()
async def grab(ctx: commands.Context):
    """DM yourself the current song info."""
    player = get_player(ctx.guild.id)
    if not player.current:
        return await ctx.send(embed=err("Nothing is playing!"))
    song = player.current
    e = discord.Embed(color=C_LUNA, title="❤️ Saved Song!",
                      description=f"**[{song.title}]({song.url})**")
    e.add_field(name="Duration", value=song.dur_str, inline=True)
    e.add_field(name="Channel",  value=song.uploader, inline=True)
    if song.thumbnail:
        e.set_thumbnail(url=song.thumbnail)
    try:
        await ctx.author.send(embed=e)
        await ctx.send(embed=ok("❤️ Song info sent to your DMs!"))
    except discord.Forbidden:
        await ctx.send(embed=err("I can't DM you. Enable DMs from server members."))

# ──────────────────────────────────────────────────────
#  COMMANDS — INFO
# ──────────────────────────────────────────────────────
@bot.command()
async def ping(ctx: commands.Context):
    """Bot latency."""
    lat = round(bot.latency * 1000)
    e = discord.Embed(color=C_LUNA, title="🏓 Pong!", description=f"Latency: **{lat}ms**")
    await ctx.send(embed=e)


@bot.command(aliases=["stats"])
async def botinfo(ctx: commands.Context):
    """Show bot information."""
    uptime = int(time.time() - bot_start_time)
    h, rem = divmod(uptime, 3600)
    m, s   = divmod(rem, 60)
    e = discord.Embed(color=C_LUNA, title="🎵 Veltra Music Bot")
    e.add_field(name="Prefix",   value="`$`",                 inline=True)
    e.add_field(name="Servers",  value=str(len(bot.guilds)),  inline=True)
    e.add_field(name="Uptime",   value=f"{h}h {m}m {s}s",    inline=True)
    e.add_field(name="Library",  value="discord.py",          inline=True)
    e.add_field(name="Engine",   value="yt-dlp + FFmpeg",     inline=True)
    e.add_field(name="Filters",  value=str(len(FILTERS)),     inline=True)
    e.set_footer(text="Veltra Music Bot  •  $help for commands")
    await ctx.send(embed=e)

# ──────────────────────────────────────────────────────
#  HELP
# ──────────────────────────────────────────────────────
HELP_DATA = [
    ("🎵 Playback", [
        ("$play <query/url>",       "Play a song or YouTube playlist"),
        ("$search <query>",         "Search YouTube & pick a result"),
        ("$pause",                  "Pause playback"),
        ("$resume",                 "Resume playback"),
        ("$skip / $s",              "Skip the current song"),
        ("$stop",                   "Stop and clear the queue"),
        ("$nowplaying / $np",       "Show now playing with controls"),
        ("$again / $replay",        "Replay the current song from start"),
        ("$join",                   "Join your voice channel"),
        ("$disconnect / $dc",       "Disconnect from voice"),
    ]),
    ("📋 Queue", [
        ("$queue [page] / $q",      "Show the music queue"),
        ("$remove <index> / $rm",   "Remove a song from the queue"),
        ("$clear",                  "Clear the entire queue"),
        ("$shuffle / $sh",          "Shuffle the queue"),
        ("$move <from> <to>",       "Move a song in the queue"),
        ("$skipto <index>",         "Skip to a position in the queue"),
    ]),
    ("🎛️ Settings", [
        ("$volume <0-200> / $vol",  "Set the volume"),
        ("$loop [off/track/queue]", "Set loop mode (cycles through all)"),
        ("$filter <name>",          "Apply an audio filter"),
        ("$filters",                "List all audio filters"),
        ("$247",                    "Toggle 24/7 mode (stay in VC)"),
        ("$autoplay",               "Toggle autoplay related songs"),
        ("$djrole @role",           "Set the DJ role (admin only)"),
    ]),
    ("🛠️ Extras", [
        ("$lyrics [song]",          "Fetch song lyrics"),
        ("$grab",                   "DM yourself the current song"),
        ("$voteskip / $vs",         "Vote to skip the current song"),
        ("$history",                "Show recently played songs"),
        ("$ping",                   "Show bot latency"),
        ("$botinfo",                "Show bot information"),
    ]),
]

@bot.command(aliases=["h", "commands"])
async def help(ctx: commands.Context, *, section: str = None):
    """Show help for Veltra Music Bot."""
    e = discord.Embed(
        color=C_LUNA,
        title="🎵 Veltra Music Bot — Command List",
        description=(
            "A feature-complete music bot. Use `$play <song>` to get started!\n"
            "Interactive **Now Playing** panel: play ▶️ · pause ⏸ · skip ⏭ · loop 🔁 · shuffle 🔀\n\u200b"
        ),
    )
    for section_name, cmds in HELP_DATA:
        val = "\n".join(f"`{cmd}` — {desc}" for cmd, desc in cmds)
        e.add_field(name=section_name, value=val, inline=False)
    e.set_footer(text="Veltra Music Bot  •  Built with discord.py + yt-dlp + FFmpeg")
    await ctx.send(embed=e)

# ──────────────────────────────────────────────────────
#  EVENTS
# ──────────────────────────────────────────────────────
@bot.event
async def on_ready():
    print(f"[Veltra] Logged in as {bot.user} ({bot.user.id})")

    # Load libopus — required for voice audio encoding on Linux
    if not discord.opus.is_loaded():
        for lib in ("libopus.so.0", "libopus.so", "opus", "libopus"):
            try:
                discord.opus.load_opus(lib)
                print(f"[Veltra] Opus loaded: {lib}")
                break
            except OSError:
                continue
        if discord.opus.is_loaded():
            print("[Veltra] Voice (opus) ready.")
        else:
            print("[Veltra] WARNING: libopus not found — audio may not play.")

    await bot.change_presence(
        activity=discord.Activity(type=discord.ActivityType.listening, name="$play | Veltra Music"),
        status=discord.Status.online,
    )
    if not refresh_np.is_running():
        refresh_np.start()


@bot.event
async def on_voice_state_update(member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
    """Auto-leave if alone in VC (and not 24/7 mode)."""
    if member == bot.user:
        return
    vc = member.guild.voice_client
    if not vc:
        return
    player = get_player(member.guild.id)
    if player.tfs:
        return
    human_members = [m for m in vc.channel.members if not m.bot]
    if len(human_members) == 0:
        await asyncio.sleep(30)
        vc2 = member.guild.voice_client
        if not vc2:
            return
        humans_now = [m for m in vc2.channel.members if not m.bot]
        if len(humans_now) == 0:
            player.queue.clear()
            vc2.stop()
            await vc2.disconnect()
            players.pop(member.guild.id, None)


@tasks.loop(seconds=15)
async def refresh_np():
    """Periodically update the Now Playing embed progress bar."""
    for guild_id, player in list(players.items()):
        if not player.current or not player.np_msg:
            continue
        guild = bot.get_guild(guild_id)
        if not guild:
            continue
        vc = guild.voice_client
        if not vc or (not vc.is_playing() and not vc.is_paused()):
            continue
        try:
            new_embed = build_np_embed(player, vc)
            await player.np_msg.edit(embed=new_embed)
        except (discord.NotFound, discord.HTTPException):
            player.np_msg = None
        except Exception:
            pass


@bot.event
async def on_command_error(ctx: commands.Context, error):
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(embed=err(f"Missing argument: `{error.param.name}`"))
    elif isinstance(error, commands.BadArgument):
        await ctx.send(embed=err(f"Bad argument: {error}"))
    elif isinstance(error, commands.MissingPermissions):
        await ctx.send(embed=err("You don't have permission to use this command."))
    elif isinstance(error, commands.CommandNotFound):
        pass
    else:
        await ctx.send(embed=err(f"An error occurred: {error}"))
        raise error

# ──────────────────────────────────────────────────────
#  RUN
# ──────────────────────────────────────────────────────
if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN not set! Add it to your Railway environment variables.")

bot.run(TOKEN, log_handler=handler, log_level=logging.WARNING)
