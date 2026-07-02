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
import json

# ============================================
# CONFIGURATION & SETUP
# ============================================

# Force install dependencies if missing
try:
    import nacl
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "PyNaCl>=1.5.0"])
    import nacl

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Bot configuration
TOKEN = os.environ.get('DISCORD_TOKEN') or os.environ.get('BOT_TOKEN')
if not TOKEN:
    logger.error("❌ No token found! Set DISCORD_TOKEN environment variable")
    sys.exit(1)

PREFIX = '$'
VERSION = "2.0.0"

# ============================================
# DISCORD BOT INITIALIZATION
# ============================================

intents = discord.Intents.all()
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

class GuildMusicPlayer:
    """Advanced music player for each guild"""
    
    def __init__(self, guild_id):
        self.guild_id = guild_id
        self.queue = deque()
        self.current = None
        self.voice = None
        self.is_playing = False
        self.is_paused = False
        self.loop_mode = 'off'  # off, single, queue
        self.volume = 100
        self.requester = None
        self.start_time = 0
        self.last_update = time.time()
        self.history = deque(maxlen=20)
    
    def add(self, song):
        """Add song to queue"""
        self.queue.append(song)
        return len(self.queue)
    
    def next(self):
        """Get next song from queue"""
        if self.queue:
            return self.queue.popleft()
        return None
    
    def clear(self):
        """Clear the queue"""
        self.queue.clear()
        self.history.clear()
    
    def shuffle(self):
        """Shuffle the queue"""
        if len(self.queue) > 1:
            temp = list(self.queue)
            random.shuffle(temp)
            self.queue = deque(temp)
            return True
        return False
    
    def remove(self, position):
        """Remove song at position"""
        if 0 <= position < len(self.queue):
            temp = list(self.queue)
            removed = temp.pop(position)
            self.queue = deque(temp)
            return removed
        return None
    
    def get_queue_info(self):
        """Get formatted queue information"""
        songs = []
        total_duration = 0
        
        for i, song in enumerate(list(self.queue)[:10], 1):
            duration = song.get('duration', 0)
            total_duration += duration
            minutes = duration // 60
            seconds = duration % 60
            songs.append(f"{i}. **{song['title'][:50]}** ({minutes}:{seconds:02d})")
        
        return songs, total_duration
    
    def format_duration(self, seconds):
        """Format duration in seconds to readable format"""
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60
        
        if hours > 0:
            return f"{hours}h {minutes}m {secs}s"
        elif minutes > 0:
            return f"{minutes}m {secs}s"
        else:
            return f"{secs}s"

# ============================================
# YOUTUBE HANDLING
# ============================================

class YouTubeHandler:
    """Handles YouTube searching and extraction"""
    
    @staticmethod
    def get_ydl_opts():
        """Get youtube-dl options for fast extraction"""
        return {
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
            'cookiefile': 'cookies.txt' if os.path.exists('cookies.txt') else None,
            'extractor_args': {
                'youtube': {
                    'skip': ['hls', 'dash'],
                    'player_client': ['android', 'web'],
                }
            }
        }
    
    @staticmethod
    async def search(query, limit=1):
        """Search YouTube for videos"""
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'default_search': 'ytsearch',
            'ignoreerrors': True,
            'no_check_certificate': True,
            'socket_timeout': 30,
            'retries': 3,
        }
        
        search_query = f"ytsearch{limit}:{query}"
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
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
    
    @staticmethod
    async def get_info(url):
        """Get video information from URL"""
        with yt_dlp.YoutubeDL(YouTubeHandler.get_ydl_opts()) as ydl:
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
# AUDIO PLAYBACK
# ============================================

ffmpeg_options = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn -b:a 192k -bufsize 64k',
}

