#imports
import os
import re
from dotenv import load_dotenv
import discord
from discord.ext import commands
from cogs.message_tracking import MESSAGE_STATS, save_message_stats



load_dotenv()
TOKEN = os.getenv("DEV_BOT_TOKEN")
intents = discord.Intents.default()
intents.presences = True 
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="?", intents=intents)

@bot.event
async def setup_hook():
    await bot.load_extension("cogs.tournament")
    await bot.load_extension("cogs.moderation")
    await bot.load_extension("cogs.message_tracking")

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (id: {bot.user.id})")
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} commands")
    except Exception as e:
        print(f"Failed to sync commands: {e}")

@bot.event
async def on_message(message: discord.Message):
    if message.author == bot.user or not message.guild:
        return
    gid = str(message.guild.id)
    uid = str(message.author.id)
    if gid not in MESSAGE_STATS:
        MESSAGE_STATS[gid] = {}
    MESSAGE_STATS[gid][uid] = MESSAGE_STATS[gid].get(uid, 0) + 1
    save_message_stats()
    content = message.content.lower().strip()
    if "beep" in content:
        await message.channel.send("boop")
    elif "clanker" in content:
        await message.channel.send("shutup fleshbag")
    elif re.search(r'\bnya\b', content):
        await message.channel.send("ew.")
    elif re.search(r'\bbonk', content):
        await message.channel.send("https://tenor.com/view/bonk-gif-19410756")
    elif re.search(r'\bsimp\b', content):
        await message.channel.send("sniper monke")
    await bot.process_commands(message)

if __name__ == "__main__":
    bot.run(TOKEN)

