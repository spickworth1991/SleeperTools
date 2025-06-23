import os

basedir = os.path.abspath(os.path.dirname(__file__))

class Config:
    # This will ensure that the database file is created in the PlayerStock directory
    SQLALCHEMY_DATABASE_URI = 'sqlite:///' + os.path.join(basedir, 'app.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
