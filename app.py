from flask import Flask, render_template, request
from models import db, SleeperPlayer, UserSearch, PlayerLeagueAssociation
import requests
import logging
from config import Config

app = Flask(__name__)
app.config.from_object(Config)


db.init_app(app)

with app.app_context():
    db.create_all()

@app.route('/')
def index():
    return render_template('index.html')

logging.basicConfig(level=logging.DEBUG)

@app.route('/search_username', methods=['POST'])
def search_username():
    username = request.form['username']
    user_api_url = f"https://api.sleeper.app/v1/user/{username}"
    user_api_response = requests.get(user_api_url)

    if user_api_response.status_code != 200:
        logging.error(f"Error fetching user data: {user_api_response.status_code}")
        return f"Error fetching user data: {user_api_response.status_code}"

    user_data = user_api_response.json()
    user_id = user_data.get('user_id')

    if not user_id:
        return "User not found or invalid username."

    # Save or update user in UserSearch
    user_search = UserSearch.query.filter_by(username=username).first()
    if user_search:
        user_search.user_id = user_id
    else:
        user_search = UserSearch(username=username, user_id=user_id)
        db.session.add(user_search)
    db.session.commit()

    year = 2025
    leagues_api_url = f"https://api.sleeper.app/v1/user/{user_id}/leagues/nfl/{year}"
    leagues_api_response = requests.get(leagues_api_url)

    if leagues_api_response.status_code != 200:
        logging.error(f"Error fetching leagues data: {leagues_api_response.status_code}")
        return f"Error fetching leagues data: {leagues_api_response.status_code}"

    year_leagues = leagues_api_response.json()
    leagues_data = [{'name': league['name'], 'id': league['league_id']} for league in year_leagues if league.get('status') == 'in_season']

    # Clear previous league associations for the user
    PlayerLeagueAssociation.query.filter_by(user_id=user_id).delete()
    db.session.commit()

    player_ids = []
    associations = []
    for league in leagues_data:
        league_api_url = f"https://api.sleeper.app/v1/league/{league['id']}/rosters"
        league_api_response = requests.get(league_api_url)

        if league_api_response.status_code != 200:
            logging.warning(f"Error fetching roster data for league {league['id']}: {league_api_response.status_code}")
            continue

        roster_data = league_api_response.json()
        user_roster = next((roster for roster in roster_data if roster['owner_id'] == user_id), None)

        if user_roster and user_roster.get('players'):
            for player_id in user_roster['players']:
                player_ids.append(player_id)
                associations.append(PlayerLeagueAssociation(user_id=user_id, league_id=league['id'], player_id=player_id))
        else:
            logging.warning(f"No valid roster data found for user_id {user_id} in league {league['id']}")

    db.session.bulk_save_objects(associations)
    db.session.commit()

    # DEBUG: check database player IDs
    print("🧠 First 5 player IDs in DB:", [p.id for p in SleeperPlayer.query.limit(5)])

    player_map = {
        player.id: {'name': player.name, 'position': player.position}
        for player in SleeperPlayer.query.all()
    }

    player_leagues_count = {player_id: player_ids.count(player_id) for player_id in set(player_ids)}
    sorted_player_ids = sorted(player_leagues_count, key=player_leagues_count.get, reverse=True)

    players = []
    for player_id in sorted_player_ids:
        print(f"🔎 Looking for player_id: {player_id}")
        player_info = player_map.get(str(player_id), {'name': 'Unknown Player', 'position': 'Unknown Position'})
        league_count = player_leagues_count[player_id]
        percentage = (league_count / len(leagues_data)) * 100
        players.append({'name': player_info['name'], 'position': player_info['position'], 'percentage': f"{percentage:.2f}%"})

    return render_template('result.html', username=username, players=players, leagues=[])




@app.route('/search_player', methods=['POST'])
def search_player():
    username = request.form['username']
    player_name = request.form['player_name']

    user_search = UserSearch.query.filter_by(username=username).first()
    if not user_search:
        return "User not found in the database."

    user_id = user_search.user_id
    year = 2025
    leagues_api_url = f"https://api.sleeper.app/v1/user/{user_id}/leagues/nfl/{year}"
    leagues_api_response = requests.get(leagues_api_url)
    year_leagues = leagues_api_response.json()

    leagues_data = [{'name': league['name'], 'id': league['league_id']} for league in year_leagues]

    player_ids = []
    associations = PlayerLeagueAssociation.query.filter_by(user_id=user_id).all()
    for association in associations:
        player_ids.append(association.player_id)

    player_map = {player.id: {'name': player.name, 'position': player.position} for player in SleeperPlayer.query.all()}
    league_map = {league['id']: league['name'] for league in leagues_data}

    player_leagues_count = {player_id: player_ids.count(player_id) for player_id in set(player_ids)}
    sorted_player_ids = sorted(player_leagues_count, key=player_leagues_count.get, reverse=True)

    players = []
    for player_id in sorted_player_ids:
        player_info = player_map.get(player_id, {'name': 'Unknown Player', 'position': 'Unknown Position'})
        league_count = player_leagues_count[player_id]
        percentage = (league_count / len(leagues_data)) * 100
        players.append({'name': player_info['name'], 'position': player_info['position'], 'percentage': f"{percentage:.2f}%"})

    searched_player = next((player for player in players if player['name'].lower() == player_name.lower()), None)
    leagues = []
    if searched_player:
        searched_player_id = next((key for key, value in player_map.items() if value['name'].lower() == player_name.lower()), None)
        if searched_player_id:
            leagues = [league_map.get(association.league_id, 'Unknown League') for association in PlayerLeagueAssociation.query.filter_by(player_id=searched_player_id, user_id=user_id).all()]

    return render_template('result.html', username=username, players=players, searched_player=searched_player, leagues=leagues)

