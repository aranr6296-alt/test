import discord
from discord.ext import commands
import yt_dlp
import asyncio
import os
import sys
from collections import deque
import random
import time
from urllib.parse import urlparse, parse_qs
import logging
import subprocess

# Force install PyNaCl if missing
try:
    import nacl
except ImportError:
    print("📦 Installing PyNaCl...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "PyNaCl>=1.5.0"])
    import nacl

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Bot configuration
TOKEN = os.environ.get('DISCORD_TOKEN') or os.environ.get('BOT_TOKEN')
if not TOKEN:
    print("❌ No token found! Please set DISCORD_TOKEN environment variable")
    sys.exit(1)

PREFIX = '$'

# Intents setup - ALL intents enabled for full functionality
intents = discord.Intents.all()
intents.message_content = True
intents.voice_states = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix=PREFIX, intents=intents, help_command=None)

# Music player class
class MusicPlayer:
    def __init__(self, guild_id):
        self.guild_id = guild_id
        self.queue = deque()
        self.current_song = None
        self.voice_client = None
        self.is_playing = False
        self.is_paused = False
        self.loop = False
        self.loop_queue = False
        self.volume = 100
        self.last_activity = time.time()
        self.requester = None

    def add_to_queue(self, song_data):
        self.queue.append(song_data)
        return len(self.queue)

    def clear_queue(self):
        self.queue.clear()

    def get_next_song(self):
        if self.queue:
            return self.queue.popleft()
        return None

# Dictionary to store guild players
players = {}

# YT-DL options for fast searching
ydl_opts = {
    'format': 'bestaudio/best',
    'quiet': True,
    'no_warnings': True,
    'extract_flat': False,
    'default_search': 'ytsearch',
    'source_address': '0.0.0.0',
    'ignoreerrors': True,
    'logtostderr': False,
    'no_check_certificate': True,
    'prefer_ffmpeg': True,
    'socket_timeout': 30,
    'retries': 5,
    'cookiefile': 'cookies.txt' if os.path.exists('cookies.txt') else None,
}

# FFmpeg options for streaming
ffmpeg_options = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn -b:a 192k -bufsize 64k',
}

async def search_youtube(query, limit=1):
    """Fast YouTube search"""
    search_query = f"ytsearch{limit}:{query}"
    
    with yt_dlp.YoutubeDL({
        'quiet': True,
        'no_warnings': True,
        'extract_flat': False,
        'default_search': 'ytsearch',
        'ignoreerrors': True,
        'no_check_certificate': True,
        'socket_timeout': 30,
        'retries': 3
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
    """Get video info"""
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
            logger.error(f"Error getting video info: {e}")
            return None

async def play_song(guild_id):
    """Play the next song in queue"""
    if guild_id not in players:
        return
    
    player = players[guild_id]
    
    if not player.voice_client or not player.voice_client.is_connected():
        return
    
    if player.is_playing and not player.is_paused:
        return
    
    # Get next song
    if player.loop and player.current_song:
        song = player.current_song
    else:
        song = player.get_next_song()
        if not song:
            if player.loop_queue and player.current_song:
                player.queue.append(player.current_song)
                song = player.get_next_song()
            if not song:
                return
    
    player.current_song = song
    player.is_playing = True
    player.is_paused = False
    
    try:
        # Get audio source
        info = await get_video_info(song['url'])
        if not info:
            player.is_playing = False
            return
        
        # Create audio source
        audio_source = discord.FFmpegPCMAudio(info['url'], **ffmpeg_options)
        
        # Play
        player.voice_client.play(
            audio_source,
            after=lambda e: asyncio.run_coroutine_threadsafe(
                on_song_end(guild_id, e), bot.loop
            )
        )
        
        # Set volume
        if player.voice_client.source:
            player.voice_client.source = discord.PCMVolumeTransformer(
                player.voice_client.source,
                volume=player.volume / 100
            )
        
        player.last_activity = time.time()
        
        # Update bot status
        await bot.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.listening,
                name=f"🎵 {song['title'][:50]}"
            )
        )
        
    except Exception as e:
        logger.error(f"Error playing: {e}")
        player.is_playing = False
        await on_song_end(guild_id, e)

