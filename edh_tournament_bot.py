"""
EDH FFA Tournament Discord Bot
- Supports 3-4 player pods per round (FFA style)
- Automatic round ending once all pods report results
- Points: 4-player pod: 1st=3, 2nd=2, 3rd=1, 4th=0
- Points: 3-player pod: 1st=3, 2nd=2, 3rd=0
- Slash commands support
- Persistent JSON storage
"""
import time
import asyncio
import re
import discord
from discord.ui import View, Button
from discord import Embed
from discord.ext import commands
from discord import app_commands
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional
import json, os, random, tempfile, shutil, atexit
from pathlib import Path
from dotenv import load_dotenv

def is_tournament_organizer():
    async def predicate(interaction: discord.Interaction) -> bool:
        # Allow server admins automatically
        if interaction.user.guild_permissions.administrator:
            return True  

        # Look for role by name
        role = discord.utils.get(interaction.guild.roles, name="Tournament Organizer")
        if role and role in interaction.user.roles:
            return True

        # Deny access politely
        await interaction.response.send_message(
            "🚫 You need the **Tournament Organizer** role to use this command.",
            ephemeral=True
        )
        return False
    return app_commands.check(predicate)

MESSAGE_STATS_FILE = Path("message_stats.json")

# Load existing message stats
if MESSAGE_STATS_FILE.exists():
    with open(MESSAGE_STATS_FILE, "r", encoding="utf-8") as f:
        MESSAGE_STATS = json.load(f)
else:
    MESSAGE_STATS = {}



# -----------------------------
# Load bot token
# -----------------------------
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise Exception("BOT_TOKEN not found in .env")

DATA_FILE = Path("tournaments.json")

# -----------------------------
# Intents and bot setup
# -----------------------------
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents, description="EDH FFA Tournament Bot")

@bot.event
async def setup_hook():
    # ✅ Proper way to start background tasks in discord.py 2.x+
    import asyncio
    asyncio.create_task(check_round_timeouts())


# -----------------------------
# Data structures
# -----------------------------
@dataclass
class Player:
    id: int
    name: str
    points: float = 0.0
    matches_played: int = 0

@dataclass
class Game:
    pod_number: int
    players: List[int]  # user IDs
    results_reported: bool = False
    results: Dict[int, int] = field(default_factory=dict)  # player_id -> points

@dataclass
class Round:
    number: int
    games: List[Game] = field(default_factory=list)
    active: bool = True
    start_time: Optional[float] = None  # when the round started (timestamp)
    notified_timeout: bool = False      # prevents repeated pings after timeout


@dataclass
class Tournament:
    id: str
    name: str
    host: int
    players: Dict[int, Player] = field(default_factory=dict)
    rounds: List[Round] = field(default_factory=list)
    finished: bool = False
    pod_size: int = 4
    max_rounds: int = 4
    time_limit: int = 90


# -----------------------------
# Persistence helpers
# -----------------------------
async def register_user_past_messages(guild: discord.Guild, user: discord.Member, limit_per_channel: int = 10000):
    """Scan past messages of a specific user in the server and update MESSAGE_STATS."""
    gid = str(guild.id)
    uid = str(user.id)

    if gid not in MESSAGE_STATS:
        MESSAGE_STATS[gid] = {}

    total_added = 0

    for channel in guild.text_channels:
        try:
            async for msg in channel.history(limit=limit_per_channel):
                if msg.author.id == user.id:
                    MESSAGE_STATS[gid][uid] = MESSAGE_STATS[gid].get(uid, 0) + 1
                    total_added += 1
        except Exception as e:
            print(f"Failed to scan channel {channel.name}: {e}")

    save_message_stats()
    return total_added


def load_all() -> Dict[str, Tournament]:
    if not DATA_FILE.exists():
        return {}

    raw = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    out = {}

    for tid, t in raw.items():
        players = {}
        for pid, p in t['players'].items():
            filtered = {k: v for k, v in p.items() if k in {"id", "name", "points", "matches_played"}}
            players[int(pid)] = Player(**filtered)

        rounds = []
        for r in t['rounds']:
            games = [Game(**g) for g in r['games']]
            rounds.append(Round(number=r['number'], games=games, active=r.get('active', True)))

        out[tid] = Tournament(
            id=t['id'],
            name=t['name'],
            host=t['host'],
            players=players,
            rounds=rounds,
            finished=t.get('finished', False),
            pod_size=t.get('pod_size', 4),
            max_rounds=t.get('max_rounds', 4),
            time_limit=t.get('time_limit', 90)
        )

    return out

