from flask_login import UserMixin

class User(UserMixin):
    def __init__(self, id, username, is_admin, player_name=None):
        self.id = id
        self.username = username
        self.is_admin = is_admin
        self.player_name = player_name 