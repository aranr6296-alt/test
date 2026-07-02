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
# SIMPLE LOGGING
# ============================================

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============================================
# BOT TOKEN - READ FROM ENVIRONMENT
# ============================================

TOKEN = os.environ.get('DISCORD_TOKEN')
if not TOKEN:
    print("❌ ERROR: No DISCORD_TOKEN found!")
    sys.exit(1)

PREFIX = '$'

# ============================================
# BOT SETUP - SIMPLE INTENTS
# ============================================

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
intents.guilds = True

bot = commands.Bot(command_prefix=PREFIX, intents=intents)

# ============================================
# SIMPLE MUSIC PLAYER
# ============================================

class SimplePlayer:
    def __init__(self):
        self.queue = []
        self.current = None
        self.voice = None
        self.is_playing = False
        self.volume = 100

players = {}

# ============================================
# YOUTUBE SEARCH
# ============================================

ytdl_format_options = {
    'format': 'bestaudio/best',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0'
}

ffmpeg_options = {
    'options': '-vn',
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5'
}

ytdl = yt_dlp.YoutubeDL(ytdl_format_options)

class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')
        self.url = data.get('url')

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=False):
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))
        
        if 'entries' in data:
            data = data['entries'][0]
        
        filename = data['url'] if stream else ytdl.prepare_filename(data)
        return cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options), data=data)

# ============================================
# COMMANDS - EVERY COMMAND RESPONDS
# ============================================

@bot.event
async def on_ready():
    print("=" * 50)
    print("🎵 BOT IS ONLINE AND READY!")
    print("=" * 50)
    print(f"🤖 Bot: {bot.user.name}")
    print(f"🆔 ID: {bot.user.id}")
    print(f"📝 Prefix: {PREFIX}")
    print(f"🏠 Servers: {len(bot.guilds)}")
    print("=" * 50)
    print("✅ Type $help for commands")
    print("=" * 50)
    
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.listening,
            name="$help | Music Bot"
        )
    )

@bot.event
async def on_message(message):
    # Don't respond to bot messages
    if message.author.bot:
        return
    
    # Process commands
    await bot.process_commands(message)

@bot.event
async def on_command_error(ctx, error):
    """Handle command errors"""
    if isinstance(error, commands.CommandNotFound):
        # Command not found - silently ignore
        return
    
    # Send error message
    error_msg = str(error)
    await ctx.send(f"❌ **Error:** {error_msg}")
    print(f"Command error: {error_msg}")

# ============================================
# TEST COMMAND - ALWAYS RESPONDS
# ============================================

@bot.command(name='ping')
async def ping(ctx):
    """🏓 Check if bot is alive"""
    await ctx.send(f"🏓 **Pong!** Latency: `{round(bot.latency * 1000)}ms`")
    print(f"Ping command used by {ctx.author}")

@bot.command(name='test')
async def test(ctx):
    """🧪 Test command"""
    await ctx.send("✅ **Bot is working!** I can see your messages!")
    print(f"Test command used by {ctx.author}")

@bot.command(name='hello')
async def hello(ctx):
    """👋 Say hello"""
    await ctx.send(f"👋 **Hello {ctx.author.mention}!** I'm a music bot!")
    print(f"Hello command used by {ctx.author}")

# ============================================
# MUSIC COMMANDS
# ============================================