def save_message_stats():
    with open(MESSAGE_STATS_FILE, "w", encoding="utf-8") as f:
        json.dump(MESSAGE_STATS, f, indent=2)


def save_all(data: Dict[str, Tournament]):
    """Atomically save all tournament data to disk."""
    raw = {}
    for tid, t in data.items():
        raw[tid] = {
            'id': t.id,
            'name': t.name,
            'host': t.host,
            'players': {str(pid): {
                'id': p.id,
                'name': p.name,
                'points': p.points,
                'matches_played': p.matches_played
            } for pid, p in t.players.items()},
            'rounds': [
                {
                    'number': r.number,
                    'games': [asdict(g) for g in r.games],
                    'active': r.active
                } for r in t.rounds
            ],
            'finished': t.finished,
            'pod_size': t.pod_size,
            'max_rounds': t.max_rounds,
            'time_limit': t.time_limit
        }

    # Atomic save to prevent corruption
    tmp_path = tempfile.NamedTemporaryFile(delete=False, dir=DATA_FILE.parent, mode='w', encoding='utf-8')
    with tmp_path as f:
        json.dump(raw, f, indent=2)
    shutil.move(tmp_path.name, DATA_FILE)


# -----------------------------
# Load tournaments on startup
# -----------------------------
TOURNAMENTS = load_all()
print(f"Loaded {len(TOURNAMENTS)} tournaments from {DATA_FILE}")

# -----------------------------
# Save on shutdown automatically
# -----------------------------
@atexit.register
def shutdown_save():
    print("Saving tournaments before shutdown...")
    save_all(TOURNAMENTS)
    print("Tournaments saved successfully.")


# -----------------------------
# Utilities
# -----------------------------
def generate_tournament_id(name: str) -> str:
    base = ''.join(ch for ch in name.lower() if ch.isalnum() or ch == '_')[:20]
    i = 1
    tid = f"{base}_{i}"
    while tid in TOURNAMENTS:
        i += 1
        tid = f"{base}_{i}"
    return tid

def standings_list(t: Tournament) -> List[Player]:
    return sorted(t.players.values(), key=lambda p: (-p.points, p.matches_played, p.name))

def make_pods(t: Tournament) -> List[Game]:
    """Divide registered players into pods for the round."""
    players = list(t.players.keys())
    random.shuffle(players)
    pods = []
    pod_number = 1
    pod_size = t.pod_size
    while players:
        pod_players = players[:pod_size]
        players = players[pod_size:]
        pods.append(Game(pod_number=pod_number, players=pod_players))
        pod_number += 1
    return pods

def get_point_allocation(pod_len: int) -> List[int]:
    """Return points based on new rework system: 1st=+2, 2nd=+1, 3rd=0, 4th=-1"""
    if pod_len == 4:
        return [4, 3, 2, 1]
    elif pod_len == 3:
        return [4, 3, 2]
    elif pod_len == 2:
        return [3, 2]
    else:
        return [2]  # auto-win if alone


# -----------------------------
# Bot events
# -----------------------------
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (id: {bot.user.id})")
    print("------")
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} commands")
    except Exception as e:
        print(f"Failed to sync commands: {e}")


async def check_round_timeouts():
    """Background task: check for rounds that exceed the time limit and ping players."""
    await bot.wait_until_ready()
    while not bot.is_closed():
        now = time.time()
        for tid, t in list(TOURNAMENTS.items()):
            for r in t.rounds:
                if r.active and r.start_time and not r.notified_timeout:
                    elapsed_minutes = (now - r.start_time) / 60
                    if elapsed_minutes > t.time_limit:
                        # Mark as notified to prevent repeated warnings
                        r.notified_timeout = True
                        save_all(TOURNAMENTS)

                        overdue_pods = [g for g in r.games if not g.results_reported]
                        for g in overdue_pods:
                            players_ping = " ".join(f"<@{pid}>" for pid in g.players)

                            # Try to notify host first
                            try:
                                host = await bot.fetch_user(t.host)
                                await host.send(
                                    f"⚠️ Round **{r.number}** in **{t.name}** has exceeded the {t.time_limit}-minute limit!\n"
                                    f"Pod {g.pod_number}: {players_ping}, please report your results!"
                                )
                            except Exception as e:
                                print(f"Failed to DM host for {t.name}: {e}")

                            # Try to send a message in a public channel (if possible)
                            try:
                                for guild in bot.guilds:
                                    if guild.get_member(t.host):
                                        channel = next(
                                            (ch for ch in guild.text_channels if ch.permissions_for(guild.me).send_messages),
                                            None
                                        )
                                        if channel:
                                            await channel.send(
                                                f"⚠️ Time limit exceeded for **{t.name}**, Round {r.number}.\n"
                                                f"Pod {g.pod_number}: {players_ping}, please report results!"
                                            )
                                            break
                            except Exception as e:
                                print(f"Failed to send timeout message in channel: {e}")

        await asyncio.sleep(300)  # check every 5 minutes

