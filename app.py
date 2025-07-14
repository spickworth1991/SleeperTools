from flask import Flask, render_template, request, session, jsonify, render_template_string
from flask_session import Session
import os
from models import db, SleeperPlayer, UserSearch, PlayerLeagueAssociation
import requests
import logging
from config import Config
from datetime import datetime

app = Flask(__name__)
app.config.from_object(Config)
app.config.update(SESSION_COOKIE_SAMESITE='None', SESSION_COOKIE_SECURE=True)
app.secret_key = 'your_secret_key'

# 🔐 Use server-side session storage
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_FILE_DIR'] = os.path.join(
    app.root_path, 'flask_session')  # Optional but good
app.config['SESSION_PERMANENT'] = False  # or True if you want long sessions
app.config['SESSION_COOKIE_NAME'] = 'session'
Session(app)

db.init_app(app)

with app.app_context():
    db.create_all()


@app.route('/')
def home():
    return render_template('home.html')


logging.basicConfig(level=logging.DEBUG)


@app.route('/search_username', methods=['POST'])
def search_username():
    username = request.form['username'].strip()
    if not username:
        return "⚠️ No username entered."

    user_api_url = f"https://api.sleeper.app/v1/user/{username}"
    user_api_response = requests.get(user_api_url)

    if user_api_response.status_code != 200:
        return f"⚠️ Error fetching user data (status: {user_api_response.status_code})"

    try:
        user_data = user_api_response.json()
    except Exception:
        return f"⚠️ Invalid response received from Sleeper for '{username}'."

    if not isinstance(user_data, dict) or 'user_id' not in user_data:
        return render_template(
            'error.html',
            message=
            f"⚠️ Could not find user '{username}'. Please check spelling.")

    user_id = user_data['user_id']
    session['username'] = username
    # Save or update user in UserSearch
    user_search = UserSearch.query.filter_by(username=username).first()
    if user_search:
        user_search.user_id = user_id
    else:
        user_search = UserSearch(username=username, user_id=user_id)
        db.session.add(user_search)
    db.session.commit()

    year = datetime.now().year

    leagues_api_url = f"https://api.sleeper.app/v1/user/{user_id}/leagues/nfl/{year}"
    leagues_api_response = requests.get(leagues_api_url)

    if leagues_api_response.status_code != 200:
        logging.error(
            f"Error fetching leagues data: {leagues_api_response.status_code}")
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

        leagues_data.append({
            'name': league['name'],
            'id': league['league_id']
        })
    session[f'{username}_league_ids'] = [
        league['id'] for league in leagues_data
    ]
    session[f'{username}_league_names'] = [
        league['name'] for league in leagues_data
    ]

    # Clear previous league associations for the user
    PlayerLeagueAssociation.query.filter_by(user_id=user_id).delete()
    db.session.commit()

    player_ids = []
    associations = []
    for league in leagues_data:
        league_api_url = f"https://api.sleeper.app/v1/league/{league['id']}/rosters"
        league_api_response = requests.get(league_api_url)

        if league_api_response.status_code != 200:
            logging.warning(
                f"Error fetching roster data for league {league['id']}: {league_api_response.status_code}"
            )
            continue

        roster_data = league_api_response.json()
        user_roster = next(
            (roster
             for roster in roster_data if roster['owner_id'] == user_id), None)

        if user_roster and user_roster.get('players'):
            for player_id in user_roster['players']:
                player_ids.append(player_id)
                associations.append(
                    PlayerLeagueAssociation(user_id=user_id,
                                            league_id=league['id'],
                                            player_id=player_id))
        else:
            logging.warning(
                f"No valid roster data found for user_id {user_id} in league {league['id']}"
            )

    db.session.bulk_save_objects(associations)
    db.session.commit()

    # DEBUG: check database player IDs
    #print("🧠 First 5 player IDs in DB:", [p.id for p in SleeperPlayer.query.limit(5)])

    player_map = {
        player.id: {
            'name': player.name,
            'position': player.position
        }
        for player in SleeperPlayer.query.all()
    }

    player_leagues_count = {
        player_id: player_ids.count(player_id)
        for player_id in set(player_ids)
    }
    # Map each player to the leagues they're in
    player_league_names = {}
    league_id_to_name = {
        league['id']: league['name']
        for league in leagues_data
    }

    for assoc in associations:
        name = league_id_to_name.get(assoc.league_id, 'Unknown League')
        player_league_names.setdefault(assoc.player_id, []).append(name)

    sorted_player_ids = sorted(player_leagues_count,
                               key=player_leagues_count.get,
                               reverse=True)

    players = []
    for player_id in sorted_player_ids:
        #print(f"🔎 Looking for player_id: {player_id}")
        player_info = player_map.get(str(player_id), {
            'name': 'Unknown Player',
            'position': 'Unknown Position'
        })
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
        filter_label=filter_label)


