import tkinter as tk
from tkinter import ttk
import json
from collections import namedtuple
from json import JSONEncoder
import operator
import math
from datetime import datetime
import os


class CreateToolTip(object):
    '''
    create a tooltip for a given widget
    '''

    def __init__(self, widget, text='widget info'):
        self.widget = widget
        self.text = text
        self.widget.bind("<Enter>", self.enter)
        self.widget.bind("<Leave>", self.close)

    def enter(self, event=None):
        x = y = 0
        x, y, cx, cy = self.widget.bbox("insert")
        x += self.widget.winfo_rootx() + 25
        y += self.widget.winfo_rooty() + 20
        # creates a toplevel window
        self.tw = tk.Toplevel(self.widget)
        # Leaves only the label and removes the app window
        self.tw.wm_overrideredirect(True)
        self.tw.wm_geometry("+%d+%d" % (x, y))
        label = tk.Label(self.tw, text=self.text, justify='left',
                         background='white', relief='solid', borderwidth=1
                         )
        label.pack(ipadx=1)

    def close(self, event=None):
        if self.tw:
            self.tw.destroy()


def GetProbability(rating1, rating2):
    x = 1 / (1 + 10 ** ((rating1 - rating2) / 400))
    print(x)
    return x


def getElo(ratingOfPlayer1, ratingOfPlayer2, K, result):
    if ratingOfPlayer1 >= ratingOfPlayer2:
        higherRating = ratingOfPlayer1
        lowerRating = ratingOfPlayer2
    else:
        higherRating = ratingOfPlayer2
        lowerRating = ratingOfPlayer1
    expectedScore = GetProbability(higherRating, lowerRating)
    eloChange = K * (1 - expectedScore)
    print(eloChange)
    if result == 1:
        newRatingOfPlayer1 = int(round(ratingOfPlayer1 + eloChange, 1))
        newRatingOfPlayer2 = int(round(ratingOfPlayer2 - eloChange, 1))
    else:
        newRatingOfPlayer1 = int(round(ratingOfPlayer1 - eloChange, 1))
        newRatingOfPlayer2 = int(round(ratingOfPlayer2 + eloChange, 1))
    return newRatingOfPlayer1, newRatingOfPlayer2


def getPlayer(name):
    for player in league.players:
        if player.name == name:
            return player


class Game:
    def __init__(self, white, black, result, date):
        self.white = white  # Jugador con blancas
        self.black = black  # Jugador con negras
        self.result = result  # 1 si ganan blancas, 0 si ganan negras, 0.5 tablas
        self.date = date


class League:
    def __init__(self, players, games=None):
        self.players = players
        self.games = games if games else []


class Player:
    def __init__(self, rating, name):
        self.rating = rating
        self.name = name


class MyEncoder(JSONEncoder):
    def default(self, o):
        return o.__dict__


def toJSON(self):
    return json.dumps(self, default=lambda o: o.__dict__,
                      sort_keys=True, indent=4)


def customDecoder(Dict):
    if 'name' in Dict:
        # Si no tiene rating, asignar 1000 como valor por defecto
        if 'rating' not in Dict:
            Dict['rating'] = 500
        return Player(**Dict)
    elif 'players' in Dict:
        return League(**Dict)
    elif 'white' in Dict and 'black' in Dict and 'result' in Dict:
        return Game(**Dict)
    else:
        return Dict


def jsonIntoObj(jsonFile):
    with open(jsonFile, "r", encoding='utf-8') as r:
        return json.loads(r.read(), object_hook=customDecoder)


def objIntoJson(jsonFile, LeagueToDump):
    return toJSON(LeagueToDump)


def sortObject(objectForUse):
    return sorted(objectForUse.players, key=lambda x: int(x.rating), reverse=True)

# Obtener el directorio del script actual
script_dir = os.path.dirname(os.path.abspath(__file__))

# Usar os.path.join para crear rutas relativas al script
league = jsonIntoObj(os.path.join(script_dir, "league.json"))

