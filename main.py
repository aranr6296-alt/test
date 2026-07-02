import discord
from discord.ext import commands
import yt_dlp
import asyncio
import os
import sys
from collections import deque
import random
import time
from urllib.parse import urlparse
import logging

# ============================================
# LOGGING SETUP
# ============================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============================================
# BOT CONFIGURATION
# ============================================

TOKEN = os.environ.get('DISCORD_TOKEN') or os.environ.get('BOT_TOKEN')
if not TOKEN:
    logger.error("❌ No token found! Set DISCORD_TOKEN environment variable")
    sys.exit(1)

PREFIX = '$'

# ============================================
# DISCORD BOT WITH ALL INTENTS
# ============================================

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
intents.guilds = True
intents.members = True

bot = commands.Bot(
    command_prefix=PREFIX,
    intents=intents,
    help_command=None,
    case_insensitive=True
)

# ============================================
# MUSIC PLAYER CLASS
# ============================================

class MusicPlayer:
    def __init__(self, guild_id):
        self.guild_id = guild_id
        self.queue = deque()
        self.current = None
        self.voice = None
        self.is_playing = False
        self.is_paused = False
        self.loop = False
        self.loop_queue = False
        self.volume = 100
        self.requester = None
        self.start_time = 0

    def add(self, song):
        self.queue.append(song)
        return len(self.queue)

    def next(self):
        if self.queue:
            return self.queue.popleft()
        return None

    def clear(self):
        self.queue.clear()

    def shuffle(self):
        if len(self.queue) > 1:
            temp = list(self.queue)
            random.shuffle(temp)
            self.queue = deque(temp)
            return True
        return False

    def remove(self, position):
        if 0 <= position < len(self.queue):
            temp = list(self.queue)
            removed = temp.pop(position)
            self.queue = deque(temp)
            return removed
        return None

    def format_duration(self, seconds):
        minutes = seconds // 60
        secs = seconds % 60
        if minutes > 0:
            return f"{minutes}m {secs}s"
        return f"{secs}s"

# ============================================
# YOUTUBE HANDLER
# ============================================

ydl_opts = {
    'format': 'bestaudio/best',
    'quiet': True,
    'no_warnings': True,
    'extract_flat': False,
    'default_search': 'ytsearch',
    'source_address': '0.0.0.0',
    'ignoreerrors': True,
    'no_check_certificate': True,
    'socket_timeout': 30,
    'retries': 5,
}

ffmpeg_options = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn -b:a 192k -bufsize 64k',
}

async def search_youtube(query, limit=1):
    """Search YouTube for videos"""
    search_query = f"ytsearch{limit}:{query}"
    
    with yt_dlp.YoutubeDL({
        'quiet': True,
        'no_warnings': True,
        'extract_flat': False,
        'default_search': 'ytsearch',
        'ignoreerrors': True,
        'no_check_certificate': True,
        'socket_timeout': 30,
        'retries': 3,
    }) as ydl:
        try:
            info = ydl.extract_info(search_query, download=False)
            if info and 'entries' in info:
                results = []
                for entry in info['entries']:
                    if entry:
                        results.append({
                            'title': entry.get('title', 'Unknown Title'),
                            'url': entry.get('webpage_url', ''),
                            'duration': entry.get('duration', 0),
                            'uploader': entry.get('uploader', 'Unknown'),
                            'thumbnail': entry.get('thumbnail', ''),
                        })
                return results
        except Exception as e:
            logger.error(f"Search error: {e}")
            return None

async def get_video_info(url):
    """Get video information"""
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(url, download=False)
            if info and 'entries' in info:
                info = info['entries'][0]
            return {
                'title': info.get('title', 'Unknown Title'),
                'url': info.get('webpage_url', url),
                'duration': info.get('duration', 0),
                'uploader': info.get('uploader', 'Unknown'),
                'thumbnail': info.get('thumbnail', ''),
            }
        except Exception as e:
            logger.error(f"Info error: {e}")
            return None

# ============================================
# GLOBAL VARIABLES
# ============================================

players = {}

# ============================================
# PLAYBACK FUNCTIONS
# ============================================

