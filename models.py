from run import db

class Ping(db.Model):
    id = db.Column(db.Integer, primary_key=True)
