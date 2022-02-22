import tkinter as tk
from tkinter import ttk
import json
from collections import namedtuple
from json import JSONEncoder
import operator
import math


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
    eloChange = 0
    higherRating = 0
    lowerRating = 0
    if ratingOfPlayer1 >= ratingOfPlayer2:
        higherRating = ratingOfPlayer1
        lowerRating = ratingOfPlayer2
    else:
        higherRating = ratingOfPlayer2
        lowerRating = ratingOfPlayer1
    expectedScore = GetProbability(higherRating, lowerRating)
    newRatingOfPlayer1 = 0
    newRatingOfPlayer2 = 0
    eloChange = K * (1 - expectedScore)
    print(eloChange)
    if result == 1:

        newRatingOfPlayer1 = int(round(ratingOfPlayer1 + eloChange, 1))
        newRatingOfPlayer2 = int(round(ratingOfPlayer2 - eloChange, 1))
    elif result == 0:

        newRatingOfPlayer1 = int(round(ratingOfPlayer1 - eloChange, 1))
        newRatingOfPlayer2 = int(round(ratingOfPlayer2 + eloChange, 1))
    else:
        pass

    return newRatingOfPlayer1, newRatingOfPlayer2


def getPlayer(name):
    for player in league.players:
        if player.name == name:
            return player


class League:

    def __init__(self, players):
        self.players = players


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
    if 'name' in Dict and 'rating' in Dict:
        return Player(**Dict)
    elif 'players' in Dict:
        return League(**Dict)
    else:
        return Dict


def jsonIntoObj(jsonFile):
    with open(jsonFile, "r") as r:
        return json.loads(r.read(), object_hook=customDecoder)


def objIntoJson(jsonFile, LeagueToDump):
    return toJSON(LeagueToDump)


def change_attribute(attribute, value):
    attribute = value


def sortObject(objectForUse):
    return sorted(objectForUse.players, key=lambda x: int(x.rating), reverse=True)


league = jsonIntoObj("league.json")


# league = League([Player("jack", 1500), Player("dad", 1000)])
# league = League(playersList)


def getLeagueTable(inputLeague):
    sortedList = sortObject(inputLeague)
    lf = ttk.LabelFrame(root, text='Chess League')
    lf.grid(column=0, row=0, padx=20, pady=20)

    alignment_var = tk.StringVar()
    alignments = ('Left', 'Center', 'Right')

    for i in range(len(inputLeague.players)):
        tk.Label(lf, text=str(i + 1) + ". " + sortedList[i].name + ": " + str(sortedList[i].rating)).pack()


def writeStandings(param, leagueForDump):
    with open(param, "w") as w:
        w.write(objIntoJson(param, leagueForDump))
        w.close()


def addingPlayer():
    name = playerEntry.get()
    league.players.append(Player(1000, name))
    writeStandings("league.json", league)
    getLeagueTable(league)


def recordResults():
    player1 = getPlayer(player1Entry.get())
    player2 = getPlayer(player2Entry.get())
    resultOfGame = int(resultEntry.get())
    league.players[league.players.index(player1)].rating, league.players[
        league.players.index(player2)].rating = getElo(player1.rating, player2.rating, 50, resultOfGame)
    getLeagueTable(league)
    writeStandings("league.json", league)


def resetLeague():
    for ply in league.players:
        ply.rating = 1000


root = tk.Tk()
root.title('Chess League')

window_width = 300
window_height = 800

screen_width = root.winfo_screenwidth()
screen_height = root.winfo_screenheight()

center_x = int(screen_width / 2 - window_width / 2)
center_y = int(screen_height / 2 - window_height / 2)

# tk.Label(root, text="Chess League").pack()


getLeagueTable(league)

addPlayersPanel = ttk.LabelFrame(root, text='Add Players')
addPlayersPanel.grid(column=1, row=0, padx=20, pady=20)
addPlayersPanel.place(x=145, y=5)

recordGamePanel = ttk.LabelFrame(root, text="Record Game")
recordGamePanel.grid(column=1, row=3, padx=10, pady=20)
recordGamePanel.place(x=145, y=100)

ttk.Label(recordGamePanel, text="Player 1: ").pack()
player1Entry = tk.Entry(recordGamePanel)

player2Entry = tk.Entry(recordGamePanel)
playerEntry = tk.Entry(addPlayersPanel)

player1Entry.pack()

ttk.Label(recordGamePanel, text="Player 2: ").pack()
player2Entry.pack()
resultLabel = ttk.Label(recordGamePanel, text="Result:  ")
resultLabel.pack()
tooltip = CreateToolTip(resultLabel, "Type 1 if player 1 won the game, 0.5 if it was a draw and 0 if player 2 won the "
                                     "game")
resultEntry = ttk.Entry(recordGamePanel)
resultEntry.pack()
playerEntry.pack()
ttk.Button(addPlayersPanel, text="Add", command=addingPlayer).pack()
ttk.Button(recordGamePanel, text="Record Results", command=recordResults).pack()


panelReset = ttk.LabelFrame(root, text="Reset League standings")
panelReset.grid(column=1, row=3, padx=10, pady=20)
panelReset.place(x=145, y=275)
ttk.Button(panelReset, text="Variable", command=resetLeague).pack()


root.geometry(f'{window_width}x{window_height}+{center_x}+{center_y}')
root.resizable(False, False)
root.mainloop()