async def play_song(guild_id):
    if guild_id not in players:
        return
    
    player = players[guild_id]
    
    if not player.voice or not player.voice.is_connected():
        return
    
    if player.is_playing and not player.is_paused:
        return
    
    # Get next song
    if player.loop and player.current:
        song = player.current
    else:
        song = player.next()
        if not song and player.loop_queue and player.current:
            player.add(player.current)
            song = player.next()
        if not song:
            return
    
    player.current = song
    player.is_playing = True
    player.is_paused = False
    player.start_time = time.time()
    
    try:
        info = await get_video_info(song['url'])
        if not info:
            player.is_playing = False
            return
        
        audio_source = discord.FFmpegPCMAudio(info['url'], **ffmpeg_options)
        
        player.voice.play(
            audio_source,
            after=lambda e: asyncio.run_coroutine_threadsafe(
                on_song_end(guild_id, e), bot.loop
            )
        )
        
        if player.voice.source:
            player.voice.source = discord.PCMVolumeTransformer(
                player.voice.source,
                volume=player.volume / 100
            )
        
        # Update status
        await bot.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.listening,
                name=f"🎵 {song['title'][:50]}"
            )
        )
        
        logger.info(f"Now playing: {song['title']}")
        
    except Exception as e:
        logger.error(f"Play error: {e}")
        player.is_playing = False
        await on_song_end(guild_id, e)

async def on_song_end(guild_id, error=None):
    if guild_id not in players:
        return
    
    player = players[guild_id]
    player.is_playing = False
    
    if error:
        logger.error(f"Song error: {error}")
    
    if player.loop and player.current:
        await play_song(guild_id)
        return
    
    if player.loop_queue and player.current:
        player.add(player.current)
    
    if player.queue or (player.loop_queue and player.current):
        await play_song(guild_id)
    else:
        await bot.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.listening,
                name="🎵 $help | Music Bot"
            )
        )

# ============================================
# COMMANDS - ALL WITH RESPONSES
# ============================================

@bot.command(name='play', aliases=['p'])
async def play(ctx, *, query):
    """🎵 Play a song from YouTube"""
    
    # Send initial response
    await ctx.send(f"🔍 **Searching for:** `{query}`...")
    
    # Check voice channel
    if not ctx.author.voice:
        await ctx.send("❌ **You need to be in a voice channel!**")
        return
    
    # Initialize player
    guild_id = ctx.guild.id
    if guild_id not in players:
        players[guild_id] = MusicPlayer(guild_id)
    
    player = players[guild_id]
    player.requester = ctx.author.display_name
    
    # Connect to voice
    voice_channel = ctx.author.voice.channel
    try:
        if not player.voice or not player.voice.is_connected():
            player.voice = await voice_channel.connect()
            await ctx.send(f"✅ **Connected to:** {voice_channel.name}")
        elif player.voice.channel != voice_channel:
            await player.voice.move_to(voice_channel)
            await ctx.send(f"✅ **Moved to:** {voice_channel.name}")
    except Exception as e:
        await ctx.send(f"❌ **Connection failed:** {str(e)}")
        return
    
    try:
        # Check if URL
        is_url = urlparse(query).scheme in ('http', 'https')
        
        if is_url:
            song = await get_video_info(query)
            if song:
                position = player.add(song)
                await ctx.send(f"✅ **Added to queue:** 🎵 {song['title']} (Position #{position})")
            else:
                await ctx.send("❌ **Could not find the video!**")
                return
        else:
            # Search for song (supports Kurdish)
            results = await search_youtube(query, limit=3)
            if results:
                song = results[0]
                position = player.add(song)
                await ctx.send(f"✅ **Added to queue:** 🎵 {song['title']} (Position #{position})")
                
                # Show alternatives
                if len(results) > 1:
                    alt_text = "\n".join([f"{i+1}. {r['title'][:40]}" for i, r in enumerate(results[1:], 1)])
                    await ctx.send(f"📋 **Other results:**\n{alt_text}")
            else:
                await ctx.send(f"❌ **No results found for:** `{query}`")
                return
        
        # Start playing if not already
        if not player.is_playing:
            await play_song(guild_id)
            
    except Exception as e:
        logger.error(f"Play error: {e}")
        await ctx.send(f"❌ **Error:** {str(e)}")

@bot.command(name='skip', aliases=['s'])
async def skip(ctx):
    """⏭️ Skip the current song"""
    guild_id = ctx.guild.id
    
    if guild_id not in players:
        await ctx.send("❌ **No music is playing!**")
        return
    
    player = players[guild_id]
    
    if not player.is_playing:
        await ctx.send("❌ **No music is playing!**")
        return
    
    if player.voice:
        player.voice.stop()
        await ctx.send(f"⏭️ **Skipped:** {player.current['title'] if player.current else 'Current song'}")