@bot.command(name='play', aliases=['p'])
async def play(ctx, *, query):
    """🎵 Play a song from YouTube"""
    
    # IMMEDIATE RESPONSE
    await ctx.send(f"🔍 **Searching for:** `{query}`...")
    print(f"Play command: {query} by {ctx.author}")
    
    # Check voice channel
    if not ctx.author.voice:
        await ctx.send("❌ **You need to be in a voice channel!**")
        return
    
    voice_channel = ctx.author.voice.channel
    guild_id = ctx.guild.id
    
    # Create player if not exists
    if guild_id not in players:
        players[guild_id] = SimplePlayer()
    
    player = players[guild_id]
    
    # Connect to voice
    try:
        if not player.voice or not player.voice.is_connected():
            player.voice = await voice_channel.connect()
            await ctx.send(f"✅ **Connected to:** {voice_channel.name}")
        elif player.voice.channel != voice_channel:
            await player.voice.move_to(voice_channel)
            await ctx.send(f"✅ **Moved to:** {voice_channel.name}")
    except Exception as e:
        await ctx.send(f"❌ **Connection error:** {str(e)}")
        return
    
    try:
        # Search for song
        is_url = query.startswith('http://') or query.startswith('https://')
        
        if not is_url:
            # Search YouTube
            search_query = f"ytsearch:{query}"
            loop = asyncio.get_event_loop()
            data = await loop.run_in_executor(None, lambda: ytdl.extract_info(search_query, download=False))
            
            if data and 'entries' in data and data['entries']:
                song_info = data['entries'][0]
                song_url = song_info['webpage_url']
                song_title = song_info['title']
            else:
                await ctx.send(f"❌ **No results found for:** `{query}`")
                return
        else:
            song_url = query
            song_info = await loop.run_in_executor(None, lambda: ytdl.extract_info(song_url, download=False))
            song_title = song_info.get('title', 'Unknown')
        
        # Add to queue
        player.queue.append({
            'url': song_url,
            'title': song_title
        })
        
        await ctx.send(f"✅ **Added to queue:** 🎵 {song_title}")
        
        # Start playing if not playing
        if not player.is_playing:
            await play_next(ctx.guild.id)
            
    except Exception as e:
        await ctx.send(f"❌ **Error:** {str(e)}")
        print(f"Play error: {e}")

async def play_next(guild_id):
    """Play next song in queue"""
    if guild_id not in players:
        return
    
    player = players[guild_id]
    
    if not player.queue:
        player.is_playing = False
        return
    
    if not player.voice or not player.voice.is_connected():
        player.is_playing = False
        return
    
    # Get next song
    song = player.queue.pop(0)
    player.current = song
    
    try:
        # Create audio source
        source = await YTDLSource.from_url(song['url'], loop=bot.loop, stream=True)
        source.volume = player.volume / 100
        
        # Play
        player.voice.play(source, after=lambda e: asyncio.run_coroutine_threadsafe(play_next(guild_id), bot.loop))
        player.is_playing = True
        
        # Update status
        await bot.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.listening,
                name=f"🎵 {song['title'][:50]}"
            )
        )
        
        print(f"Now playing: {song['title']}")
        
    except Exception as e:
        print(f"Play error: {e}")
        player.is_playing = False
        await play_next(guild_id)

@bot.command(name='skip', aliases=['s'])
async def skip(ctx):
    """⏭️ Skip current song"""
    guild_id = ctx.guild.id
    
    if guild_id not in players:
        await ctx.send("❌ **No music playing!**")
        return
    
    player = players[guild_id]
    
    if not player.is_playing or not player.current:
        await ctx.send("❌ **No music playing!**")
        return
    
    if player.voice:
        player.voice.stop()
        await ctx.send(f"⏭️ **Skipped:** {player.current['title']}")
        player.is_playing = False
        await play_next(guild_id)

@bot.command(name='stop')
async def stop(ctx):
    """⏹️ Stop and clear queue"""
    guild_id = ctx.guild.id
    
    if guild_id not in players:
        await ctx.send("❌ **No music playing!**")
        return
    
    player = players[guild_id]
    
    if player.voice:
        player.voice.stop()
        player.is_playing = False
        player.current = None
    
    player.queue.clear()
    await ctx.send("⏹️ **Stopped and cleared queue!**")
    
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.listening,
            name="$help | Music Bot"
        )
    )

@bot.command(name='pause')
async def pause(ctx):
    """⏸️ Pause music"""
    guild_id = ctx.guild.id
    
    if guild_id not in players:
        await ctx.send("❌ **No music playing!**")
        return
    
    player = players[guild_id]
    
    if not player.is_playing:
        await ctx.send("❌ **No music playing!**")
        return
    
    if player.voice and player.voice.is_playing():
        player.voice.pause()
        await ctx.send("⏸️ **Paused!**")
    else:
        await ctx.send("❌ **Nothing to pause!**")