def calculate_current_ratings():
    # Comenzar con ratings iniciales
    start_league = jsonIntoObj(os.path.join(script_dir, "start.json"))
    current_ratings = {player.name: player.rating for player in start_league.players}
    
    # Aplicar todos los juegos en orden cronológico
    for game in league.games:
        white_rating = current_ratings[game.white]
        black_rating = current_ratings[game.black]
        
        new_white, new_black = getElo(white_rating, black_rating, 50, game.result)
        current_ratings[game.white] = new_white
        current_ratings[game.black] = new_black
    
    return current_ratings

def getLeagueTable(inputLeague):
    current_ratings = calculate_current_ratings()
    
    # Crear lista de jugadores con ratings actuales
    players_with_ratings = [
        Player(current_ratings[p.name], p.name) 
        for p in inputLeague.players
    ]
    
    # Ordenar por rating
    sortedList = sorted(players_with_ratings, 
                       key=lambda x: int(x.rating), 
                       reverse=True)
    
    lf = ttk.LabelFrame(root, text='Chess League')
    lf.grid(column=0, row=0, padx=20, pady=20)
    
    for i, player in enumerate(sortedList):
        tk.Label(lf, text=f"{i + 1}. {player.name}: {player.rating}").pack()

def writeStandings(param, leagueForDump):
    with open(param, "w", encoding='utf-8') as w:
        w.write(objIntoJson(param, leagueForDump))
        w.close()


def get_player_names():
    # Obtener lista de nombres de jugadores
    return [player.name for player in league.players]

