import discord
from discord.ext import commands
import yt_dlp
import asyncio
import os
from collections import deque
import random
import time
from urllib.parse import urlparse, parse_qs

# Bot configuration
TOKEN = 'YOUR_BOT_TOKEN_HERE'
PREFIX = '$'

# Intents setup
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

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
        self.skip_votes = set()
        self.volume = 100
        self.last_activity = time.time()

    def add_to_queue(self, song_data):
        self.queue.append(song_data)
        return len(self.queue)

    def clear_queue(self):
        self.queue.clear()
        self.skip_votes.clear()

    def get_next_song(self):
        if self.queue:
            return self.queue.popleft()
        return None

# Dictionary to store guild players
players = {}

# YT-DL options for fast searching and downloading
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
    'postprocessors': [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'mp3',
        'preferredquality': '192',
    }],
    'cookiefile': 'cookies.txt' if os.path.exists('cookies.txt') else None,
}

# FFmpeg options for streaming
ffmpeg_options = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn -b:a 192k -bufsize 64k',
}

async def search_youtube(query, limit=5):
    """Search YouTube for videos matching the query"""
    search_query = f"ytsearch{limit}:{query}"
    
    with yt_dlp.YoutubeDL({'quiet': True, 'no_warnings': True, 'extract_flat': False}) as ydl:
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
                            'source': 'youtube'
                        })
                return results
        except Exception as e:
            print(f"Search error: {e}")
            return None

async def get_video_info(url):
    """Get video information from URL or query"""
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
                'source': 'youtube'
            }
        except Exception as e:
            print(f"Error getting video info: {e}")
            return None

async def play_song(guild_id):
    """Play the next song in the queue"""
    if guild_id not in players:
        return
    
    player = players[guild_id]
    
    if not player.voice_client or not player.voice_client.is_connected():
        return
    
    if player.is_playing and not player.is_paused:
        return
    
    # Check if we should loop the current song
    if player.loop and player.current_song:
        song = player.current_song
    else:
        # Get next song from queue
        song = player.get_next_song()
        if not song:
            # Check if queue looping is enabled
            if player.loop_queue and player.current_song:
                # Re-add the current song to queue if available
                if player.current_song:
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
        
        # Create FFmpeg audio source
        audio_source = discord.FFmpegPCMAudio(info['url'], **ffmpeg_options)
        
        # Play the audio
        player.voice_client.play(
            audio_source,
            after=lambda e: asyncio.run_coroutine_threadsafe(
                on_song_end(guild_id, e), bot.loop
            )
        )
        
        # Update volume
        player.voice_client.source = discord.PCMVolumeTransformer(
            player.voice_client.source,
            volume=player.volume / 100
        )
        
        # Update activity
        player.last_activity = time.time()
        
    except Exception as e:
        print(f"Error playing song: {e}")
        player.is_playing = False
        await on_song_end(guild_id, e)

async def on_song_end(guild_id, error=None):
    """Handle song end event"""
    if guild_id not in players:
        return
    
    player = players[guild_id]
    player.is_playing = False
    
    if error:
        print(f"Song ended with error: {error}")
    
    # Check if loop is enabled
    if player.loop and player.current_song:
        await play_song(guild_id)
        return
    
    # Check if queue loop is enabled
    if player.loop_queue and player.current_song:
        player.queue.append(player.current_song)
    
    # Play next song
    if player.queue or (player.loop_queue and player.current_song):
        await play_song(guild_id)
    else:
        # No more songs, disconnect after idle
        await bot.loop.create_task(disconnect_after_idle(guild_id))

async def disconnect_after_idle(guild_id):
    """Disconnect after idle timeout"""
    if guild_id not in players:
        return
    
    player = players[guild_id]
    await asyncio.sleep(180)  # 3 minutes idle timeout
    
    if not player.is_playing and not player.queue:
        if player.voice_client and player.voice_client.is_connected():
            await player.voice_client.disconnect()
        if guild_id in players:
            del players[guild_id]

# Commands