@bot.command(name='resume')
async def resume(ctx):
    """▶️ Resume music"""
    guild_id = ctx.guild.id
    
    if guild_id not in players:
        await ctx.send("❌ **No music paused!**")
        return
    
    player = players[guild_id]
    
    if player.voice and player.voice.is_paused():
        player.voice.resume()
        await ctx.send("▶️ **Resumed!**")
    else:
        await ctx.send("❌ **Nothing to resume!**")

@bot.command(name='queue', aliases=['q'])
async def queue(ctx):
    """📋 Show queue"""
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
    
    if player.current:
        embed.add_field(
            name="▶️ Now Playing",
            value=f"**{player.current['title']}**",
            inline=False
        )
    
    if player.queue:
        queue_text = []
        for i, song in enumerate(player.queue[:10], 1):
            queue_text.append(f"{i}. **{song['title'][:40]}**")
        
        embed.add_field(
            name=f"📋 Up Next ({len(player.queue)} songs)",
            value="\n".join(queue_text) if queue_text else "Empty",
            inline=False
        )
    
    embed.add_field(name="🔊 Volume", value=f"{player.volume}%", inline=True)
    
    await ctx.send(embed=embed)

@bot.command(name='volume', aliases=['vol'])
async def volume(ctx, level: int = None):
    """🔊 Set volume (1-100)"""
    guild_id = ctx.guild.id
    
    if guild_id not in players:
        await ctx.send("❌ **No music playing!**")
        return
    
    player = players[guild_id]
    
    if level is None:
        await ctx.send(f"🔊 **Current volume:** `{player.volume}%`")
        return
    
    if not 1 <= level <= 100:
        await ctx.send("❌ **Volume must be 1-100!**")
        return
    
    player.volume = level
    await ctx.send(f"🔊 **Volume set to:** `{level}%`")

@bot.command(name='clear')
async def clear(ctx):
    """🗑️ Clear queue"""
    guild_id = ctx.guild.id
    
    if guild_id not in players:
        await ctx.send("❌ **Queue is empty!**")
        return
    
    player = players[guild_id]
    count = len(player.queue)
    player.queue.clear()
    
    await ctx.send(f"🗑️ **Cleared {count} songs!**")

@bot.command(name='leave', aliases=['dc'])
async def leave(ctx):
    """👋 Disconnect bot"""
    guild_id = ctx.guild.id
    
    if guild_id not in players:
        await ctx.send("❌ **I'm not in a voice channel!**")
        return
    
    player = players[guild_id]
    
    if player.voice:
        await player.voice.disconnect()
        await ctx.send("👋 **Disconnected!**")
    
    if guild_id in players:
        del players[guild_id]
    
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.listening,
            name="$help | Music Bot"
        )
    )

@bot.command(name='help')
async def help_command(ctx):
    """📖 Show all commands"""
    embed = discord.Embed(
        title="🎵 Music Bot Commands",
        description=f"**Prefix:** `{PREFIX}`\nKurdish Music Supported!",
        color=discord.Color.blue()
    )
    
    commands = {
        f"`{PREFIX}ping`": "🏓 Check bot latency",
        f"`{PREFIX}test`": "🧪 Test if bot works",
        f"`{PREFIX}hello`": "👋 Say hello",
        f"`{PREFIX}play` `<song>`": "🎵 Play a song",
        f"`{PREFIX}skip`": "⏭️ Skip current song",
        f"`{PREFIX}stop`": "⏹️ Stop and clear",
        f"`{PREFIX}pause`": "⏸️ Pause music",
        f"`{PREFIX}resume`": "▶️ Resume music",
        f"`{PREFIX}queue`": "📋 Show queue",
        f"`{PREFIX}volume` `<1-100>`": "🔊 Set volume",
        f"`{PREFIX}clear`": "🗑️ Clear queue",
        f"`{PREFIX}leave`": "👋 Disconnect bot",
        f"`{PREFIX}help`": "📖 This help"
    }
    
    for cmd, desc in commands.items():
        embed.add_field(name=cmd, value=desc, inline=False)
    
    await ctx.send(embed=embed)

# ============================================
# RUN BOT
# ============================================

if __name__ == "__main__":
    try:
        print("🚀 Starting bot...")
        bot.run(TOKEN, reconnect=True)
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)