async def play_song(guild_id):
    """Play the next song in the queue"""
    if guild_id not in players:
        return
    
    player = players[guild_id]
    
    if not player.voice or not player.voice.is_connected():
        return
    
    if player.is_playing and not player.is_paused:
        return
    
    # Get next song based on loop mode
    if player.loop_mode == 'single' and player.current:
        song = player.current
    else:
        song = player.next()
        if not song and player.loop_mode == 'queue' and player.current:
            # Re-add current song to queue for queue loop
            player.add(player.current)
            song = player.next()
        
        if not song:
            return
    
    player.current = song
    player.is_playing = True
    player.is_paused = False
    player.start_time = time.time()
    
    try:
        info = await YouTubeHandler.get_info(song['url'])
        if not info:
            player.is_playing = False
            return
        
        # Create audio source
        audio_source = discord.FFmpegPCMAudio(info['url'], **ffmpeg_options)
        
        # Play with callback
        player.voice.play(
            audio_source,
            after=lambda e: asyncio.run_coroutine_threadsafe(
                on_song_end(guild_id, e), bot.loop
            )
        )
        
        # Apply volume
        if player.voice.source:
            player.voice.source = discord.PCMVolumeTransformer(
                player.voice.source,
                volume=player.volume / 100
            )
        
        # Update bot status
        await update_bot_status(guild_id)
        
        logger.info(f"🎵 Now playing: {song['title']} in guild {guild_id}")
        
    except Exception as e:
        logger.error(f"Play error: {e}")
        player.is_playing = False
        await on_song_end(guild_id, e)

async def on_song_end(guild_id, error=None):
    """Handle song completion"""
    if guild_id not in players:
        return
    
    player = players[guild_id]
    player.is_playing = False
    
    if error:
        logger.error(f"Song error in {guild_id}: {error}")
    
    # Add to history if not looping
    if player.current and player.loop_mode != 'single':
        player.history.append(player.current)
    
    # Handle loop modes
    if player.loop_mode == 'single' and player.current:
        await play_song(guild_id)
        return
    
    # Play next or disconnect
    if player.queue or (player.loop_mode == 'queue' and player.current):
        await play_song(guild_id)
    else:
        await update_bot_status(guild_id, idle=True)
        # Schedule auto-disconnect
        asyncio.create_task(auto_disconnect(guild_id))

async def auto_disconnect(guild_id):
    """Auto-disconnect after idle timeout"""
    await asyncio.sleep(180)  # 3 minutes
    
    if guild_id in players:
        player = players[guild_id]
        if not player.is_playing and not player.queue:
            try:
                if player.voice and player.voice.is_connected():
                    await player.voice.disconnect()
                logger.info(f"👋 Auto-disconnected from guild {guild_id}")
            except:
                pass
            if guild_id in players:
                del players[guild_id]

async def update_bot_status(guild_id, idle=False):
    """Update bot's presence status"""
    if guild_id not in players:
        await bot.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.listening,
                name="🎵 music | $help"
            )
        )
        return
    
    player = players[guild_id]
    
    if idle or not player.is_playing:
        await bot.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.listening,
                name="🎵 music | $help"
            )
        )
    elif player.current:
        title = player.current['title']
        if len(title) > 50:
            title = title[:47] + "..."
        await bot.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.listening,
                name=f"🎵 {title}"
            )
        )

# ============================================
# GLOBAL VARIABLES
# ============================================

players = {}

# ============================================
# COMMANDS
# ============================================