@bot.command(name='play', aliases=['p'])
async def play(ctx, *, query):
    """Play a song from YouTube (supports Kurdish music)"""
    if not ctx.author.voice:
        await ctx.send("❌ You need to be in a voice channel!")
        return
    
    voice_channel = ctx.author.voice.channel
    guild_id = ctx.guild.id
    
    # Create player if doesn't exist
    if guild_id not in players:
        players[guild_id] = MusicPlayer(guild_id)
    
    player = players[guild_id]
    
    # Connect to voice channel
    if not player.voice_client or not player.voice_client.is_connected():
        try:
            player.voice_client = await voice_channel.connect()
        except Exception as e:
            await ctx.send(f"❌ Failed to connect: {str(e)}")
            return
    elif player.voice_client.channel != voice_channel:
        await player.voice_client.move_to(voice_channel)
    
    # Search for the song
    status_msg = await ctx.send(f"🔍 Searching for `{query}`...")
    
    try:
        # Check if it's a URL
        is_url = urlparse(query).scheme in ('http', 'https')
        
        if is_url:
            song_info = await get_video_info(query)
            if song_info:
                song_info['source'] = 'youtube'
                player.add_to_queue(song_info)
                await status_msg.edit(content=f"✅ Added to queue: **{song_info['title']}**")
            else:
                await status_msg.edit(content="❌ Could not find the video!")
                return
        else:
            # Search for the song
            search_results = await search_youtube(query, limit=1)
            if search_results:
                song_info = search_results[0]
                player.add_to_queue(song_info)
                await status_msg.edit(content=f"✅ Added to queue: **{song_info['title']}**")
            else:
                await status_msg.edit(content="❌ No results found!")
                return
        
        # Start playing if not already playing
        if not player.is_playing:
            await play_song(guild_id)
            
    except Exception as e:
        await status_msg.edit(content=f"❌ Error: {str(e)}")

@bot.command(name='search')
async def search(ctx, *, query):
    """Search for songs and add them to queue"""
    if not ctx.author.voice:
        await ctx.send("❌ You need to be in a voice channel!")
        return
    
    await ctx.send(f"🔍 Searching for `{query}`...")
    
    results = await search_youtube(query, limit=5)
    if not results:
        await ctx.send("❌ No results found!")
        return
    
    # Create selection message
    embed = discord.Embed(
        title="🎵 Search Results",
        color=discord.Color.blue()
    )
    
    for i, result in enumerate(results, 1):
        duration = result['duration']
        minutes = duration // 60
        seconds = duration % 60
        embed.add_field(
            name=f"{i}. {result['title']}",
            value=f"⏱️ {minutes}:{seconds:02d} | 👤 {result['uploader']}",
            inline=False
        )
    
    embed.set_footer(text="Type the number (1-5) to add to queue, or cancel")
    
    msg = await ctx.send(embed=embed)
    
    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel
    
    try:
        response = await bot.wait_for('message', timeout=30.0, check=check)
        
        if response.content.lower() in ['cancel', 'stop']:
            await ctx.send("❌ Search cancelled!")
            return
        
        try:
            choice = int(response.content) - 1
            if 0 <= choice < len(results):
                song = results[choice]
                
                # Get voice channel
                voice_channel = ctx.author.voice.channel
                guild_id = ctx.guild.id
                
                # Create player if doesn't exist
                if guild_id not in players:
                    players[guild_id] = MusicPlayer(guild_id)
                
                player = players[guild_id]
                
                # Connect to voice channel
                if not player.voice_client or not player.voice_client.is_connected():
                    player.voice_client = await voice_channel.connect()
                
                # Add to queue
                player.add_to_queue(song)
                await ctx.send(f"✅ Added to queue: **{song['title']}**")
                
                # Start playing if not already playing
                if not player.is_playing:
                    await play_song(guild_id)
            else:
                await ctx.send("❌ Invalid choice!")
        except ValueError:
            await ctx.send("❌ Please enter a valid number!")
            
    except asyncio.TimeoutError:
        await ctx.send("⏰ Selection timed out!")

@bot.command(name='skip', aliases=['s'])
async def skip(ctx):
    """Skip the current song"""
    guild_id = ctx.guild.id
    
    if guild_id not in players:
        await ctx.send("❌ No music is playing!")
        return
    
    player = players[guild_id]
    
    if not player.is_playing:
        await ctx.send("❌ No music is playing!")
        return
    
    # Check if user is in voice channel
    if not ctx.author.voice:
        await ctx.send("❌ You need to be in a voice channel!")
        return
    
    # Skip voting (3 votes needed for others, 1 for the requester)
    if player.current_song and ctx.author.id != 0:  # You can add requester ID check
        # Simple skip without voting (like Lara Bot)
        if player.voice_client:
            player.voice_client.stop()
            await ctx.send("⏭️ Skipped the current song!")
        else:
            await ctx.send("❌ No audio is playing!")