async def on_song_end(guild_id, error=None):
    """Handle song end"""
    if guild_id not in players:
        return
    
    player = players[guild_id]
    player.is_playing = False
    
    if error:
        logger.error(f"Song error: {error}")
    
    # Loop handling
    if player.loop and player.current_song:
        await play_song(guild_id)
        return
    
    if player.loop_queue and player.current_song:
        player.queue.append(player.current_song)
    
    # Play next
    if player.queue or (player.loop_queue and player.current_song):
        await play_song(guild_id)
    else:
        await bot.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.listening,
                name="music | $help"
            )
        )

# ============= COMMANDS =============

@bot.command(name='play', aliases=['p'])
async def play(ctx, *, query):
    """🎵 Play a song from YouTube - Supports Kurdish music!"""
    if not ctx.author.voice:
        await ctx.send("❌ **You need to be in a voice channel!**")
        return
    
    # Get voice channel
    voice_channel = ctx.author.voice.channel
    guild_id = ctx.guild.id
    
    # Create player if needed
    if guild_id not in players:
        players[guild_id] = MusicPlayer(guild_id)
    
    player = players[guild_id]
    player.requester = ctx.author.display_name
    
    # Connect to voice
    if not player.voice_client or not player.voice_client.is_connected():
        try:
            player.voice_client = await voice_channel.connect()
        except Exception as e:
            await ctx.send(f"❌ **Failed to connect:** {str(e)}")
            return
    elif player.voice_client.channel != voice_channel:
        await player.voice_client.move_to(voice_channel)
    
    # Send searching message
    msg = await ctx.send(f"🔍 **Searching for:** `{query}`...")
    
    try:
        # Check if URL
        is_url = urlparse(query).scheme in ('http', 'https')
        
        if is_url:
            song_info = await get_video_info(query)
            if song_info:
                player.add_to_queue(song_info)
                await msg.edit(content=f"✅ **Added to queue:** 🎵 {song_info['title']}")
            else:
                await msg.edit(content="❌ **Could not find the video!**")
                return
        else:
            # Search for song - supports Kurdish
            search_results = await search_youtube(query, limit=1)
            if search_results:
                song_info = search_results[0]
                player.add_to_queue(song_info)
                await msg.edit(content=f"✅ **Added to queue:** 🎵 {song_info['title']}")
            else:
                await msg.edit(content="❌ **No results found!** Try different keywords.")
                return
        
        # Start playing if not already
        if not player.is_playing:
            await play_song(guild_id)
            
    except Exception as e:
        logger.error(f"Play error: {e}")
        await msg.edit(content=f"❌ **Error:** {str(e)}")

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
    
    if not ctx.author.voice:
        await ctx.send("❌ **You need to be in a voice channel!**")
        return
    
    if player.voice_client:
        player.voice_client.stop()
        await ctx.send("⏭️ **Skipped the current song!**")

@bot.command(name='stop')
async def stop(ctx):
    """⏹️ Stop playback and clear queue"""
    guild_id = ctx.guild.id
    
    if guild_id not in players:
        await ctx.send("❌ **No music is playing!**")
        return
    
    player = players[guild_id]
    
    if player.voice_client:
        player.voice_client.stop()
        player.is_playing = False
        player.current_song = None
    
    player.clear_queue()
    
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.listening,
            name="music | $help"
        )
    )
    
    await ctx.send("⏹️ **Stopped playback and cleared queue!**")

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
    
    if player.voice_client and player.voice_client.is_playing():
        player.voice_client.pause()
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
    
    if player.voice_client:
        player.voice_client.resume()
        player.is_paused = False
        await ctx.send("▶️ **Resumed the music!**")

