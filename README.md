
# EDH FFA Tournament Discord Bot / GuacBot

A Discord bot to manage **EDH Free-For-All tournaments** with 1–4 player pods per round. Designed for casual and competitive play with automated point tracking and round management.

---

## Features

* **3–4 Player Pods**: Supports 1–4 player free-for-all pods per round.
* **Automatic Round Ending**: Rounds automatically end when all pods report results.
* **Flexible Point System**:

  * 4-player pod: 1st=4, 2nd=3, 3rd=2, 4th=1
  * 3-player pod: 1st=4, 2nd=3, 3rd=2
  * 2-player pod: 1st=3, 2nd=2
  * 1-player pod (auto-win): 2 points
* **Slash Commands**: Easy-to-use slash commands for organizers and participants.
* **Persistent Storage**: Tournament and message stats are saved in JSON files.
* **Leaderboard Support**: Tracks message activity for a "Yapper" leaderboard.
* **Help Menu**: Interactive buttons with guidance on commands, points, and general info.

---

## Requirements

* Python 3.11+
* [discord.py 2.x](https://discordpy.readthedocs.io/en/stable/)
* `python-dotenv` for storing your bot token

```bash
pip install -r requirements.txt
```

---

## Setup

1. **Clone the repository**:

```bash
git clone <repo_url>
cd edh-ffa-discord-bot
```

2. **Create a `.env` file** with your bot token:

```env
BOT_TOKEN=your_discord_bot_token_here
```

3. **Run the bot**:

```bash
python bot.py
```

---

## Slash Commands

| Command                        | Description                                   | Access             |
| ------------------------------ | --------------------------------------------- | ------------------ |
| `/create_tournament`           | Create a new tournament                       | Organizer only     |
| `/register`                    | Register for a tournament                     | All users          |
| `/start_round`                 | Start a new round                             | Organizer only     |
| `/report_game`                 | Report pod results                            | Pod participants   |
| `/standings`                   | Show current tournament standings             | Organizer only     |
| `/my_standings`                | Show your own points                          | Registered players |
| `/my_pods`                     | Show your current pod                         | Registered players |
| `/end_tournament`              | Finish a tournament                           | Organizer only     |
| `/disqualify`                  | Remove a player from tournament               | Organizer only     |
| `/help`                        | Show help with interactive buttons            | All users          |
| `/register_past_messages_user` | Register past messages for Yapper leaderboard | Admins only        |
| `/yapper_leaderboard`          | Show top message senders                      | All users          |

---

## Data Storage

* `tournaments.json`: Stores tournament state, rounds, pods, and player points.
* `message_stats.json`: Tracks user messages for leaderboards.

All data is saved atomically to prevent corruption.

---

## Permissions

* Users need the **Tournament Organizer** role or admin permissions to create, start, or end tournaments.
* Players can register and report results for their own pods.

---

## Customization

* **Pod Size**: Default 4 players per pod; configurable during tournament creation.
* **Round Time Limit**: Default 90 minutes; configurable per tournament.
* **Max Rounds**: Default 4; configurable per tournament.

---

## Message Reactions

The bot automatically responds to certain keywords:

| Keyword   | Response                                             |
| --------- | ---------------------------------------------------- |
| `beep`    | `boop`                                               |
| `clanker` | `shutup fleshbag`                                    |
| `nya`     | `ew.`                                                |
| `bonk`    | [Bonk GIF](https://tenor.com/view/bonk-gif-19410756) |
| `simp`    | `sniper monke`                                       |

---

## License

MIT License – free to use and modify for your own Discord servers.

