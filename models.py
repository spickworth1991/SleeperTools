from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class SleeperPlayer(db.Model):
    id = db.Column(db.String, primary_key=True)
    name = db.Column(db.String(100))
    position = db.Column(db.String(50))

    def __repr__(self):
        return f'<SleeperPlayer {self.name}>'

class UserSearch(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String)
    user_id = db.Column(db.String)

class PlayerLeagueAssociation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String)
    league_id = db.Column(db.String)
    player_id = db.Column(db.String, db.ForeignKey('sleeper_player.id'))

    player = db.relationship('SleeperPlayer', backref=db.backref('leagues', lazy=True))