def recordResults():
    white = getPlayer(player1_combo.get())  # Usar combobox en lugar de Entry
    black = getPlayer(player2_combo.get())  # Usar combobox en lugar de Entry
    result = result_var.get()
    
    game = Game(white.name, black.name, result, 
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    league.games.append(game)
    
    getLeagueTable(league)
    writeStandings("league.json", league)

def update_player_lists():
    # Actualizar las listas de jugadores en los comboboxes
    players = get_player_names()
    player1_combo['values'] = players
    player2_combo['values'] = players

def addingPlayer():
    name = playerEntry.get()
    league.players.append(Player(1000, name))
    writeStandings("league.json", league)
    getLeagueTable(league)
    update_player_lists()  # Actualizar comboboxes cuando se agrega un jugador

def get_last_colors():
    # Obtener el último juego entre dos jugadores seleccionados
    player1 = player1_combo.get()
    player2 = player2_combo.get()
    
    if not player1 or not player2:
        return None, None
        
    for game in reversed(league.games):
        if (game.white == player1 and game.black == player2) or \
           (game.white == player2 and game.black == player1):
            return (game.white, game.black)
    return None, None

def get_player_game_counts():
    # Diccionario para contar juegos por jugador
    player_counts = {p.name: 0 for p in league.players}
    # Diccionario para contar juegos entre pares de jugadores
    pair_counts = {}
    
    for game in league.games:
        player_counts[game.white] += 1
        player_counts[game.black] += 1
        
        # Ordenar el par para consistencia
        pair = tuple(sorted([game.white, game.black]))
        pair_counts[pair] = pair_counts.get(pair, 0) + 1
    
    return player_counts, pair_counts

def get_last_game_color(player):
    # Obtener el último color que usó un jugador
    for game in reversed(league.games):
        if game.white == player:
            return 'white'
        if game.black == player:
            return 'black'
    return None

def create_match():
    player_counts, pair_counts = get_player_game_counts()
    players = [p.name for p in league.players]
    
    # Encontrar todas las posibles parejas y sus puntuaciones
    pairs = []
    for i, p1 in enumerate(players):
        for p2 in players[i+1:]:
            pair = tuple(sorted([p1, p2]))
            games_between = pair_counts.get(pair, 0)
            
            # Calcular puntuación (menor es mejor)
            score = games_between * 10  # Prioridad alta a parejas con pocos juegos
            
            # Penalizar si algún jugador tiene muchos más juegos que el promedio
            avg_games = sum(player_counts.values()) / len(player_counts)
            score += abs(player_counts[p1] - avg_games)
            score += abs(player_counts[p2] - avg_games)
            
            # Agregar algo de aleatoriedad a la puntuación
            from random import uniform
            score += uniform(0, 5)  # Agregar entre 0 y 5 puntos aleatorios
            
            pairs.append((score, p1, p2))
    
    # Ordenar por puntuación y tomar uno de los mejores pares
    pairs.sort()
    from random import randint
    # Tomar un par aleatorio entre los 3 mejores
    selected_index = randint(0, min(2, len(pairs)-1))
    if not pairs:
        return
    
    _, p1, p2 = pairs[selected_index]
    
    # Decidir colores basado en historial
    p1_last_color = get_last_game_color(p1)
    p2_last_color = get_last_game_color(p2)
    
    # Asignar colores priorizando alternancia
    if p1_last_color == 'white' and p2_last_color != 'black':
        white, black = p2, p1
    elif p2_last_color == 'white' and p1_last_color != 'black':
        white, black = p1, p2
    elif p1_last_color == 'black':
        white, black = p1, p2
    elif p2_last_color == 'black':
        white, black = p2, p1
    else:
        # Si no hay historial o es ambiguo, asignar aleatoriamente
        from random import choice
        if choice([True, False]):
            white, black = p1, p2
        else:
            white, black = p2, p1
    
    # Actualizar los comboboxes
    player1_combo.set(white)
    player2_combo.set(black)

root = tk.Tk()
root.title('Chess League')

window_width = 500
window_height = 800

screen_width = root.winfo_screenwidth()
screen_height = root.winfo_screenheight()

center_x = int(screen_width / 2 - window_width / 2)
center_y = int(screen_height / 2 - window_height / 2)

# tk.Label(root, text="Chess League").pack()


getLeagueTable(league)

addPlayersPanel = ttk.LabelFrame(root, text='Add Players')
addPlayersPanel.grid(column=1, row=0, padx=20, pady=20)
addPlayersPanel.place(x=245, y=5)

recordGamePanel = ttk.LabelFrame(root, text="Record Game")
recordGamePanel.grid(column=1, row=3, padx=10, pady=20)
recordGamePanel.place(x=245, y=100)

ttk.Label(recordGamePanel, text="White: ").pack()
player1_combo = ttk.Combobox(recordGamePanel, values=get_player_names(), state='readonly')
player1_combo.pack()

ttk.Label(recordGamePanel, text="Black: ").pack()
player2_combo = ttk.Combobox(recordGamePanel, values=get_player_names(), state='readonly')
player2_combo.pack()
resultLabel = ttk.Label(recordGamePanel, text="Result:")
resultLabel.pack()
tooltip = CreateToolTip(resultLabel, "Type 1 if white won the game, 0.5 if it was a draw and 0 if black won the "
                                     "game")

# Variable para los radio buttons
result_var = tk.DoubleVar(value=1)  # Default to white wins

# Frame para los radio buttons
result_frame = ttk.Frame(recordGamePanel)
result_frame.pack(pady=5)

ttk.Radiobutton(result_frame, text="White wins", variable=result_var, value=1.0).pack(side=tk.LEFT, padx=5)
ttk.Radiobutton(result_frame, text="Draw", variable=result_var, value=0.5).pack(side=tk.LEFT, padx=5)
ttk.Radiobutton(result_frame, text="Black wins", variable=result_var, value=0.0).pack(side=tk.LEFT, padx=5)

playerEntry = tk.Entry(addPlayersPanel)
playerEntry.pack()
ttk.Button(addPlayersPanel, text="Add", command=addingPlayer).pack()
ttk.Button(recordGamePanel, text="Create Match", command=create_match).pack(pady=5)
ttk.Button(recordGamePanel, text="Record Results", command=recordResults).pack()


# Comentamos el panel y botón de reset
"""
panelReset = ttk.LabelFrame(root, text="Reset League standings")
panelReset.grid(column=1, row=3, padx=10, pady=20)
panelReset.place(x=245, y=275)
ttk.Button(panelReset, text="Reset", command=resetLeague).pack()
"""

root.geometry(f'{window_width}x{window_height}+{center_x}+{center_y}')
root.resizable(False, False)
root.mainloop()
