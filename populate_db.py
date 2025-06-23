import csv
import os
import logging
from app import app
from models import db, SleeperPlayer

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

def populate_database(csv_file):
    with app.app_context():
        if not os.path.exists(csv_file):
            logging.error(f"CSV file {csv_file} does not exist.")
            return

        logging.info(f"Reading CSV file: {csv_file}")
        with open(csv_file, newline='', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            seen_ids = set()
            new_players = []

            for row in reader:
                player_id = row.get('id')
                name = row.get('name')
                position = row.get('position')

                if not (player_id and name and position):
                    continue
                if player_id in seen_ids:
                    continue
                seen_ids.add(player_id)

                # Check for existing player
                existing = SleeperPlayer.query.get(player_id)
                if existing:
                    existing.name = name
                    existing.position = position
                    logging.debug(f"Updated player: {player_id}, {name}, {position}")
                else:
                    new_players.append(SleeperPlayer(id=player_id, name=name, position=position))
                    logging.debug(f"Inserted new player: {player_id}, {name}, {position}")

            if new_players:
                db.session.bulk_save_objects(new_players)
            db.session.commit()
            logging.info("Database population completed.")

if __name__ == '__main__':
    current_dir = os.path.dirname(os.path.abspath(__file__))
    csv_path = os.path.join(current_dir, 'sleeper_players.csv')
    populate_database(csv_path)