@bot.command(name='stop')
async def stop(ctx):
    """⏹️ Stop playback and clear queue"""
    guild_id = ctx.guild.id
    
    if guild_id not in players:
        await ctx.send("❌ **No music is playing!**")
        return
    
    player = players[guild_id]
    
    if player.voice:
        player.voice.stop()
        player.is_playing = False
        player.current = None
    
    player.clear()
    await ctx.send("⏹️ **Stopped playback and cleared the queue!**")
    
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.listening,
            name="🎵 $help | Music Bot"
        )
    )

@bot.command(name='pause')
async def pause(ctx):
    """⏸️ Pause the current song"""
    guild_id = ctx.guild.id
    
    if guild_id not in players:
        await ctx.send("❌ **No music is playing!**")
        return
    
    player = players[guild_id]
    
    if not player.is_playing:
        await ctx.send("❌ **No music is playing!**")
        return
    
    if player.is_paused:
        await ctx.send("⏸️ **Music is already paused!**")
        return
    
    if player.voice and player.voice.is_playing():
        player.voice.pause()
        player.is_paused = True
        await ctx.send("⏸️ **Paused the music!**")

@bot.command(name='resume')
async def resume(ctx):
    """▶️ Resume the current song"""
    guild_id = ctx.guild.id
    
    if guild_id not in players:
        await ctx.send("❌ **No music is playing!**")
        return
    
    player = players[guild_id]
    
    if not player.is_paused:
        await ctx.send("▶️ **Music is not paused!**")
        return
    
    if player.voice:
        player.voice.resume()
        player.is_paused = False
        await ctx.send("▶️ **Resumed the music!**")

@bot.command(name='queue', aliases=['q'])
async def show_queue(ctx):
    """📋 Show the current queue"""
    guild_id = ctx.guild.id
    
    if guild_id not in players:
        await ctx.send("📋 **Queue is empty!**")
        return
    
    player = players[guild_id]
    
    if not player.queue and not player.current:
        await ctx.send("📋 **Queue is empty!**")
        return
    
    embed = discord.Embed(
        title="🎵 Music Queue",
        color=discord.Color.blue()
    )
    
    # Current song
    if player.current and player.is_playing:
        duration = player.current.get('duration', 0)
        embed.add_field(
            name="▶️ Now Playing",
            value=f"**{player.current['title']}**\n⏱️ {player.format_duration(duration)}",
            inline=False
        )
    
    # Queue
    if player.queue:
        queue_text = []
        total_duration = 0
        
        for i, song in enumerate(list(player.queue)[:10], 1):
            duration = song.get('duration', 0)
            total_duration += duration
            queue_text.append(f"{i}. **{song['title'][:40]}** ({player.format_duration(duration)})")
        
        embed.add_field(
            name=f"📋 Up Next ({len(player.queue)} songs)",
            value="\n".join(queue_text) if queue_text else "Empty",
            inline=False
        )
        
        if total_duration > 0:
            embed.add_field(
                name="⏱️ Total Duration",
                value=player.format_duration(total_duration),
                inline=True
            )
    
    # Loop status
    loop_status = []
    if player.loop:
        loop_status.append("🔁 Single")
    if player.loop_queue:
        loop_status.append("🔄 Queue")
    if not loop_status:
        loop_status.append("⏹️ Off")
    
    embed.add_field(
        name="🔄 Loop",
        value=", ".join(loop_status),
        inline=True
    )
    
    embed.add_field(
        name="🔊 Volume",
        value=f"{player.volume}%",
        inline=True
    )
    
    await ctx.send(embed=embed)

