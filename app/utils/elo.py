def GetProbability(rating1, rating2):
    return 1 / (1 + 10 ** ((rating2 - rating1) / 400))

def getElo(ratingOfPlayer1, ratingOfPlayer2, K, result):
    expected = GetProbability(ratingOfPlayer1, ratingOfPlayer2)
    actual = result
    change = K * (actual - expected)
    
    newRatingOfPlayer1 = int(round(ratingOfPlayer1 + change))
    newRatingOfPlayer2 = int(round(ratingOfPlayer2 - change))
    
    return newRatingOfPlayer1, newRatingOfPlayer2 