@bot.command(name='queue', aliases=['q'])
async def queue(ctx):
    """📋 Show the current queue"""
    guild_id = ctx.guild.id
    
    if guild_id not in players:
        await ctx.send("📋 **Queue is empty!**")
        return
    
    player = players[guild_id]
    
    if not player.queue and not player.current_song:
        await ctx.send("📋 **Queue is empty!**")
        return
    
    embed = discord.Embed(
        title="🎵 Music Queue",
        color=discord.Color.blue()
    )
    
    # Current song
    if player.current_song and player.is_playing:
        duration = player.current_song.get('duration', 0)
        minutes = duration // 60
        seconds = duration % 60
        embed.add_field(
            name="🎵 Now Playing",
            value=f"**{player.current_song['title']}**\n⏱️ {minutes}:{seconds:02d}",
            inline=False
        )
    
    # Queue list
    if player.queue:
        queue_list = []
        total_duration = 0
        
        for i, song in enumerate(list(player.queue)[:10], 1):
            duration = song.get('duration', 0)
            total_duration += duration
            minutes = duration // 60
            seconds = duration % 60
            queue_list.append(f"`{i}.` {song['title']} ({minutes}:{seconds:02d})")
        
        embed.add_field(
            name=f"📋 Up Next ({len(player.queue)} songs)",
            value="\n".join(queue_list) if queue_list else "No songs in queue",
            inline=False
        )
        
        # Total time
        hours = total_duration // 3600
        minutes = (total_duration % 3600) // 60
        if hours > 0:
            embed.add_field(name="⏱️ Total Time", value=f"{hours}h {minutes}m", inline=True)
        else:
            embed.add_field(name="⏱️ Total Time", value=f"{minutes}m", inline=True)
    
    # Loop status
    loop_status = []
    if player.loop:
        loop_status.append("🔁 Single Loop")
    if player.loop_queue:
        loop_status.append("🔁 Queue Loop")
    if not loop_status:
        loop_status.append("⏹️ Off")
    
    embed.add_field(name="🔄 Loop", value="\n".join(loop_status), inline=True)
    
    await ctx.send(embed=embed)

@bot.command(name='nowplaying', aliases=['np'])
async def nowplaying(ctx):
    """🎵 Show currently playing song"""
    guild_id = ctx.guild.id
    
    if guild_id not in players:
        await ctx.send("❌ **No music is playing!**")
        return
    
    player = players[guild_id]
    
    if not player.current_song or not player.is_playing:
        await ctx.send("❌ **No music is playing!**")
        return
    
    song = player.current_song
    duration = song.get('duration', 0)
    minutes = duration // 60
    seconds = duration % 60
    
    embed = discord.Embed(
        title="🎵 Now Playing",
        color=discord.Color.blue()
    )
    
    embed.add_field(
        name="**Title**",
        value=song.get('title', 'Unknown'),
        inline=False
    )
    
    embed.add_field(
        name="⏱️ Duration",
        value=f"{minutes}:{seconds:02d}",
        inline=True
    )
    
    embed.add_field(
        name="👤 Uploader",
        value=song.get('uploader', 'Unknown'),
        inline=True
    )
    
    if song.get('thumbnail'):
        embed.set_thumbnail(url=song['thumbnail'])
    
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
    
    if player.voice_client and player.voice_client.source:
        if hasattr(player.voice_client.source, 'volume'):
            player.voice_client.source.volume = level / 100
    
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
        await ctx.send("🔁 **Loop enabled** - Current song will repeat!")
    else:
        await ctx.send("🔁 **Loop disabled**")

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
        await ctx.send("🔁 **Queue loop enabled** - Queue will repeat!")
    else:
        await ctx.send("🔁 **Queue loop disabled**")

@bot.command(name='clear')
async def clear(ctx):
    """🗑️ Clear the queue"""
    guild_id = ctx.guild.id
    
    if guild_id not in players:
        await ctx.send("❌ **Queue is empty!**")
        return
    
    player = players[guild_id]
    
    if not player.queue:
        await ctx.send("❌ **Queue is empty!**")
        return
    
    queue_size = len(player.queue)
    player.clear_queue()
    
    await ctx.send(f"🗑️ **Cleared {queue_size} songs from queue!**")

@bot.command(name='shuffle')
async def shuffle(ctx):
    """🔀 Shuffle the queue"""
    guild_id = ctx.guild.id
    
    if guild_id not in players:
        await ctx.send("❌ **No songs in queue!**")
        return
    
    player = players[guild_id]
    
    if len(player.queue) < 2:
        await ctx.send("❌ **Need at least 2 songs to shuffle!**")
        return
    
    queue_list = list(player.queue)
    random.shuffle(queue_list)
    player.queue = deque(queue_list)
    
    await ctx.send("🔀 **Shuffled the queue!**")