class HelpView(View):
    def __init__(self):
        super().__init__(timeout=None)  # persist indefinitely

        # Add buttons
        self.add_item(Button(label="General Info", style=discord.ButtonStyle.primary, custom_id="help_general"))
        self.add_item(Button(label="Commands", style=discord.ButtonStyle.secondary, custom_id="help_commands"))
        self.add_item(Button(label="Points", style=discord.ButtonStyle.success, custom_id="help_points"))
# -----------------------------
# Interaction handler for help buttons
# -----------------------------
@bot.event
async def on_interaction(interaction: discord.Interaction):
    if not interaction.type == discord.InteractionType.component:
        return

    # Check if the interaction is from our help buttons
    if interaction.data.get("custom_id", "").startswith("help_"):
        section = interaction.data["custom_id"].replace("help_", "")
        if section == "general":
            embed = Embed(title="EDH FFA Tournament Bot", description="This bot runs EDH free-for-all tournaments (2-4 player pods).", color=discord.Color.blue())
        elif section == "commands":
            embed = Embed(title="Commands", description=(
                "/create_tournament — Create a tournament (Organizer only)\n"
                "/register — Register for a tournament\n"
                "/start_round — Start a new round (Organizer only)\n"
                "/report_game — Report your pod results\n"
                "/standings — Show tournament standings (Organizer only)\n"
                "/my_standings — Show your own points\n"
                "/my_pods — See your pod\n"
                "/end_tournament — End tournament (Organizer only)\n"
                "/disqualify — Remove a player (Organizer only)"
            ), color=discord.Color.green())
        elif section == "points":
            embed = Embed(title="Points System", description=(
                "4-player pod: 1st=4, 2nd=3, 3rd=2, 4th=1\n"
                "3-player pod: 1st=4, 2nd=3, 3rd=2\n"
                "2-player pod: 1st=3, 2nd=2\n"
                "1-player pod(auto win): 1st=2"

            ), color=discord.Color.gold())
        else:
            return  # unknown button

        view = HelpView()  # recreate the view for persistent buttons
        await interaction.response.edit_message(embed=embed, view=view)


# -----------------------------
# Slash commands
# -----------------------------
@bot.tree.command(name="create_tournament", description="Create a new EDH FFA tournament")
@is_tournament_organizer()
@app_commands.describe(name="Tournament name", pod_size="Players per pod", max_rounds="Max rounds", time_limit="Minutes per round")
async def create_tournament(interaction: discord.Interaction, name: str, pod_size: int = 4, max_rounds: int = 4, time_limit: int = 90):
    tid = generate_tournament_id(name)
    t = Tournament(id=tid, name=name, host=interaction.user.id, pod_size=pod_size, max_rounds=max_rounds, time_limit=time_limit)
    TOURNAMENTS[tid] = t
    save_all(TOURNAMENTS)
    await interaction.response.send_message(f"Tournament **{name}** created with id `{tid}`. Players can register with `/register {tid}`.")

@bot.tree.command(name="register", description="Register for a tournament")
@app_commands.describe(tournament_id="Tournament ID")
async def register(interaction: discord.Interaction, tournament_id: str):
    t = TOURNAMENTS.get(tournament_id)
    if not t: return await interaction.response.send_message("Tournament not found.", ephemeral=True)
    if t.finished: return await interaction.response.send_message("Tournament already finished.", ephemeral=True)
    pid = interaction.user.id
    if pid in t.players: return await interaction.response.send_message("You are already registered.", ephemeral=True)
    t.players[pid] = Player(id=pid, name=str(interaction.user))
    save_all(TOURNAMENTS)
    await interaction.response.send_message(f"<@{pid}> registered for **{t.name}**.", ephemeral=True)