@bot.command(name='play', aliases=['p'])
async def play(ctx, *, query):
    """🎵 Play a song from YouTube - Supports Kurdish music!"""
    
    # Check voice channel
    if not ctx.author.voice:
        embed = discord.Embed(
            title="❌ Voice Channel Required",
            description="You need to be in a voice channel to use this command!",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)
        return
    
    # Initialize player
    guild_id = ctx.guild.id
    if guild_id not in players:
        players[guild_id] = GuildMusicPlayer(guild_id)
    
    player = players[guild_id]
    player.requester = ctx.author.display_name
    
    # Connect to voice
    voice_channel = ctx.author.voice.channel
    try:
        if not player.voice or not player.voice.is_connected():
            player.voice = await voice_channel.connect()
        elif player.voice.channel != voice_channel:
            await player.voice.move_to(voice_channel)
    except Exception as e:
        embed = discord.Embed(
            title="❌ Connection Failed",
            description=f"Could not connect to voice channel: {str(e)}",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)
        return
    
    # Search for song
    embed = discord.Embed(
        title="🔍 Searching...",
        description=f"Looking for `{query}`",
        color=discord.Color.blue()
    )
    msg = await ctx.send(embed=embed)
    
    try:
        # Check if URL
        is_url = urlparse(query).scheme in ('http', 'https')
        
        if is_url:
            song = await YouTubeHandler.get_info(query)
            if song:
                position = player.add(song)
                embed = discord.Embed(
                    title="✅ Added to Queue",
                    description=f"**{song['title']}**",
                    color=discord.Color.green()
                )
                embed.add_field(name="Position", value=f"#{position}", inline=True)
                embed.add_field(name="Duration", value=player.format_duration(song['duration']), inline=True)
                embed.add_field(name="Uploader", value=song['uploader'], inline=True)
                if song.get('thumbnail'):
                    embed.set_thumbnail(url=song['thumbnail'])
                await msg.edit(embed=embed)
            else:
                embed = discord.Embed(
                    title="❌ Not Found",
                    description="Could not find the video!",
                    color=discord.Color.red()
                )
                await msg.edit(embed=embed)
                return
        else:
            # Search for song (supports Kurdish)
            results = await YouTubeHandler.search(query, limit=3)
            if results:
                song = results[0]  # Take first result
                position = player.add(song)
                
                embed = discord.Embed(
                    title="✅ Added to Queue",
                    description=f"**{song['title']}**",
                    color=discord.Color.green()
                )
                embed.add_field(name="Position", value=f"#{position}", inline=True)
                embed.add_field(name="Duration", value=player.format_duration(song['duration']), inline=True)
                embed.add_field(name="Uploader", value=song['uploader'], inline=True)
                if song.get('thumbnail'):
                    embed.set_thumbnail(url=song['thumbnail'])
                
                # Show alternative results if available
                if len(results) > 1:
                    alternatives = []
                    for i, res in enumerate(results[1:], 2):
                        alternatives.append(f"{i}. {res['title'][:40]}")
                    embed.add_field(
                        name="📋 Other Results",
                        value="\n".join(alternatives[:2]),
                        inline=False
                    )
                
                await msg.edit(embed=embed)
            else:
                embed = discord.Embed(
                    title="❌ No Results",
                    description=f"Could not find anything for `{query}`. Try different keywords!",
                    color=discord.Color.red()
                )
                await msg.edit(embed=embed)
                return
        
        # Start playing if not already
        if not player.is_playing:
            await play_song(guild_id)
            
    except Exception as e:
        logger.error(f"Play error: {e}")
        embed = discord.Embed(
            title="❌ Error",
            description=f"Something went wrong: {str(e)}",
            color=discord.Color.red()
        )
        await msg.edit(embed=embed)

@bot.command(name='skip', aliases=['s', 'next'])
async def skip(ctx):
    """⏭️ Skip the current song"""
    guild_id = ctx.guild.id
    
    if guild_id not in players:
        embed = discord.Embed(
            title="❌ No Music",
            description="Nothing is playing right now!",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)
        return
    
    player = players[guild_id]
    
    if not player.is_playing:
        embed = discord.Embed(
            title="❌ No Music",
            description="Nothing is playing right now!",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)
        return
    
    if player.voice:
        player.voice.stop()
        embed = discord.Embed(
            title="⏭️ Skipped",
            description=f"Skipped **{player.current['title']}**",
            color=discord.Color.orange()
        )
        await ctx.send(embed=embed)

@bot.command(name='stop', aliases=['end'])
async def stop(ctx):
    """⏹️ Stop playback and clear the queue"""
    guild_id = ctx.guild.id
    
    if guild_id not in players:
        embed = discord.Embed(
            title="❌ No Music",
            description="Nothing is playing right now!",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)
        return
    
    player = players[guild_id]
    
    if player.voice:
        player.voice.stop()
        player.is_playing = False
        player.current = None
    
    player.clear()
    
    embed = discord.Embed(
        title="⏹️ Stopped",
        description="Playback stopped and queue cleared!",
        color=discord.Color.blue()
    )
    await ctx.send(embed=embed)
    
    await update_bot_status(guild_id, idle=True)

