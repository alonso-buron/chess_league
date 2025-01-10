from flask import Blueprint
from . import auth, game, player, main

# Registrar todos los blueprints aquí para importarlos fácilmente en app/__init__.py
blueprints = [
    auth.bp,
    game.bp,
    player.bp,
    main.bp
] 