@bot.command(name='queue', aliases=['q'])
async def queue(ctx):
    """Display the current queue"""
    guild_id = ctx.guild.id
    
    if guild_id not in players:
        await ctx.send("❌ No songs in queue!")
        return
    
    player = players[guild_id]
    
    if not player.queue and not player.current_song:
        await ctx.send("❌ No songs in queue!")
        return
    
    embed = discord.Embed(
        title="🎵 Queue",
        color=discord.Color.blue()
    )
    
    # Current song
    if player.current_song:
        duration = player.current_song.get('duration', 0)
        minutes = duration // 60
        seconds = duration % 60
        embed.add_field(
            name="🎵 Now Playing",
            value=f"**{player.current_song['title']}**\n⏱️ {minutes}:{seconds:02d}",
            inline=False
        )
    
    # Queue
    if player.queue:
        queue_list = []
        total_duration = 0
        
        for i, song in enumerate(list(player.queue)[:10], 1):
            duration = song.get('duration', 0)
            total_duration += duration
            minutes = duration // 60
            seconds = duration % 60
            queue_list.append(f"{i}. {song['title']} ({minutes}:{seconds:02d})")
        
        embed.add_field(
            name=f"📋 Up Next ({len(player.queue)} songs)",
            value="\n".join(queue_list) if queue_list else "No songs in queue",
            inline=False
        )
        
        # Total duration
        hours = total_duration // 3600
        minutes = (total_duration % 3600) // 60
        if hours > 0:
            embed.add_field(name="⏱️ Total Duration", value=f"{hours}h {minutes}m", inline=True)
        else:
            embed.add_field(name="⏱️ Total Duration", value=f"{minutes}m", inline=True)
    else:
        embed.add_field(name="📋 Up Next", value="No songs in queue", inline=False)
    
    # Loop status
    loop_status = []
    if player.loop:
        loop_status.append("🔁 Single Loop")
    if player.loop_queue:
        loop_status.append("🔁 Queue Loop")
    if not loop_status:
        loop_status.append("⏹️ Loop Disabled")
    
    embed.add_field(name="🔄 Loop Mode", value="\n".join(loop_status), inline=True)
    
    await ctx.send(embed=embed)

@bot.command(name='stop')
async def stop(ctx):
    """Stop playback and clear queue"""
    guild_id = ctx.guild.id
    
    if guild_id not in players:
        await ctx.send("❌ No music is playing!")
        return
    
    player = players[guild_id]
    
    if player.voice_client:
        player.voice_client.stop()
        player.is_playing = False
        player.current_song = None
    
    player.clear_queue()
    
    await ctx.send("⏹️ Stopped playback and cleared queue!")

@bot.command(name='pause')
async def pause(ctx):
    """Pause the current song"""
    guild_id = ctx.guild.id
    
    if guild_id not in players:
        await ctx.send("❌ No music is playing!")
        return
    
    player = players[guild_id]
    
    if not player.is_playing or player.is_paused:
        await ctx.send("❌ No music is playing!")
        return
    
    if player.voice_client and player.voice_client.is_playing():
        player.voice_client.pause()
        player.is_paused = True
        await ctx.send("⏸️ Paused the music!")

@bot.command(name='resume', aliases=['unpause'])
async def resume(ctx):
    """Resume the current song"""
    guild_id = ctx.guild.id
    
    if guild_id not in players:
        await ctx.send("❌ No music is playing!")
        return
    
    player = players[guild_id]
    
    if not player.is_paused:
        await ctx.send("❌ Music is not paused!")
        return
    
    if player.voice_client:
        player.voice_client.resume()
        player.is_paused = False
        await ctx.send("▶️ Resumed the music!")

@bot.command(name='volume', aliases=['vol'])
async def volume(ctx, level: int = None):
    """Set the volume (1-100)"""
    guild_id = ctx.guild.id
    
    if guild_id not in players:
        await ctx.send("❌ No music is playing!")
        return
    
    player = players[guild_id]
    
    if level is None:
        await ctx.send(f"🔊 Current volume: **{player.volume}%**")
        return
    
    if not 1 <= level <= 100:
        await ctx.send("❌ Volume must be between 1 and 100!")
        return
    
    player.volume = level
    
    if player.voice_client and player.voice_client.source:
        if hasattr(player.voice_client.source, 'volume'):
            player.voice_client.source.volume = level / 100
    
    await ctx.send(f"🔊 Volume set to **{level}%**!")