@bot.command(name='pause')
async def pause(ctx):
    """⏸️ Pause the current song"""
    guild_id = ctx.guild.id
    
    if guild_id not in players:
        embed = discord.Embed(
            title="❌ No Music",
            description="Nothing is playing right now!",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)
        return
    
    player = players[guild_id]
    
    if not player.is_playing:
        embed = discord.Embed(
            title="❌ No Music",
            description="Nothing is playing right now!",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)
        return
    
    if player.is_paused:
        embed = discord.Embed(
            title="⏸️ Already Paused",
            description="Music is already paused!",
            color=discord.Color.orange()
        )
        await ctx.send(embed=embed)
        return
    
    if player.voice and player.voice.is_playing():
        player.voice.pause()
        player.is_paused = True
        
        embed = discord.Embed(
            title="⏸️ Paused",
            description=f"Paused **{player.current['title']}**",
            color=discord.Color.blue()
        )
        await ctx.send(embed=embed)

@bot.command(name='resume')
async def resume(ctx):
    """▶️ Resume the current song"""
    guild_id = ctx.guild.id
    
    if guild_id not in players:
        embed = discord.Embed(
            title="❌ No Music",
            description="Nothing is playing right now!",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)
        return
    
    player = players[guild_id]
    
    if not player.is_paused:
        embed = discord.Embed(
            title="▶️ Not Paused",
            description="Music is not paused!",
            color=discord.Color.orange()
        )
        await ctx.send(embed=embed)
        return
    
    if player.voice:
        player.voice.resume()
        player.is_paused = False
        
        embed = discord.Embed(
            title="▶️ Resumed",
            description=f"Resumed **{player.current['title']}**",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)

@bot.command(name='queue', aliases=['q', 'list'])
async def show_queue(ctx):
    """📋 Show the current queue"""
    guild_id = ctx.guild.id
    
    if guild_id not in players:
        embed = discord.Embed(
            title="📋 Queue",
            description="The queue is empty!",
            color=discord.Color.blue()
        )
        await ctx.send(embed=embed)
        return
    
    player = players[guild_id]
    
    embed = discord.Embed(
        title="🎵 Music Queue",
        color=discord.Color.blue()
    )
    
    # Current song
    if player.current and player.is_playing:
        embed.add_field(
            name="▶️ Now Playing",
            value=f"**{player.current['title']}**\n⏱️ {player.format_duration(player.current['duration'])}",
            inline=False
        )
    
    # Queue
    songs, total = player.get_queue_info()
    if songs:
        embed.add_field(
            name=f"📋 Up Next ({len(player.queue)} songs)",
            value="\n".join(songs) if songs else "Empty",
            inline=False
        )
        
        if total > 0:
            embed.add_field(
                name="⏱️ Total Duration",
                value=player.format_duration(total),
                inline=True
            )
    else:
        embed.add_field(
            name="📋 Up Next",
            value="No more songs in queue",
            inline=False
        )
    
    # Loop mode
    loop_emoji = {
        'off': '⏹️',
        'single': '🔁',
        'queue': '🔄'
    }
    embed.add_field(
        name="🔄 Loop Mode",
        value=f"{loop_emoji.get(player.loop_mode, '⏹️')} {player.loop_mode.title()}",
        inline=True
    )
    
    embed.add_field(
        name="🔊 Volume",
        value=f"{player.volume}%",
        inline=True
    )
    
    await ctx.send(embed=embed)

