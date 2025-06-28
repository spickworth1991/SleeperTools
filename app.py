from flask import Flask, render_template, request, session
from flask_session import Session
import os
from models import db, SleeperPlayer, UserSearch, PlayerLeagueAssociation
import requests
import logging
from config import Config

app = Flask(__name__)
app.config.from_object(Config)
app.secret_key = 'your_secret_key'

# 🔐 Use server-side session storage
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_FILE_DIR'] = os.path.join(app.root_path, 'flask_session')  # Optional but good
app.config['SESSION_PERMANENT'] = False  # or True if you want long sessions
app.config['SESSION_COOKIE_NAME'] = 'session'
Session(app)


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
    only_bestball = request.form.get('only_bestball') == "1"
    exclude_bestball = request.form.get('exclude_bestball') == "1"

    if only_bestball and exclude_bestball:
        return "⚠️ Please select only one best ball filter option."

    leagues_data = []
    for league in year_leagues:
        if league.get('status') != 'in_season':
            continue

        is_best_ball = league.get('settings', {}).get('best_ball', False)
        #print(f"✅ {league['name']} | best_ball: {is_best_ball}")

        if only_bestball and not is_best_ball:
            continue
        if exclude_bestball and is_best_ball:
            continue

        leagues_data.append({'name': league['name'], 'id': league['league_id']})
    session[f'{username}_league_ids'] = [league['id'] for league in leagues_data]
    session[f'{username}_league_names'] = [league['name'] for league in leagues_data]

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
    # Map each player to the leagues they're in
    player_league_names = {}
    league_id_to_name = {league['id']: league['name'] for league in leagues_data}

    for assoc in associations:
        name = league_id_to_name.get(assoc.league_id, 'Unknown League')
        player_league_names.setdefault(assoc.player_id, []).append(name)

    sorted_player_ids = sorted(player_leagues_count, key=player_leagues_count.get, reverse=True)

    players = []
    for player_id in sorted_player_ids:
        #print(f"🔎 Looking for player_id: {player_id}")
        player_info = player_map.get(str(player_id), {'name': 'Unknown Player', 'position': 'Unknown Position'})
        league_count = player_leagues_count[player_id]
        percentage = (league_count / len(leagues_data)) * 100
        players.append({
        'name': player_info['name'],
        'position': player_info['position'],
        'percentage': f"{percentage:.2f}%",
        'leagues': player_league_names.get(player_id, [])
    })

    filter_label = "All Leagues"
    if only_bestball:
        filter_label = "Only Best Ball Leagues"
    elif exclude_bestball:
        filter_label = "Excluding Best Ball Leagues"

    # Store players and filter label in session for later use
    session[f'{username}_cached_players'] = players
    session[f'{username}_filter_label'] = filter_label

    return render_template(
    'result.html',
    username=username,
    players=players,
    all_leagues=[league['name'] for league in leagues_data],
    searched_player=None,
    filter_label=filter_label
)


@app.route('/search_player', methods=['POST'])
def search_player():
    username = request.form['username']
    player_name = request.form['player_name']
    user = UserSearch.query.filter_by(username=username).first()
    if not user:
        return "User not found"

    user_id = user.user_id

    # Use leagues stored from initial username search
    filtered_ids = session.get(f'{username}_league_ids', [])
    filtered_names = session.get(f'{username}_league_names', [])

    # Only calculate the searched player
    searched_player = None
    league_map = {id: name for id, name in zip(filtered_ids, filtered_names)}

    searched_player_obj = SleeperPlayer.query.filter(SleeperPlayer.name.ilike(player_name)).first()
    if searched_player_obj:
        player_id = searched_player_obj.id
        associations = PlayerLeagueAssociation.query.filter_by(user_id=user_id, player_id=player_id).all()
        leagues = [league_map.get(assoc.league_id, 'Unknown League') for assoc in associations]
        searched_player = {
            'name': searched_player_obj.name,
            'position': searched_player_obj.position
        }
    else:
        leagues = []

    # Use existing player data from last search
    players = session.get(f'{username}_cached_players', [])
    filter_label = session.get(f'{username}_filter_label', '')

    return render_template(
        'result.html',
        username=username,
        players=players,  # don't recalculate
        searched_player=searched_player,
        leagues=leagues,
        all_leagues=[name for name in filtered_names],
        filter_label=filter_label
    )



if __name__ == "__main__":
    app.run(debug=True)