@bot.command(name='loop')
async def loop(ctx):
    """Toggle single song loop"""
    guild_id = ctx.guild.id
    
    if guild_id not in players:
        await ctx.send("❌ No music is playing!")
        return
    
    player = players[guild_id]
    player.loop = not player.loop
    
    if player.loop:
        await ctx.send("🔁 **Loop enabled** - Current song will repeat!")
    else:
        await ctx.send("🔁 **Loop disabled**")

@bot.command(name='loopqueue', aliases=['loopq'])
async def loopqueue(ctx):
    """Toggle queue loop"""
    guild_id = ctx.guild.id
    
    if guild_id not in players:
        await ctx.send("❌ No music is playing!")
        return
    
    player = players[guild_id]
    player.loop_queue = not player.loop_queue
    
    if player.loop_queue:
        await ctx.send("🔁 **Queue loop enabled** - Queue will repeat!")
    else:
        await ctx.send("🔁 **Queue loop disabled**")

@bot.command(name='nowplaying', aliases=['np'])
async def nowplaying(ctx):
    """Show the currently playing song"""
    guild_id = ctx.guild.id
    
    if guild_id not in players:
        await ctx.send("❌ No music is playing!")
        return
    
    player = players[guild_id]
    
    if not player.current_song or not player.is_playing:
        await ctx.send("❌ No music is playing!")
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
    
    await ctx.send(embed=embed)

@bot.command(name='clear')
async def clear(ctx):
    """Clear the queue"""
    guild_id = ctx.guild.id
    
    if guild_id not in players:
        await ctx.send("❌ No songs in queue!")
        return
    
    player = players[guild_id]
    
    if not player.queue:
        await ctx.send("❌ No songs in queue!")
        return
    
    queue_size = len(player.queue)
    player.clear_queue()
    
    await ctx.send(f"🗑️ Cleared **{queue_size}** songs from queue!")

@bot.command(name='shuffle')
async def shuffle(ctx):
    """Shuffle the queue"""
    guild_id = ctx.guild.id
    
    if guild_id not in players:
        await ctx.send("❌ No songs in queue!")
        return
    
    player = players[guild_id]
    
    if len(player.queue) < 2:
        await ctx.send("❌ Need at least 2 songs to shuffle!")
        return
    
    queue_list = list(player.queue)
    random.shuffle(queue_list)
    player.queue = deque(queue_list)
    
    await ctx.send("🔀 **Shuffled the queue!**")

@bot.command(name='move', aliases=['mv'])
async def move(ctx, from_pos: int, to_pos: int):
    """Move a song in the queue"""
    guild_id = ctx.guild.id
    
    if guild_id not in players:
        await ctx.send("❌ No songs in queue!")
        return
    
    player = players[guild_id]
    
    if not player.queue or len(player.queue) < 2:
        await ctx.send("❌ Need at least 2 songs in queue!")
        return
    
    if from_pos < 1 or from_pos > len(player.queue) or to_pos < 1 or to_pos > len(player.queue):
        await ctx.send(f"❌ Positions must be between 1 and {len(player.queue)}!")
        return
    
    queue_list = list(player.queue)
    song = queue_list.pop(from_pos - 1)
    queue_list.insert(to_pos - 1, song)
    player.queue = deque(queue_list)
    
    await ctx.send(f"✅ Moved song from position {from_pos} to {to_pos}!")

@bot.command(name='remove', aliases=['rm'])
async def remove(ctx, position: int):
    """Remove a song from the queue"""
    guild_id = ctx.guild.id
    
    if guild_id not in players:
        await ctx.send("❌ No songs in queue!")
        return
    
    player = players[guild_id]
    
    if not player.queue:
        await ctx.send("❌ No songs in queue!")
        return
    
    if position < 1 or position > len(player.queue):
        await ctx.send(f"❌ Position must be between 1 and {len(player.queue)}!")
        return
    
    queue_list = list(player.queue)
    removed_song = queue_list.pop(position - 1)
    player.queue = deque(queue_list)
    
    await ctx.send(f"🗑️ Removed **{removed_song['title']}** from queue!")