@bot.command(name='nowplaying', aliases=['np', 'current'])
async def nowplaying(ctx):
    """🎵 Show currently playing song"""
    guild_id = ctx.guild.id
    
    if guild_id not in players:
        embed = discord.Embed(
            title="❌ No Music",
            description="Nothing is playing right now!",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)
        return
    
    player = players[guild_id]
    
    if not player.current or not player.is_playing:
        embed = discord.Embed(
            title="❌ No Music",
            description="Nothing is playing right now!",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)
        return
    
    song = player.current
    progress = int((time.time() - player.start_time) % song['duration']) if song['duration'] > 0 else 0
    
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
        value=f"{player.format_duration(progress)} / {player.format_duration(song['duration'])}",
        inline=True
    )
    
    embed.add_field(
        name="👤 Uploader",
        value=song['uploader'],
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
    
    # Progress bar
    if song['duration'] > 0:
        bar_length = 20
        filled = int((progress / song['duration']) * bar_length)
        bar = '▬' * filled + '🔘' + '▬' * (bar_length - filled)
        embed.add_field(
            name="📊 Progress",
            value=f"`{bar}`",
            inline=False
        )
    
    await ctx.send(embed=embed)

@bot.command(name='volume', aliases=['vol'])
async def volume(ctx, level: int = None):
    """🔊 Set volume (1-100)"""
    guild_id = ctx.guild.id
    
    if guild_id not in players:
        embed = discord.Embed(
            title="❌ No Music",
            description="Nothing is playing right now!",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)
        return
    
    player = players[guild_id]
    
    if level is None:
        embed = discord.Embed(
            title="🔊 Current Volume",
            description=f"Volume is at **{player.volume}%**",
            color=discord.Color.blue()
        )
        await ctx.send(embed=embed)
        return
    
    if not 1 <= level <= 100:
        embed = discord.Embed(
            title="❌ Invalid Volume",
            description="Volume must be between **1** and **100**!",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)
        return
    
    player.volume = level
    
    if player.voice and player.voice.source:
        if hasattr(player.voice.source, 'volume'):
            player.voice.source.volume = level / 100
    
    embed = discord.Embed(
        title="🔊 Volume Updated",
        description=f"Volume set to **{level}%**",
        color=discord.Color.green()
    )
    await ctx.send(embed=embed)

@bot.command(name='loop')
async def loop(ctx):
    """🔁 Toggle single song loop"""
    guild_id = ctx.guild.id
    
    if guild_id not in players:
        embed = discord.Embed(
            title="❌ No Music",
            description="Nothing is playing right now!",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)
        return
    
    player = players[guild_id]
    
    if player.loop_mode == 'off':
        player.loop_mode = 'single'
        status = "🔁 **Single Loop Enabled**"
        description = "Current song will repeat endlessly!"
    elif player.loop_mode == 'single':
        player.loop_mode = 'queue'
        status = "🔄 **Queue Loop Enabled**"
        description = "The entire queue will repeat!"
    else:
        player.loop_mode = 'off'
        status = "⏹️ **Loop Disabled**"
        description = "Normal playback resumed!"
    
    embed = discord.Embed(
        title=status,
        description=description,
        color=discord.Color.blue()
    )
    await ctx.send(embed=embed)

@bot.command(name='shuffle')
async def shuffle(ctx):
    """🔀 Shuffle the queue"""
    guild_id = ctx.guild.id
    
    if guild_id not in players:
        embed = discord.Embed(
            title="❌ No Songs",
            description="The queue is empty!",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)
        return
    
    player = players[guild_id]
    
    if player.shuffle():
        embed = discord.Embed(
            title="🔀 Shuffled",
            description=f"Shuffled **{len(player.queue)}** songs in the queue!",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)
    else:
        embed = discord.Embed(
            title="❌ Cannot Shuffle",
            description="Need at least **2** songs in the queue to shuffle!",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)

@bot.command(name='clear')
async def clear(ctx):
    """🗑️ Clear the queue"""
    guild_id = ctx.guild.id
    
    if guild_id not in players:
        embed = discord.Embed(
            title="❌ No Songs",
            description="The queue is empty!",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)
        return
    
    player = players[guild_id]
    count = len(player.queue)
    player.clear()
    
    embed = discord.Embed(
        title="🗑️ Queue Cleared",
        description=f"Removed **{count}** songs from the queue!",
        color=discord.Color.orange()
    )
    await ctx.send(embed=embed)

@bot.command(name='remove', aliases=['rm'])
async def remove(ctx, position: int):
    """🗑️ Remove a song from queue by position"""
    guild_id = ctx.guild.id
    
    if guild_id not in players:
        embed = discord.Embed(
            title="❌ No Songs",
            description="The queue is empty!",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)
        return
    
    player = players[guild_id]
    
    if not player.queue:
        embed = discord.Embed(
            title="❌ No Songs",
            description="The queue is empty!",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)
        return
    
    removed = player.remove(position - 1)
    if removed:
        embed = discord.Embed(
            title="🗑️ Song Removed",
            description=f"Removed **{removed['title']}** from the queue!",
            color=discord.Color.orange()
        )
        await ctx.send(embed=embed)
    else:
        embed = discord.Embed(
            title="❌ Invalid Position",
            description=f"Position must be between **1** and **{len(player.queue)}**!",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)

@bot.command(name='move')
async def move(ctx, from_pos: int, to_pos: int):
    """📦 Move a song in the queue"""
    guild_id = ctx.guild.id
    
    if guild_id not in players:
        embed = discord.Embed(
            title="❌ No Songs",
            description="The queue is empty!",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)
        return
    
    player = players[guild_id]
    
    if len(player.queue) < 2:
        embed = discord.Embed(
            title="❌ Cannot Move",
            description="Need at least **2** songs in the queue!",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)
        return
    
    if not (1 <= from_pos <= len(player.queue) and 1 <= to_pos <= len(player.queue)):
        embed = discord.Embed(
            title="❌ Invalid Position",
            description=f"Positions must be between **1** and **{len(player.queue)}**!",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)
        return
    
    temp = list(player.queue)
    song = temp.pop(from_pos - 1)
    temp.insert(to_pos - 1, song)
    player.queue = deque(temp)
    
    embed = discord.Embed(
        title="📦 Song Moved",
        description=f"Moved **{song['title']}** from position `{from_pos}` to `{to_pos}`!",
        color=discord.Color.green()
    )
    await ctx.send(embed=embed)

@bot.command(name='leave', aliases=['dc', 'disconnect'])
async def leave(ctx):
    """👋 Disconnect the bot from voice channel"""
    guild_id = ctx.guild.id
    
    if guild_id not in players:
        embed = discord.Embed(
            title="❌ Not Connected",
            description="I'm not in a voice channel!",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)
        return
    
    player = players[guild_id]
    
    if player.voice:
        await player.voice.disconnect()
        embed = discord.Embed(
            title="👋 Disconnected",
            description="Left the voice channel!",
            color=discord.Color.blue()
        )
        await ctx.send(embed=embed)
    
    if guild_id in players:
        del players[guild_id]
    
    await update_bot_status(guild_id, idle=True)

@bot.command(name='help')
async def help_command(ctx):
    """📖 Show all available commands"""
    embed = discord.Embed(
        title="🎵 Music Bot Commands",
        description=f"**Prefix:** `{PREFIX}`\n**Version:** {VERSION}\nFast & Reliable Music Bot with Kurdish Support!",
        color=discord.Color.blue()
    )
    
    commands_info = {
        f"**{PREFIX}play** `<song/url>`": "🎵 Play a song from YouTube",
        f"**{PREFIX}skip**": "⏭️ Skip the current song",
        f"**{PREFIX}stop**": "⏹️ Stop playback and clear queue",
        f"**{PREFIX}pause**": "⏸️ Pause the current song",
        f"**{PREFIX}resume**": "▶️ Resume the current song",
        f"**{PREFIX}queue**": "📋 Show the current queue",
        f"**{PREFIX}nowplaying**": "🎵 Show currently playing song",
        f"**{PREFIX}volume** `<1-100>`": "🔊 Adjust volume",
        f"**{PREFIX}loop**": "🔁 Toggle loop modes (Single/Queue/Off)",
        f"**{PREFIX}shuffle**": "🔀 Shuffle the queue",
        f"**{PREFIX}clear**": "🗑️ Clear the queue",
        f"**{PREFIX}remove** `<position>`": "🗑️ Remove song from queue",
        f"**{PREFIX}move** `<from> <to>`": "📦 Move song in queue",
        f"**{PREFIX}leave**": "👋 Disconnect the bot",
        f"**{PREFIX}help**": "📖 Show this help message"
    }
    
    for cmd, desc in commands_info.items():
        embed.add_field(name=cmd, value=desc, inline=False)
    
    embed.set_footer(text="💡 Supports Kurdish music! Just use $play [song name]")
    await ctx.send(embed=embed)

@bot.command(name='invite')
async def invite(ctx):
    """🔗 Get bot invite link"""
    embed = discord.Embed(
        title="🤖 Invite Me!",
        description="Add this bot to your server!",
        color=discord.Color.blue()
    )
    
    if bot.user:
        invite_url = f"https://discord.com/oauth2/authorize?client_id={bot.user.id}&permissions=36700160&scope=bot%20applications.commands"
        embed.add_field(
            name="🔗 Invite Link",
            value=f"[Click Here to Invite]({invite_url})",
            inline=False
        )
    
    await ctx.send(embed=embed)

@bot.command(name='stats')
async def stats(ctx):
    """📊 Show bot statistics"""
    embed = discord.Embed(
        title="📊 Bot Statistics",
        color=discord.Color.blue()
    )
    
    embed.add_field(
        name="🤖 Bot Name",
        value=bot.user.name if bot.user else "Unknown",
        inline=True
    )
    
    embed.add_field(
        name="🏠 Servers",
        value=str(len(bot.guilds)),
        inline=True
    )
    
    embed.add_field(
        name="👥 Users",
        value=str(sum(guild.member_count for guild in bot.guilds)),
        inline=True
    )
    
    total_players = len(players)
    total_queue = sum(len(p.queue) for p in players.values())
    total_playing = sum(1 for p in players.values() if p.is_playing)
    
    embed.add_field(
        name="🎵 Active Players",
        value=str(total_players),
        inline=True
    )
    
    embed.add_field(
        name="📋 Total Queue",
        value=str(total_queue),
        inline=True
    )
    
    embed.add_field(
        name="▶️ Currently Playing",
        value=str(total_playing),
        inline=True
    )
    
    embed.set_footer(text=f"Version {VERSION} | Prefix: {PREFIX}")
    await ctx.send(embed=embed)

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
    print(f"👥 Users: {sum(guild.member_count for guild in bot.guilds)}")
    print("=" * 50)
    print("✅ Ready for commands!")
    print("💡 Supports Kurdish songs!")
    print("=" * 50)
    
    # Set initial status
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.listening,
            name="🎵 $help | Kurdish Support"
        )
    )