@bot.command(name='nowplaying', aliases=['np'])
async def nowplaying(ctx):
    """🎵 Show currently playing song"""
    guild_id = ctx.guild.id
    
    if guild_id not in players:
        await ctx.send("❌ **No music is playing!**")
        return
    
    player = players[guild_id]
    
    if not player.current or not player.is_playing:
        await ctx.send("❌ **No music is playing!**")
        return
    
    song = player.current
    duration = song.get('duration', 0)
    progress = int((time.time() - player.start_time) % duration) if duration > 0 else 0
    
    embed = discord.Embed(
        title="🎵 Now Playing",
        color=discord.Color.blue()
    )
    
    embed.add_field(
        name="📌 Title",
        value=f"**{song['title']}**",
        inline=False
    )
    
    embed.add_field(
        name="⏱️ Progress",
        value=f"{player.format_duration(progress)} / {player.format_duration(duration)}",
        inline=True
    )
    
    embed.add_field(
        name="👤 Uploader",
        value=song.get('uploader', 'Unknown'),
        inline=True
    )
    
    embed.add_field(
        name="🔊 Volume",
        value=f"{player.volume}%",
        inline=True
    )
    
    embed.add_field(
        name="📢 Requested by",
        value=player.requester or "Unknown",
        inline=True
    )
    
    if song.get('thumbnail'):
        embed.set_thumbnail(url=song['thumbnail'])
    
    await ctx.send(embed=embed)

@bot.command(name='volume', aliases=['vol'])
async def volume(ctx, level: int = None):
    """🔊 Set volume (1-100)"""
    guild_id = ctx.guild.id
    
    if guild_id not in players:
        await ctx.send("❌ **No music is playing!**")
        return
    
    player = players[guild_id]
    
    if level is None:
        await ctx.send(f"🔊 **Current volume:** `{player.volume}%`")
        return
    
    if not 1 <= level <= 100:
        await ctx.send("❌ **Volume must be between 1 and 100!**")
        return
    
    player.volume = level
    
    if player.voice and player.voice.source:
        if hasattr(player.voice.source, 'volume'):
            player.voice.source.volume = level / 100
    
    await ctx.send(f"🔊 **Volume set to:** `{level}%`")

@bot.command(name='loop')
async def loop(ctx):
    """🔁 Toggle single song loop"""
    guild_id = ctx.guild.id
    
    if guild_id not in players:
        await ctx.send("❌ **No music is playing!**")
        return
    
    player = players[guild_id]
    player.loop = not player.loop
    
    if player.loop:
        await ctx.send("🔁 **Single loop enabled!** Current song will repeat.")
    else:
        await ctx.send("🔁 **Single loop disabled!**")

@bot.command(name='loopqueue', aliases=['lq'])
async def loopqueue(ctx):
    """🔁 Toggle queue loop"""
    guild_id = ctx.guild.id
    
    if guild_id not in players:
        await ctx.send("❌ **No music is playing!**")
        return
    
    player = players[guild_id]
    player.loop_queue = not player.loop_queue
    
    if player.loop_queue:
        await ctx.send("🔄 **Queue loop enabled!** Queue will repeat.")
    else:
        await ctx.send("🔄 **Queue loop disabled!**")

@bot.command(name='shuffle')
async def shuffle(ctx):
    """🔀 Shuffle the queue"""
    guild_id = ctx.guild.id
    
    if guild_id not in players:
        await ctx.send("❌ **No songs in queue!**")
        return
    
    player = players[guild_id]
    
    if player.shuffle():
        await ctx.send(f"🔀 **Shuffled {len(player.queue)} songs in the queue!**")
    else:
        await ctx.send("❌ **Need at least 2 songs to shuffle!**")

@bot.command(name='clear')
async def clear(ctx):
    """🗑️ Clear the queue"""
    guild_id = ctx.guild.id
    
    if guild_id not in players:
        await ctx.send("❌ **Queue is empty!**")
        return
    
    player = players[guild_id]
    count = len(player.queue)
    player.clear()
    
    await ctx.send(f"🗑️ **Cleared {count} songs from the queue!**")

@bot.command(name='remove', aliases=['rm'])
async def remove(ctx, position: int):
    """🗑️ Remove a song from queue"""
    guild_id = ctx.guild.id
    
    if guild_id not in players:
        await ctx.send("❌ **No songs in queue!**")
        return
    
    player = players[guild_id]
    
    if not player.queue:
        await ctx.send("❌ **Queue is empty!**")
        return
    
    removed = player.remove(position - 1)
    if removed:
        await ctx.send(f"🗑️ **Removed:** {removed['title']}")
    else:
        await ctx.send(f"❌ **Invalid position!** Must be between 1 and {len(player.queue)}")

