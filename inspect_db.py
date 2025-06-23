from app import app
from models import db, SleeperPlayer, UserSearch, PlayerLeagueAssociation

def inspect_database():
    with app.app_context():
        print("🔍 Inspecting app.db...\n")

        print("🧍 SleeperPlayer Table:")
        players = SleeperPlayer.query.all()
        for p in players:
            print(f" - ID: {p.id}, Name: {p.name}, Position: {p.position}")
        print(f"Total players: {len(players)}\n")

        print("🔎 UserSearch Table:")
        users = UserSearch.query.all()
        for u in users:
            print(f" - Username: {u.username}, User ID: {u.user_id}")
        print(f"Total users: {len(users)}\n")

        print("📦 PlayerLeagueAssociation Table:")
        associations = PlayerLeagueAssociation.query.all()
        for a in associations:
            print(f" - User ID: {a.user_id}, League ID: {a.league_id}, Player ID: {a.player_id}")
        print(f"Total associations: {len(associations)}")
        for u in users:
            print(f" - Username: {u.username}, User ID: {u.user_id}")
        print(f"Total users: {len(users)}\n")
        print(f"Total players: {len(players)}\n")

if __name__ == "__main__":
    inspect_database()