@app.route('/search_player', methods=['POST'])
def search_player():
    username = session.get('username', '').strip()
    player_name = request.form['player_name'].strip()
    user = UserSearch.query.filter_by(username=username).first()
    if not user:
        return "User not found", 404

    user_id = user.user_id
    filtered_ids = session.get(f'{username}_league_ids', [])
    filtered_names = session.get(f'{username}_league_names', [])
    league_map = {id: name for id, name in zip(filtered_ids, filtered_names)}

    searched_player_obj = SleeperPlayer.query.filter(
        SleeperPlayer.name.ilike(player_name)).first()
    if searched_player_obj:
        player_id = searched_player_obj.id
        associations = PlayerLeagueAssociation.query.filter_by(
            user_id=user_id, player_id=player_id).all()
        leagues = [
            league_map.get(assoc.league_id, 'Unknown League')
            for assoc in associations
        ]
        searched_player = {
            'name': searched_player_obj.name,
            'position': searched_player_obj.position
        }
    else:
        searched_player = None
        leagues = []

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return render_template_string("""
            {% if searched_player %}
                <h2>Search Results for {{ searched_player.name }}</h2>
                <ul>
                    {% for league in leagues %}
                        <li class="league-item"><span class="league-name">{{ league }}</span></li>
                    {% endfor %}
                </ul>
            {% else %}
                <h3>No results found for {{ player_name }}</h3>
            {% endif %}
        """,
                                      searched_player=searched_player,
                                      leagues=leagues,
                                      player_name=player_name)

    # Fallback for regular full page load
    players = session.get(f'{username}_cached_players', [])
    filter_label = session.get(f'{username}_filter_label', '')
    return render_template('result.html',
                           username=username,
                           players=players,
                           searched_player=searched_player,
                           leagues=leagues,
                           all_leagues=filtered_names,
                           filter_label=filter_label)


@app.route('/not_rostered_setup', methods=['POST'])
def not_rostered_setup():
    username = request.form['username'].strip()

    if not username:
        return "⚠️ No username entered."

    user_api_url = f"https://api.sleeper.app/v1/user/{username}"
    user_api_response = requests.get(user_api_url)

    if user_api_response.status_code != 200:
        return f"⚠️ Error fetching user data (status: {user_api_response.status_code})"

    try:
        user_data = user_api_response.json()
    except Exception:
        return f"⚠️ Invalid response received from Sleeper for '{username}'."

    if not isinstance(user_data, dict) or 'user_id' not in user_data:
        return render_template(
            'error.html',
            message=
            f"⚠️ Could not find user '{username}'. Please check spelling.")

    user_id = user_data['user_id']
    session['username'] = username
    year = datetime.now().year

    leagues_resp = requests.get(
        f'https://api.sleeper.app/v1/user/{user_id}/leagues/nfl/{year}')
    leagues = [{
        'id': l['league_id'],
        'name': l['name']
    } for l in leagues_resp.json() if l.get("status") not in ("none")]

    session[f'{username}_nr_league_ids'] = [l['id'] for l in leagues]
    session[f'{username}_nr_league_names'] = [l['name'] for l in leagues]

    # Cache full player list only once per session
    if not session.get('cached_all_players'):
        try:
            resp = requests.get("https://api.sleeper.app/v1/players/nfl")
            if resp.status_code == 200:
                session['cached_all_players'] = resp.json()
            else:
                session['cached_all_players'] = {}
        except Exception as e:
            print(f"Error fetching full player list: {e}")
            session['cached_all_players'] = {}

    return render_template('not_rostered.html', username=username)


@app.route('/search_not_rostered', methods=['POST'])
def search_not_rostered():
    username = session.get('username', '').strip()

    player_name = request.form['player_name'].strip()

    # Use session-stored league IDs and names
    league_ids = session.get(f'{username}_nr_league_ids', [])
    league_names = session.get(f'{username}_nr_league_names', [])
    leagues = [{
        'id': lid,
        'name': lname
    } for lid, lname in zip(league_ids, league_names)]

    not_rostered_results = []

    for league in leagues:
        league_id = league["id"]
        league_name = league["name"]

        rosters_resp = requests.get(
            f'https://api.sleeper.app/v1/league/{league_id}/rosters')
        rosters = rosters_resp.json()
        found = False

        for roster in rosters:
            player_ids = roster.get("players", [])
            if not player_ids:
                continue
            for pid in player_ids:
                player_data = get_player_info(pid)
                if player_data and player_data.get(
                        'full_name', '').lower() == player_name.lower():
                    found = True
                    break
            if found:
                break

        if not found:
            not_rostered_results.append(league_name)

    return render_template('not_rostered.html',
                           username=username,
                           player_name=player_name,
                           not_rostered_results=not_rostered_results,
                           total_league_count=len(leagues))