@bot.command(name='help')
async def help_command(ctx):
    """Show all available commands"""
    embed = discord.Embed(
        title="🎵 Music Bot Commands",
        description=f"Prefix: `{PREFIX}`\nLike Lara Bot - Fast YouTube Music Player",
        color=discord.Color.blue()
    )
    
    commands_list = {
        f"{PREFIX}play <song>": "Play a song from YouTube (supports Kurdish music)",
        f"{PREFIX}search <song>": "Search and select from results",
        f"{PREFIX}skip": "Skip the current song",
        f"{PREFIX}queue": "Show the current queue",
        f"{PREFIX}nowplaying": "Show currently playing song",
        f"{PREFIX}pause": "Pause the current song",
        f"{PREFIX}resume": "Resume the paused song",
        f"{PREFIX}stop": "Stop playback and clear queue",
        f"{PREFIX}volume <1-100>": "Set the volume",
        f"{PREFIX}loop": "Toggle single song loop",
        f"{PREFIX}loopqueue": "Toggle queue loop",
        f"{PREFIX}shuffle": "Shuffle the queue",
        f"{PREFIX}clear": "Clear the queue",
        f"{PREFIX}remove <position>": "Remove a song from queue",
        f"{PREFIX}move <from> <to>": "Move a song in queue",
        f"{PREFIX}help": "Show this help message",
        f"{PREFIX}leave": "Disconnect the bot"
    }
    
    for cmd, desc in commands_list.items():
        embed.add_field(name=cmd, value=desc, inline=False)
    
    await ctx.send(embed=embed)

@bot.command(name='leave', aliases=['dc'])
async def leave(ctx):
    """Disconnect the bot from voice channel"""
    guild_id = ctx.guild.id
    
    if guild_id not in players:
        await ctx.send("❌ I'm not in a voice channel!")
        return
    
    player = players[guild_id]
    
    if player.voice_client:
        await player.voice_client.disconnect()
        player.is_playing = False
        player.current_song = None
        player.clear_queue()
        await ctx.send("👋 Disconnected from voice channel!")
    
    if guild_id in players:
        del players[guild_id]

@bot.command(name='invite')
async def invite(ctx):
    """Get invite link for the bot"""
    embed = discord.Embed(
        title="🤖 Bot Invite",
        description="Invite this bot to your server!",
        color=discord.Color.blue()
    )
    embed.add_field(
        name="🔗 Invite Link",
        value=f"[Click here to invite](https://discord.com/oauth2/authorize?client_id={bot.user.id}&permissions=36700160&scope=bot)",
        inline=False
    )
    await ctx.send(embed=embed)

# Event handlers
@bot.event
async def on_ready():
    print(f'🤖 Bot is ready!')
    print(f'📊 Connected as: {bot.user.name}')
    print(f'🔢 Bot ID: {bot.user.id}')
    print(f'📝 Prefix: {PREFIX}')
    print(f'🎵 Music commands loaded!')
    print('-' * 50)

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"❌ Missing required argument! Use `{PREFIX}help` for more info.")
        return
    
    if isinstance(error, commands.BadArgument):
        await ctx.send(f"❌ Invalid argument! Use `{PREFIX}help` for more info.")
        return
    
    print(f"Error: {error}")
    await ctx.send(f"❌ An error occurred: {str(error)}")

@bot.event
async def on_voice_state_update(member, before, after):
    """Handle voice state updates"""
    if member.id == bot.user.id:
        # Bot's voice state changed
        if after.channel is None:
            # Bot was disconnected
            guild_id = member.guild.id
            if guild_id in players:
                players[guild_id].is_playing = False
                players[guild_id].current_song = None
                del players[guild_id]
        return
    
    # Check if the bot is in the voice channel
    bot_member = member.guild.get_member(bot.user.id)
    if bot_member and bot_member.voice:
        voice_channel = bot_member.voice.channel
        if after.channel == voice_channel and not after.self_deaf:
            pass
        elif before.channel == voice_channel and len(voice_channel.members) == 1:
            # Bot is alone in voice channel
            guild_id = member.guild.id
            if guild_id in players:
                player = players[guild_id]
                if player.is_playing:
                    await asyncio.sleep(60)  # Wait 1 minute before disconnecting
                    if len(voice_channel.members) == 1:
                        await player.voice_client.disconnect()
                        del players[guild_id]

# Run the bot
if __name__ == "__main__":
    if TOKEN == 'YOUR_BOT_TOKEN_HERE':
        print("❌ Please add your bot token to the TOKEN variable!")
    else:
        bot.run(TOKEN)
