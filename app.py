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

# Check for voice library
try:
    import nacl
    print(f"✅ PyNaCl version: {nacl.__version__}")
except ImportError:
    print("❌ PyNaCl not installed! Installing...")
    os.system("pip install PyNaCl>=1.5.0")
    import nacl
    print(f"✅ PyNaCl installed successfully!")

# Setup logging for Railway
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Bot configuration - Get token from environment variable
TOKEN = os.environ.get('DISCORD_TOKEN') or os.environ.get('BOT_TOKEN')
if not TOKEN:
    logger.error("❌ No token found! Please set DISCORD_TOKEN environment variable")
    sys.exit(1)

PREFIX = '$'

# Intents setup
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix=PREFIX, intents=intents, help_command=None)

# Rest of your bot code here...
# (Keep your existing MusicPlayer class and commands)

# At the end, add better error handling for voice connection
@bot.event
async def on_voice_state_update(member, before, after):
    """Handle voice state updates with better error handling"""
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
                player = players[guild_id]
                if player.is_playing:
                    await asyncio.sleep(60)
                    if len(voice_channel.members) == 1:
                        try:
                            await player.voice_client.disconnect()
                        except:
                            pass
                        if guild_id in players:
                            del players[guild_id]

# Run the bot
if __name__ == "__main__":
    try:
        print("🚀 Starting bot...")
        print(f"📊 Python version: {sys.version}")
        bot.run(TOKEN, reconnect=True)
    except discord.LoginFailure as e:
        logger.error(f"❌ Login failed! Invalid token: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")
        sys.exit(1)