@app.route('/username_compare', methods=['POST'])
def username_compare():
    username1 = request.form['username1'].strip()
    username2 = request.form['username2'].strip()

    if not username1 or not username2:
        return render_template('error.html',
                               message="⚠️ Please enter both usernames.")

    if username1 == username2:
        return render_template(
            'error.html',
            message="⚠️ Please enter two different usernames to compare.")

    years = get_selected_years(request.form)
    if not years:
        years = [datetime.now().year]

    def fetch_league_names(username):
        try:
            resp = requests.get(f'https://api.sleeper.app/v1/user/{username}')
            if resp.status_code != 200:
                raise ValueError(f"⚠️ Could not find user '{username}'.")
            user_data = resp.json()
            user_id = user_data.get('user_id')
            if not user_id:
                raise ValueError(
                    f"⚠️ Invalid Sleeper response for '{username}'.")

            league_names = set()
            for year in years:
                league_resp = requests.get(
                    f'https://api.sleeper.app/v1/user/{user_id}/leagues/nfl/{year}'
                )
                if league_resp.status_code == 200:
                    year_leagues = league_resp.json()
                    league_names.update(league['name']
                                        for league in year_leagues)
            return list(league_names)
        except Exception:
            raise ValueError(
                f"⚠️ An error occurred while fetching leagues for '{username}'. Please check the username and try again."
            )

    try:
        leagues1 = fetch_league_names(username1)
        leagues2 = fetch_league_names(username2)
    except ValueError as e:
        return render_template('error.html', message=str(e))

    shared = sorted(set(leagues1) & set(leagues2))

    return render_template('username_compare.html',
                           username1=username1,
                           username2=username2,
                           total1=len(leagues1),
                           total2=len(leagues2),
                           shared_count=len(shared),
                           shared_leagues=shared)


@app.route('/league_compare', methods=['POST'])
def league_compare():
    league_id = request.form['league_id'].strip()

    if not league_id:
        return render_template('error.html',
                               message="⚠️ Please enter a valid league ID.")

    try:
        user_resp = requests.get(
            f'https://api.sleeper.app/v1/league/{league_id}/users')
        if user_resp.status_code != 200:
            raise ValueError("⚠️ Could not fetch users for that league ID.")

        users = user_resp.json()
        if not isinstance(users, list) or not users:
            raise ValueError("⚠️ No users found for that league ID.")

        user_map = {}
        league_to_users = {}
        years = get_selected_years(request.form)
        if not years:
            years = [datetime.now().year]

        for user in users:
            name = user.get('display_name', 'Unknown')
            user_id = user.get('user_id')
            if not user_id:
                continue
            league_names = set()
            for year in years:
                resp = requests.get(
                    f'https://api.sleeper.app/v1/user/{user_id}/leagues/nfl/{year}'
                )
                if resp.status_code != 200:
                    continue
                year_leagues = resp.json()
                for league in year_leagues:
                    label = f"{league['name']} ({year})"
                    league_names.add(label)
                    league_to_users.setdefault(label, set()).add(name)
            user_map[name] = league_names

        duplicates = {}
        user_league_counts = {name: set() for name in user_map}

        for league, shared_users in league_to_users.items():
            if len(shared_users) > 1:
                duplicates[league] = list(shared_users)
                for name in shared_users:
                    user_league_counts[name].add(league)

        summary = sorted([(name, len(leagues))
                          for name, leagues in user_league_counts.items()],
                         key=lambda x: x[1],
                         reverse=True)

        return render_template('league_compare.html',
                               duplicates=duplicates,
                               summary=summary)

    except ValueError as e:
        return render_template('error.html', message=str(e))


@app.route('/league_compare_page', methods=['GET'])
def league_compare_page():
    return render_template('league_compare_id.html',
                           current_year=datetime.now().year)


@app.route('/username_compare', methods=['GET'])
def username_compare_page():
    return render_template('username_compare_username.html',
                           current_year=datetime.now().year)


@app.route('/index', methods=['GET'])
def index_page():
    return render_template('index.html')


@app.route('/not_rostered', methods=['GET'])
def not_rostered():
    return render_template('not_rostered_username.html')


def get_selected_years(form):
    current_year = datetime.now().year
    selected_years = form.getlist('years')  # From the form checkboxes
    return [
        int(y) for y in selected_years
        if y.isdigit() and 2017 <= int(y) <= current_year
    ]


def get_player_info(player_id):
    username = session.get('username').strip()
    if not username:
        return None

    # Cached from user session
    cached_players = session.get(f'{username}_cached_players', [])
    for player in cached_players:
        if player.get('id') == player_id or player.get('name') == player_id:
            return {
                'full_name': player['name'],
                'position': player['position']
            }

    # Fallback only to cached_all_players (not API)
    all_players = session.get('cached_all_players', {})
    player_data = all_players.get(player_id)
    if player_data:
        return {
            'full_name':
            player_data.get('full_name')
            or player_data.get('name', 'Unknown Player'),
            'position':
            player_data.get('position', 'Unknown')
        }

    return None


# ======================== App Runner ========================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=True, host="0.0.0.0", port=port)

# This code is part of a Flask application that provides functionality for searching players in fantasy football leagues.
# It includes routes for searching by username, searching for specific players, and checking if players are not rostered in any leagues.
# The application uses the Sleeper API to fetch user and league data, and it stores user sessions using Flask-Session.
# The application also includes features for comparing leagues and usernames, and it provides a web interface for users to interact with the data.
# The code is structured to handle various scenarios, such as filtering leagues by best ball status and managing user sessions effectively.