@bot.command(name='remove', aliases=['rm'])
async def remove(ctx, position: int):
    """🗑️ Remove a song from queue"""
    guild_id = ctx.guild.id
    
    if guild_id not in players:
        await ctx.send("❌ **No songs in queue!**")
        return
    
    player = players[guild_id]
    
    if not player.queue:
        await ctx.send("❌ **No songs in queue!**")
        return
    
    if position < 1 or position > len(player.queue):
        await ctx.send(f"❌ **Position must be between 1 and {len(player.queue)}!**")
        return
    
    queue_list = list(player.queue)
    removed_song = queue_list.pop(position - 1)
    player.queue = deque(queue_list)
    
    await ctx.send(f"🗑️ **Removed:** {removed_song['title']}")

@bot.command(name='leave', aliases=['dc'])
async def leave(ctx):
    """👋 Disconnect the bot"""
    guild_id = ctx.guild.id
    
    if guild_id not in players:
        await ctx.send("❌ **I'm not in a voice channel!**")
        return
    
    player = players[guild_id]
    
    if player.voice_client:
        await player.voice_client.disconnect()
        player.is_playing = False
        player.current_song = None
        player.clear_queue()
        await ctx.send("👋 **Disconnected!**")
    
    if guild_id in players:
        del players[guild_id]
    
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.listening,
            name="music | $help"
        )
    )

@bot.command(name='help')
async def help_command(ctx):
    """📖 Show all commands"""
    embed = discord.Embed(
        title="🎵 Lara Bot Clone - Music Commands",
        description=f"**Prefix:** `{PREFIX}`\n**Like Lara Bot - Fast & Reliable!**",
        color=discord.Color.blue()
    )
    
    commands_list = {
        f"`{PREFIX}play <song>`": "Play a song (Supports Kurdish music)",
        f"`{PREFIX}skip`": "Skip the current song",
        f"`{PREFIX}queue`": "Show the queue",
        f"`{PREFIX}nowplaying`": "Show current song",
        f"`{PREFIX}pause`": "Pause the music",
        f"`{PREFIX}resume`": "Resume the music",
        f"`{PREFIX}stop`": "Stop and clear queue",
        f"`{PREFIX}volume <1-100>`": "Set volume",
        f"`{PREFIX}loop`": "Toggle single loop",
        f"`{PREFIX}loopqueue`": "Toggle queue loop",
        f"`{PREFIX}shuffle`": "Shuffle queue",
        f"`{PREFIX}clear`": "Clear queue",
        f"`{PREFIX}remove <position>`": "Remove from queue",
        f"`{PREFIX}leave`": "Disconnect bot",
        f"`{PREFIX}help`": "Show this help"
    }
    
    for cmd, desc in commands_list.items():
        embed.add_field(name=cmd, value=desc, inline=False)
    
    embed.set_footer(text="🎵 Made for fast music playback with Kurdish support!")
    await ctx.send(embed=embed)

# ============= EVENTS =============

@bot.event
async def on_ready():
    print(f"""
    ╔═══════════════════════════════════════╗
    ║      🎵 MUSIC BOT IS READY!           ║
    ╠═══════════════════════════════════════╣
    ║  Bot: {bot.user.name}                    ║
    ║  ID: {bot.user.id}                        ║
    ║  Prefix: {PREFIX}                            ║
    ║  Servers: {len(bot.guilds)}                    ║
    ╚═══════════════════════════════════════╝
    """)
    
    # Set status
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.listening,
            name=f"🎵 music | $help"
        )
    )

@bot.event
async def on_command_error(ctx, error):
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
async def on_voice_state_update(member, before, after):
    """Auto-disconnect when alone"""
    if member.id == bot.user.id:
        if after.channel is None:
            guild_id = member.guild.id
            if guild_id in players:
                players[guild_id].is_playing = False
                players[guild_id].current_song = None
                del players[guild_id]
        return
    
    bot_member = member.guild.get_member(bot.user.id)
    if bot_member and bot_member.voice:
        voice_channel = bot_member.voice.channel
        if before.channel == voice_channel and len(voice_channel.members) == 1:
            guild_id = member.guild.id
            if guild_id in players:
                await asyncio.sleep(120)
                if len(voice_channel.members) == 1:
                    player = players[guild_id]
                    try:
                        await player.voice_client.disconnect()
                    except:
                        pass
                    if guild_id in players:
                        del players[guild_id]

# ============= RUN =============

if __name__ == "__main__":
    try:
        print("🚀 Starting bot...")
        bot.run(TOKEN, reconnect=True)
    except discord.LoginFailure:
        print("❌ Invalid token! Please check your DISCORD_TOKEN")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)
