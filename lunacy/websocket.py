import json
import random

import shortuuid

from pyramid_sockjs.session import Session


# Custom Exceptions
class PlayError:

    def __init__(self, msg=None):
        if msg:
            self.msg = msg

    def __str__(self):
        return "Play Error: %s" % self.msg


class Error:

    def __init__(self, msg=None):
        if msg:
            self.msg = msg

    def __str__(self):
        return "Error: %s" % self.msg


class JoinError:

    def __init__(self, msg=None):
        if msg:
            self.msg = msg

    def __str__(self):
        return "Join Error: %s" % self.msg


class Room(object):

    """ Creates a room for CAH.  Contains player information and game state.
    """

    MAX_PLAYERS = 8
    MIN_PLAYERS = 1

    def __init__(self, deck=None):
        self.id = shortuuid.uuid()
        if not deck:
            deck = json.loads(open('./lunacy/cards.json', 'r').read())
        self.judge_deck = deck['black']
        self.select_deck = deck['white']

        self.players = []
        self.game_state = 'Init'
        self.current_select_deck = None

        self.hand = []
        self.judge_card = None

    def __str__(self):
        return "<Room Id: %s>" % str(self.id)

    def join(self, player):
        if len(self.players) >= self.MAX_PLAYERS:
            raise JoinError("No more open slots")
        player.room = self
        self.players.append(player)

    def quit(self, player):
        self.players.remove(player)

    def start(self):
        if len(self.players) < self.MIN_PLAYERS:
            raise PlayError(
                "Not enough players. Current Count: %d, needed: %d" % (
                    len(self.players),
                    self.MIN_PLAYERS,
                )
            )
        random.shuffle(self.judge_deck)
        self.current_select_deck = self.card_generator()
        for player in self.players:
            player.hand([])
            player.draw(Player.CARDS_PER_HAND)
        self.start_round()

    def start_round(self):
        self.hand = []
        self.judge_card = random.choice(self.judge_deck)

        print "Starting Round! Judge card is: %s" % self.judge_card

    def end_round(self):
        winners = sorted(self.hand, key=lambda x: len(x['votes']), reverse=True)
        winners[0]['player'].points += 10
        for winner in winners[1:]:
            winner['player'].points += len(winner['votes'])

    def card_generator(self):
        random.shuffle(self.select_deck)
        index = -1
        while True:
            index += 1
            if index > len(self.select_deck):
                random.shuffle(self.select_deck)
                index = 0
            yield self.select_deck[index]

    # Card Generator is replaced in start()
    def draw_card(self):
        if not self.current_select_deck:
            raise PlayError("Game has not started.")
        return self.current_select_deck.next()

    def ready(self):
        return all([
            self.judge_card,
            len(self.players) >= self.MIN_PLAYERS,
        ])

    def play_cards(self, player, cards):
        player_hand = player.hand()

        # Is server ready for cards?
        if not self.ready():
            raise PlayError("Player cannot play cards at this time")

        # Check if player can even play
        if not player in self.players:
            raise PlayError("Player not in room")

        if player in [x['player'] for x in self.hand]:
            raise PlayError("Player has already played")

        for card in cards:
            if not card in player_hand:
                raise PlayError("Card not in hand")

        # Correct number of cards?
        if not max(1, self.judge_card.count("_")) == len(cards):
            raise PlayError("Incorrect number of cards played")

        # Play cards and replenish hand

        self.hand.append({
            'player': player,
            'cards': cards,
            'votes': [],
        })
        for card in cards:
            player_hand.remove(card)
            player_hand.append(self.draw_card())
        player.hand(player_hand)

    def vote_for_cards(self, player, idx):
        if player == self.hand[idx]['player']:
            raise PlayError("Cannot vote for own cards")
        if any([player in x['votes'] for x in self.hand]):
            raise PlayError("Player has already voted")
        self.hand[idx]['votes'].append(player)


class Player(object):

    """ Creates a player object for joining rooms in CAH.
    Contains player state only.
    """

    CARDS_PER_HAND = 10

    def __init__(self, websocket, room, alias):
        self.id = shortuuid.uuid()
        self.websocket = websocket
        self.alias = alias
        self.room = None
        self.points = 0
        self._hand = []

        room.join(self)

    def __str__(self):
        return "<Player Name: %s>" % self.alias

    def hand(self, setter=None):
        if setter:
            self._hand = setter
            self.websocket.reply({
                'action': 'update_hand',
                'hand': self._hand,
            })
        return self._hand

    def draw(self, count=1):
        hand = self.hand()
        for _ in range(count):
            if len(hand) >= self.CARDS_PER_HAND:
                break
            hand.append(self.room.draw_card())
        self.hand(hand)

    def play_cards(self, cards):
        self.room.play_cards(self, cards)

    def get_vote_hand(self):
        return [x['cards'] for x in self.room.hand if not x['player'] == self]

    def vote_for_cards(self, idx):
        self.room.vote_for_cards(self, idx)


class Client(Session):
    clients = []
    rooms = []

    def __init__(self, *args, **kwargs):
        self.player = None
        self.room = None
        Session.__init__(self, *args, **kwargs)

    def broadcast_to_room(self, payload):
        for player in self.player.room.players:
            player.websocket.send(json.dumps(payload))

    def reply(self, payload):
        self.send(json.dumps(payload))

    def error(self, message):
        self.reply({
            'action': 'error',
            'message': message,
        })

    def init_room(self, **kwargs):
        room = Room()
        self.room = room
        self.rooms.append(room)
        self.reply({
            'action': 'init_room',
            'message': 'Room Created',
            'room_id': room.id,
        })
        return room.id

    def init_player(self, **kwargs):
        if not all([x in kwargs for x in [
            'alias',
            'room_id',
        ]]):
            raise Error("Not enough Arguments")
        room = [x for x in self.rooms if x.id == kwargs['room_id']]
        if not room:
            raise JoinError("Room does not exist")
        self.player = Player(self, room[0], kwargs['alias'])
        self.reply({
            'action': 'init_player',
            'message': 'Player Created. Joined Room',
            'player_id': self.player.id,
            'room_id': self.player.room.id,
        })

    def start_room(self, **kwargs):
        if not self.room:
            self.error("You do not have access to this command")
            return
        self.room.start()
        self.broadcast_to_room({
            'action': 'log',
            'message': 'Game has been started',
        })

    def on_open(self):
        self.clients.append(self)
        print "Client connected and placed into pool."

    def on_close(self):
        self.clients.remove(self)
        print "Client disconnected and removed from pool."

    def on_message(self, message):
        try:
            payload = json.loads(message)
        except Exception as e:
            print e
            self.reply({
                'action': 'error',
                'message': str(e)
            })

        actions = {
            'init_player': self.init_player,
            'init_room': self.init_room,
            'start_room': self.start_room,
        }
        if 'action' in payload:
            action = actions.get(payload['action'])
            try:
                print "%s (%s): %s" % (
                    str(self.player),
                    str(action.__name__),
                    str(action(**payload)),
                )
            except Exception as e:
                print e
        print payload


def includeme(config):
    config.include('pyramid_sockjs')
    config.add_sockjs_route(prefix='/api/play', session=Client)
    pass