@bot.tree.command(name="start_round", description="Start a new round")
@is_tournament_organizer()
@app_commands.describe(tournament_id="Tournament ID")
async def start_round(interaction: discord.Interaction, tournament_id: str):
    t = TOURNAMENTS.get(tournament_id)
    if not t: return await interaction.response.send_message("Tournament not found.", ephemeral=True)
    if t.finished: return await interaction.response.send_message("Tournament already finished.", ephemeral=True)
    if len(t.players) < 2: return await interaction.response.send_message("Need at least 2 players.", ephemeral=True)
    for r in t.rounds:
        if r.active: return await interaction.response.send_message("A round is still active. Finish it first.", ephemeral=True)

    pods = make_pods(t)
    rnd = Round(number=len(t.rounds)+1, games=pods, start_time=time.time())
    t.rounds.append(rnd)
    save_all(TOURNAMENTS)

    lines = [f"**Round {rnd.number} pods for {t.name}:**"]
    for g in rnd.games:
        pod_line = ", ".join(f"<@{pid}>" for pid in g.players)
        lines.append(f"Pod {g.pod_number}: {pod_line}")
    await interaction.response.send_message("\n".join(lines))

@bot.tree.command(name="report_game", description="Report your pod's results")
@app_commands.describe(tournament_id="Tournament ID", pod_number="Pod number", first="First place", second="Second place", third="Third place", fourth="Fourth place")
async def report_game(interaction: discord.Interaction, tournament_id: str, pod_number: int, first: discord.Member, second: discord.Member, third: Optional[discord.Member] = None, fourth: Optional[discord.Member] = None):
    t = TOURNAMENTS.get(tournament_id)
    if not t: return await interaction.response.send_message("Tournament not found.", ephemeral=True)
    if not t.rounds: return await interaction.response.send_message("No rounds started.", ephemeral=True)
    r = t.rounds[-1]
    if not r.active: return await interaction.response.send_message("The current round has ended.", ephemeral=True)

    game = next((g for g in r.games if g.pod_number == pod_number), None)
    if not game: return await interaction.response.send_message("Pod not found.", ephemeral=True)
    if game.results_reported: return await interaction.response.send_message("This pod already reported.", ephemeral=True)

    pod_players = [first.id, second.id] + ([third.id] if third else []) + ([fourth.id] if fourth else [])
    points_list = get_point_allocation(len(pod_players))
    game.results = {pid: pts for pid, pts in zip(pod_players, points_list)}
    game.results_reported = True

    for pid, pts in game.results.items():
        player = t.players.get(pid)
        if player:
            player.points += pts
            player.matches_played += 1

    if all(g.results_reported for g in r.games):
        r.active = False
        await interaction.response.send_message(f"Pod results recorded. All pods reported! Round {r.number} is now complete.")
    else:
        await interaction.response.send_message(f"Pod results recorded for pod {pod_number}. Waiting for other pods to report.")

    save_all(TOURNAMENTS)

@bot.tree.command(name="register_past_messages_user", description="Register past messages of a specific user for the yapper leaderboard")
@is_tournament_organizer()
@app_commands.describe(user="User to scan", limit="Max messages per channel to scan (default 10000)")
async def register_past_messages_user(interaction: discord.Interaction, user: discord.Member, limit: int = 10000):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("Only admins can run this command.", ephemeral=True)

    await interaction.response.send_message(f"Scanning past messages of {user.display_name}... This may take a while!", ephemeral=True)
    count = await register_user_past_messages(interaction.guild, user, limit)
    await interaction.followup.send(f"Registered {count} past messages for {user.display_name}.", ephemeral=True)


@bot.tree.command(name="yapper_leaderboard", description="Show the message leaderboard for this server")
async def leaderboard(interaction: discord.Interaction):
    gid = str(interaction.guild_id)
    if gid not in MESSAGE_STATS or not MESSAGE_STATS[gid]:
        return await interaction.response.send_message("No messages recorded yet!", ephemeral=True)

    # Sort users by message count
    stats = MESSAGE_STATS[gid]
    sorted_stats = sorted(stats.items(), key=lambda x: x[1], reverse=True)

    # Build leaderboard text
    lines = ["**📊 Message Leaderboard:**"]
    for i, (uid, count) in enumerate(sorted_stats[:10], start=1):
        user = interaction.guild.get_member(int(uid))
        name = user.display_name if user else f"User {uid}"
        lines.append(f"{i}. **{name}** — {count} messages")

    await interaction.response.send_message("\n".join(lines))


@bot.tree.command(name="standings", description="Show tournament standings")
@is_tournament_organizer()
@app_commands.describe(tournament_id="Tournament ID")
async def standings(interaction: discord.Interaction, tournament_id: str):
    t = TOURNAMENTS.get(tournament_id)
    if not t: return await interaction.response.send_message("Tournament not found.", ephemeral=True)
    ordered = standings_list(t)
    lines = [f"**Standings for {t.name}:**"]
    for i, p in enumerate(ordered, start=1):
        lines.append(f"{i}. <@{p.id}> — {p.points} pts — {p.matches_played} matches")
    await interaction.response.send_message("\n".join(lines))