@bot.command(name='leave', aliases=['dc'])
async def leave(ctx):
    """👋 Disconnect the bot"""
    guild_id = ctx.guild.id
    
    if guild_id not in players:
        await ctx.send("❌ **I'm not in a voice channel!**")
        return
    
    player = players[guild_id]
    
    if player.voice:
        await player.voice.disconnect()
        await ctx.send("👋 **Disconnected from voice channel!**")
    
    if guild_id in players:
        del players[guild_id]
    
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.listening,
            name="🎵 $help | Music Bot"
        )
    )

@bot.command(name='help')
async def help_command(ctx):
    """📖 Show all commands"""
    embed = discord.Embed(
        title="🎵 Music Bot Commands",
        description=f"**Prefix:** `{PREFIX}`\nFast & Reliable Music Bot with Kurdish Support!",
        color=discord.Color.blue()
    )
    
    commands_info = {
        f"**{PREFIX}play** `<song>`": "🎵 Play a song (Supports Kurdish)",
        f"**{PREFIX}skip**": "⏭️ Skip current song",
        f"**{PREFIX}stop**": "⏹️ Stop and clear queue",
        f"**{PREFIX}pause**": "⏸️ Pause music",
        f"**{PREFIX}resume**": "▶️ Resume music",
        f"**{PREFIX}queue**": "📋 Show queue",
        f"**{PREFIX}nowplaying**": "🎵 Current song",
        f"**{PREFIX}volume** `<1-100>`": "🔊 Set volume",
        f"**{PREFIX}loop**": "🔁 Toggle single loop",
        f"**{PREFIX}loopqueue**": "🔄 Toggle queue loop",
        f"**{PREFIX}shuffle**": "🔀 Shuffle queue",
        f"**{PREFIX}clear**": "🗑️ Clear queue",
        f"**{PREFIX}remove** `<pos>`": "🗑️ Remove from queue",
        f"**{PREFIX}leave**": "👋 Disconnect bot",
        f"**{PREFIX}help**": "📖 Show this help"
    }
    
    for cmd, desc in commands_info.items():
        embed.add_field(name=cmd, value=desc, inline=False)
    
    embed.set_footer(text="💡 Supports Kurdish music! Just use $play [song name]")
    await ctx.send(embed=embed)

@bot.command(name='ping')
async def ping(ctx):
    """🏓 Check bot latency"""
    latency = round(bot.latency * 1000)
    await ctx.send(f"🏓 **Pong!** Latency: `{latency}ms`")

@bot.command(name='invite')
async def invite(ctx):
    """🔗 Get bot invite link"""
    if bot.user:
        invite_url = f"https://discord.com/oauth2/authorize?client_id={bot.user.id}&permissions=36700160&scope=bot"
        await ctx.send(f"🔗 **Invite me:** {invite_url}")

# ============================================
# EVENTS
# ============================================

@bot.event
async def on_ready():
    """Bot ready event"""
    print("=" * 50)
    print("🎵 MUSIC BOT IS ONLINE!")
    print("=" * 50)
    print(f"🤖 Bot Name: {bot.user.name}")
    print(f"🆔 Bot ID: {bot.user.id}")
    print(f"📝 Prefix: {PREFIX}")
    print(f"🏠 Servers: {len(bot.guilds)}")
    print("=" * 50)
    print("✅ Bot is ready for commands!")
    print("💡 Supports Kurdish songs!")
    print("=" * 50)
    
    # Set initial status
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.listening,
            name="🎵 $help | Music Bot"
        )
    )

@bot.event
async def on_command_error(ctx, error):
    """Global error handler"""
    if isinstance(error, commands.CommandNotFound):
        return
    
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"❌ **Missing argument!** Use `{PREFIX}help` for help.")
        return
    
    if isinstance(error, commands.BadArgument):
        await ctx.send(f"❌ **Invalid argument!** Use `{PREFIX}help` for help.")
        return
    
    logger.error(f"Command error: {error}")
    await ctx.send(f"❌ **Error:** {str(error)}")

@bot.event
async def on_message(message):
    """Handle messages"""
    if message.author.bot:
        return
    
    # Process commands
    await bot.process_commands(message)

# ============================================
# MAIN
# ============================================

if __name__ == "__main__":
    try:
        logger.info("🚀 Starting Music Bot...")
        bot.run(TOKEN, reconnect=True)
    except discord.LoginFailure:
        logger.error("❌ Invalid token! Please check DISCORD_TOKEN")
        sys.exit(1)
    except KeyboardInterrupt:
        logger.info("👋 Bot stopped by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")
        sys.exit(1)
