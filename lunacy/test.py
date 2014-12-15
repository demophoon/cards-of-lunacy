from websocket import (Room, Player)

room = None
players = None


def play_cards(player):
    judge_card = player.room.judge_card
    played_cards = player._hand[0:max(1, judge_card.count("_"))]
    print "Player %s played %s" % (
        player.alias,
        str(played_cards),
    )
    player.play_cards(played_cards)


def print_scores(room):
    for player in room.players:
        print "Player %s has %d points" % (
            player.alias,
            player.points,
        )


def main():
    global room
    global players
    print "Initializing Objects..."
    room = Room()
    players = [Player(None, room, x) for x in [
        'Britt',
        'Claire',
        'Brian',
    ]]

    print "Room: ", room
    print "Players: ", room.players

    print "Starting Game..."
    room.start()

    play_cards(players[0])
    play_cards(players[1])
    play_cards(players[2])

    players[0].vote_for_cards(1)
    players[1].vote_for_cards(0)
    players[2].vote_for_cards(0)

    print "Played Cards:"
    print room.hand

    room.end_round()

    print_scores(room)

if __name__ == '__main__':
    main()