@bot.event
async def on_command_error(ctx, error):
    """Global command error handler"""
    if isinstance(error, commands.CommandNotFound):
        return
    
    if isinstance(error, commands.MissingRequiredArgument):
        embed = discord.Embed(
            title="❌ Missing Argument",
            description=f"Please provide all required arguments!\nUse `{PREFIX}help` for more info.",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)
        return
    
    if isinstance(error, commands.BadArgument):
        embed = discord.Embed(
            title="❌ Invalid Argument",
            description="Please provide a valid argument!\nUse `{PREFIX}help` for more info.",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)
        return
    
    logger.error(f"Command error in {ctx.guild.name}: {error}")
    
    embed = discord.Embed(
        title="❌ Error",
        description=f"An error occurred: {str(error)}",
        color=discord.Color.red()
    )
    await ctx.send(embed=embed)

@bot.event
async def on_voice_state_update(member, before, after):
    """Handle voice state updates"""
    # Ignore if bot is not involved
    if member.id != bot.user.id:
        # Check if bot is alone in voice channel
        guild = member.guild
        bot_member = guild.get_member(bot.user.id)
        
        if bot_member and bot_member.voice:
            voice_channel = bot_member.voice.channel
            if before.channel == voice_channel and len(voice_channel.members) == 1:
                # Bot is alone, schedule disconnect
                guild_id = guild.id
                if guild_id in players:
                    asyncio.create_task(auto_disconnect(guild_id))
        return
    
    # Bot's own voice state changed
    if after.channel is None:
        # Bot disconnected
        guild_id = member.guild.id
        if guild_id in players:
            player = players[guild_id]
            player.is_playing = False
            player.current = None
            del players[guild_id]
            logger.info(f"🗑️ Cleared player for guild {guild_id}")

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