@bot.tree.command(name="my_standings", description="Show your current points in the tournament")
@app_commands.describe(tournament_id="Tournament ID")
async def my_standings(interaction: discord.Interaction, tournament_id: str):
    t = TOURNAMENTS.get(tournament_id)
    if not t: return await interaction.response.send_message("Tournament not found.", ephemeral=True)
    p = t.players.get(interaction.user.id)
    if not p: return await interaction.response.send_message("You are not registered in this tournament.", ephemeral=True)
    await interaction.response.send_message(f"You have {p.points} points and {p.matches_played} matches played.", ephemeral=True)

@bot.tree.command(name="disqualify", description="Disqualify a player and remove them from the tournament standings")
@is_tournament_organizer()
@app_commands.describe(tournament_id="Tournament ID", player="Player to disqualify")
async def disqualify(interaction: discord.Interaction, tournament_id: str, player: discord.Member):
    t = TOURNAMENTS.get(tournament_id)
    if not t:
        return await interaction.response.send_message("Tournament not found.", ephemeral=True)

    # Check if the user is authorized (host or admin)
    if interaction.user.id != t.host and not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("Only the host or an admin can disqualify a player.", ephemeral=True)

    # Check if player exists in tournament
    pid = player.id
    if pid not in t.players:
        return await interaction.response.send_message("That player is not registered in this tournament.", ephemeral=True)

    # Remove player from the tournament
    del t.players[pid]

    # Also remove the player from any active or future pods
    for rnd in t.rounds:
        for game in rnd.games:
            if pid in game.players:
                game.players.remove(pid)
                # If the game now has fewer than 2 players, mark it as auto-reported
                if len(game.players) < 2 and not game.results_reported:
                    game.results_reported = True

    save_all(TOURNAMENTS)
    await interaction.response.send_message(f"<@{pid}> has been **disqualified** from **{t.name}** and removed from the standings.")


@bot.tree.command(name="my_pods", description="Show your pod for the current round")
@app_commands.describe(tournament_id="Tournament ID")
async def my_pods(interaction: discord.Interaction, tournament_id: str):
    t = TOURNAMENTS.get(tournament_id)
    if not t: return await interaction.response.send_message("Tournament not found.", ephemeral=True)
    if not t.rounds: return await interaction.response.send_message("No rounds started.", ephemeral=True)
    r = t.rounds[-1]
    if not r.active: return await interaction.response.send_message("Current round has ended.", ephemeral=True)

    game = next((g for g in r.games if interaction.user.id in g.players), None)
    if not game: return await interaction.response.send_message("You are not in any pod this round.", ephemeral=True)
    opponents = [f"<@{pid}>" for pid in game.players if pid != interaction.user.id]
    await interaction.response.send_message(f"Pod {game.pod_number}: " + ", ".join(opponents), ephemeral=True)

@bot.tree.command(name="end_tournament", description="End a tournament and finalize results")
@is_tournament_organizer()
@app_commands.describe(tournament_id="Tournament ID")
async def end_tournament(interaction: discord.Interaction, tournament_id: str):
    t = TOURNAMENTS.get(tournament_id)
    if not t: return await interaction.response.send_message("Tournament not found.", ephemeral=True)
    if interaction.user.id != t.host and not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("Only host or admin can end the tournament.", ephemeral=True)
    t.finished = True
    save_all(TOURNAMENTS)
    await interaction.response.send_message(f"Tournament **{t.name}** is now finished.")

@bot.tree.command(name="help", description="Show help for the EDH FFA Tournament Bot")
async def help_command(interaction: discord.Interaction):
    embed = Embed(title="EDH FFA Tournament Bot", description="Click the buttons below to navigate help sections.", color=discord.Color.blue())
    view = HelpView()
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


# -----------------------------
# Message listener
# -----------------------------
@bot.event
async def on_message(message: discord.Message):
    if message.author == bot.user or not message.guild:
        return

    # --- Track message count per user per guild ---
    gid = str(message.guild.id)
    uid = str(message.author.id)

    if gid not in MESSAGE_STATS:
        MESSAGE_STATS[gid] = {}
    MESSAGE_STATS[gid][uid] = MESSAGE_STATS[gid].get(uid, 0) + 1
    save_message_stats()

    # --- Respond to specific words ---
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

    # Allow slash commands and prefixed commands to still work
    await bot.process_commands(message)


# -----------------------------
# Run the bot
# -----------------------------
if __name__ == "__main__":
    bot.run(TOKEN)
