import json
from collections import namedtuple
from json import JSONEncoder
import operator
import math


def GetProbability(rating1, rating2):
    x = 1.0 * 1.0 / (1 + 1.0 * math.pow(10, 1.0 * (rating1 - rating2) / 400))

    return x


def getElo(ratingOfPlayer1, ratingOfPlayer2, K, result):
    probOfPlayer1 = GetProbability(ratingOfPlayer1, ratingOfPlayer2)
    probOfPlayer2 = GetProbability(ratingOfPlayer2, ratingOfPlayer1)

    if result == 1:
        ratingOfPlayer1 = ratingOfPlayer1 + K * (1 - probOfPlayer1)
        ratingOfPlayer2 = ratingOfPlayer2 + K * (0 - probOfPlayer2)
    elif result == 0:
        ratingOfPlayer1 = ratingOfPlayer1 + K * (0 - probOfPlayer1)
        ratingOfPlayer2 = ratingOfPlayer2 + K * (1 - probOfPlayer2)
    else:
        ratingOfPlayer1 = ratingOfPlayer1 + K * (0.5 - probOfPlayer1)
        ratingOfPlayer2 = ratingOfPlayer2 + K * (0.5 - probOfPlayer2)

    return int(round(ratingOfPlayer1, 1)), int(round(ratingOfPlayer2, 1))


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

clearConsole = lambda: print('\n' * 150)

print("Chess league: \n")


def getLeagueTable(inputLeague):
    sortedList = sortObject(inputLeague)
    for i in range(len(inputLeague.players)):
        print(str(i + 1) + ". " + sortedList[i].name + ": " + str(sortedList[i].rating))


print(getLeagueTable(league))
print("--------------------------")


def writeStandings(param, leagueForDump):
    with open(param, "w") as w:
        w.write(objIntoJson(param, leagueForDump))


while True:
    writeStandings("league.json", league)
    print("1. Add new player \n"
          "2. Record Score \n"
          "3. Reset League")
    choice = int(input())
    if choice == 1:
        inputName = input("Enter players name: ")
        playerToAppend = Player(1000, inputName)
        league.players.append(playerToAppend)
        clearConsole()
        print(getLeagueTable(league))

    elif choice == 2:

        player1 = getPlayer(input("Enter player 1: "))
        player2 = getPlayer(input("Enter player 2: "))
        resultOfGame = float(input("Result for player  (1 for win of player 1, 0.5 for draw and 0 for loss"))

        league.players[league.players.index(player1)].rating, league.players[
            league.players.index(player2)].rating = getElo(player1.rating, player2.rating, 25, resultOfGame)
        clearConsole()
        print(getLeagueTable(league))
        writeStandings("league.json", league)

    else:
        for ply in league.players:
            ply.rating = 1000
        print("Reset.")
