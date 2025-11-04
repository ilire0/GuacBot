import discord
from discord.ext import commands
from discord import app_commands
from pathlib import Path
import json
from typing import Optional

MESSAGE_STATS_FILE = Path("message_stats.json")

# Load existing stats
if MESSAGE_STATS_FILE.exists():
    with open(MESSAGE_STATS_FILE, "r", encoding="utf-8") as f:
        MESSAGE_STATS = json.load(f)
else:
    MESSAGE_STATS = {}

def save_message_stats():
    """Save MESSAGE_STATS to file."""
    with open(MESSAGE_STATS_FILE, "w", encoding="utf-8") as f:
        json.dump(MESSAGE_STATS, f, indent=2)

async def register_user_past_messages(
    guild: discord.Guild,
    user: discord.Member,
    limit_per_channel: int = 10000
):
    """Scan past messages of a user across all text channels."""
    gid = str(guild.id)
    uid = str(user.id)

    if gid not in MESSAGE_STATS:
        MESSAGE_STATS[gid] = {}

    total_added = 0

    for channel in guild.text_channels:
        if not channel.permissions_for(guild.me).read_messages:
            continue
        try:
            async for msg in channel.history(limit=limit_per_channel):
                if msg.author.id == user.id:
                    MESSAGE_STATS[gid][uid] = MESSAGE_STATS[gid].get(uid, 0) + 1
                    total_added += 1
        except discord.Forbidden:
            continue
        except Exception as e:
            print(f"Failed to scan channel {channel.name}: {e}")

    save_message_stats()
    return total_added

class MessageTrackingCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # Live message tracking
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        gid = str(message.guild.id)
        uid = str(message.author.id)

        if gid not in MESSAGE_STATS:
            MESSAGE_STATS[gid] = {}

        MESSAGE_STATS[gid][uid] = MESSAGE_STATS[gid].get(uid, 0) + 1
        save_message_stats()

    # Admin command to scan past messages
    @app_commands.command(
        name="register_past_messages_user",
        description="Register past messages of a user"
    )
    @app_commands.describe(user="User to scan", limit="Max messages per channel")
    @app_commands.checks.has_permissions(administrator=True)
    async def register_past_messages_user(
        self, interaction: discord.Interaction, user: discord.Member, limit: Optional[int] = 10000
    ):
        await interaction.response.send_message(
            f"Scanning past messages of {user.display_name}... This may take a while.",
            ephemeral=True
        )
        count = await register_user_past_messages(interaction.guild, user, limit)
        await interaction.followup.send(
            f"Registered {count} past messages for {user.display_name}.", ephemeral=True
        )

    # Command to view leaderboard
    @app_commands.command(
        name="yapper_leaderboard",
        description="Show the top message senders in this server"
    )
    async def leaderboard(self, interaction: discord.Interaction):
        gid = str(interaction.guild_id)
        if gid not in MESSAGE_STATS or not MESSAGE_STATS[gid]:
            return await interaction.response.send_message(
                "No messages recorded yet!", ephemeral=True
            )
        stats = MESSAGE_STATS[gid]
        sorted_stats = sorted(stats.items(), key=lambda x: x[1], reverse=True)
        lines = ["**Message Leaderboard:**"]
        for i, (uid, count) in enumerate(sorted_stats[:10], start=1):
            user = interaction.guild.get_member(int(uid))
            name = user.display_name if user else f"User {uid}"
            lines.append(f"{i}. **{name}** — {count} messages")
        await interaction.response.send_message("\n".join(lines))

async def setup(bot: commands.Bot):
    await bot.add_cog(MessageTrackingCog(bot))
