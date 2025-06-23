import requests
import csv
import os
import shutil

# File setup
filename = "sleeper_players.csv"
backup_filename = "sleeper_players_backup.csv"

if os.path.exists(filename):
    shutil.copy(filename, backup_filename)
    print(f"Backed up existing file to {backup_filename}")

# Fetch Sleeper data
url = "https://api.sleeper.app/v1/players/nfl"
response = requests.get(url)
players = response.json()

# Full CSV headers
headers = [
    "id", "name", "weight", "status", "sport", "fantasy_positions", "college", "player_id",
    "practice_description", "rotowire_id", "active", "position", "number", "last_name",
    "height", "injury_status", "injury_body_part", "injury_notes", "practice_participation",
    "high_school", "team", "sportradar_id", "yahoo_id", "years_exp", "fantasy_data_id",
    "hashtag", "search_last_name", "first_name", "birth_city", "espn_id", "birth_date",
    "search_first_name", "news_updated", "gsis_id", "birth_country", "birth_state",
    "search_full_name", "depth_chart_position", "rotoworld_id", "depth_chart_order",
    "injury_start_date", "stats_id"
]

# Separate players vs teams
player_entries = {k: v for k, v in players.items() if k.isdigit()}
team_entries = {k: v for k, v in players.items() if not k.isdigit()}

# Write CSV
with open(filename, "w", newline='', encoding="utf-8") as csvfile:
    writer = csv.writer(csvfile)
    writer.writerow(headers)

    for player_id in sorted(player_entries.keys(), key=lambda x: int(x)):
        player = player_entries[player_id]
        full_name = f"{player.get('first_name', '').strip()} {player.get('last_name', '').strip()}".strip()
        row = [player.get("player_id", player_id), full_name]

        for key in headers[2:]:  # skip id and name since already added
            row.append(player.get(key, ""))
        writer.writerow(row)

    writer.writerow([])  # spacer
    writer.writerow(["--- TEAM/META ENTRIES ---"] + [""] * (len(headers) - 1))

    for team_key in sorted(team_entries.keys()):
        team = team_entries[team_key]
        full_name = f"{team.get('first_name', '').strip()} {team.get('last_name', '').strip()}".strip()
        row = [team_key, full_name]

        for key in headers[2:]:
            row.append(team.get(key, ""))
        writer.writerow(row)

print(f"Saved {len(player_entries)} players and {len(team_entries)} teams to {filename}")
