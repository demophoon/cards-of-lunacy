import time
import threading
import json
import random

import shortuuid

from pyramid_sockjs.session import Session


# Custom Exceptions
class PlayError(Exception):

    def __init__(self, msg=None):
        if msg:
            self.msg = msg

    def __str__(self):
        return "Play Error: %s" % self.msg


class ArgumentError(Exception):

    def __init__(self, msg=None):
        if msg:
            self.msg = msg
        else:
            self.msg = "Not enough arguments"

    def __str__(self):
        return "Argument Error: %s" % self.msg


class PermissionError(Exception):

    def __str__(self):
        msg = "You do not have the required permissions for this action"
        return "Argument Error: %s" % msg


class JoinError(Exception):

    def __init__(self, msg=None):
        if msg:
            self.msg = msg

    def __str__(self):
        return "Join Error: %s" % self.msg


class Room(object):

    """ Creates a room for CAH.  Contains player information and game state.
    """

    MAX_PLAYERS = 8
    MIN_PLAYERS = 2

    def __init__(self, owner=None, deck=None):
        self.id = shortuuid.uuid()
        self.alias = None
        self.owner = owner
        if not deck:
            deck = json.loads(open('./lunacy/cards.json', 'r').read())
        self.judge_deck = deck['black']
        self.select_deck = deck['white']

        self.players = []
        self.current_round_player_count = 0
        self.current_select_deck = None

        self.hand = []
        self.judge_card = None

        self.inactivity_timer = threading.Timer(10.0, self.remove_room)
        self.inactivity_timer.start()

    def __repr__(self):
        return self.__str__()

    def __str__(self):
        return "<Room Id: %s>" % str(self.id)

    def state(self, sensitive_data=False):
        state_obj = {
            'id': self.id,
            'alias': self.alias,
            'players': [x.state(sensitive_data) for x in self.players],
            'admin': self.get_admin(),
            'judge_card': self.judge_card,
            'hand': [{
                'cards': x['cards'],
                'votes': len(x['votes']),
            } for x in self.hand],
        }
        if state_obj['admin']:
            state_obj['admin'] = state_obj['admin'].id
        if sensitive_data:
            state_obj['hand'] = [{
                'player': x['player'].id,
                'cards': x['cards'],
                'votes': [y.id for y in x['votes']],
            } for x in self.hand]
        return state_obj

    def get_admin(self):
        if len(self.players):
            return self.players[0]
        return None

    def join(self, player):
        self.inactivity_timer.cancel()
        if len(self.players) >= self.MAX_PLAYERS:
            raise JoinError("No more open slots")
        self.send_message_to_room("Player '%s' has joined." % player.alias)
        player.room = self
        self.players.append(player)
        if len(self.players) >= self.MIN_PLAYERS:
            self.start()
        self.send_state_to_players()

    def part(self, player):
        self.players.remove(player)
        self.send_state_to_players()
        self.send_message_to_room("Player '%s' has left." % player.alias)
        if len(self.players) == 0:
            print "Room %s has been removed due to inactivity" % self.id
            self.remove_room()
        Client.looking_for_room()

    def remove_room(self):
        del Client.rooms[self.id]
        Client.looking_for_room()

    def start(self):
        if len(self.players) < self.MIN_PLAYERS:
            raise PlayError(
                "Not enough players. Current Count: %d, needed: %d" % (
                    len(self.players),
                    self.MIN_PLAYERS,
                )
            )
        self.broadcast_to_room({
            'action': 'start_round',
        })
        self.current_select_deck = self.card_generator()
        for player in self.players:
            player.hand([])
            player.draw(Player.CARDS_PER_HAND)
        self.current_round_player_count = len(self.players)
        self.start_round()

    def start_round(self):
        self.hand = []
        self.judge_card = random.choice(self.judge_deck)

        print "Starting Round! Judge card is: %s" % self.judge_card
        self.send_state_to_players()

    def end_round(self):
        winners = sorted(self.hand, key=lambda x: len(x['votes']), reverse=True)
        if winners[0]['votes'] > 0:
            winners[0]['player'].points += 10
            self.send_message_to_room(
                '%s has won the round with %s! New round starting...' % (
                    winners[0]['player'].alias,
                    ', '.join(winners[0]['cards']),
                )
            )
            self.tmp = threading.Timer(5.0, self.start)
            self.tmp.start()
        for winner in winners[1:]:
            winner['player'].points += len(winner['votes'])
        self.send_state_to_players()

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
        if player not in self.players:
            raise PlayError("Player not in room")

        if player in [x['player'] for x in self.hand]:
            raise PlayError("Player has already played")

        for card in cards:
            if card not in player_hand:
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
        self.send_state_to_players()

    def vote_for_cards(self, player, cards):
        vote_count = sum([len(x['votes']) for x in self.hand])
        if vote_count == 0:
            self.next_round_timer = threading.Timer(30.0, self.end_round)
            self.next_round_timer.start()
            self.broadcast_to_room({
                'action': 'countdown',
                'time': 30,
                'message': '30 seconds left to vote.',
            })
        vote = [x for x in self.hand if cards == x['cards']]
        if len(vote) == 0:
            raise PlayError("Cards not found")
        vote = vote[0]
        if vote['player'] == player:
            raise PlayError("Cannot vote for own cards")
        if any([player in x['votes'] for x in self.hand]):
            raise PlayError("Player has already voted")
        vote['votes'].append(player)
        vote_count = sum([len(x['votes']) for x in self.hand])
        if vote_count == self.current_round_player_count:
            self.next_round_timer.cancel()
            self.end_round()
        self.send_state_to_players()

    def send_message_to_room(self, message):
        self.broadcast_to_room({
            'action': 'new_message',
            'sender': 'Room',
            'body': message,
            'message_type': {
                'room': True,
            },
        })

    def broadcast_to_room(self, payload):
        for player in self.players:
            player.websocket.reply(payload)

    def send_state_to_players(self):
        for player in self.players:
            player.websocket.get_room_state()


class Player(object):

    """ Creates a player object for joining rooms in CAH.
    Contains player state only.
    """

    CARDS_PER_HAND = 10

    def __init__(self, websocket, room=None, alias=None):
        self.id = shortuuid.uuid()
        self.websocket = websocket
        self.alias = alias
        self.room = None
        self.points = 0
        self._hand = []

        if room:
            room.join(self)

    def __repr__(self):
        return self.__str__()

    def __str__(self):
        return "<Player Name: %s>" % self.alias

    def is_admin(self):
        if not self.room:
            raise JoinError("Not currently in a room")
        return self.room.get_admin() == self

    def state(self, with_cards=False):
        state_object = {
            'id': self.id,
            'room': self.room.id,
            'points': self.points,
            'alias': self.alias,
        }
        if with_cards:
            state_object['cards'] = self.hand(),
        return state_object

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

    def vote_for_cards(self, cards):
        self.room.vote_for_cards(self, cards)


class Client(Session):
    clients = []
    rooms = {}

    def __init__(self, *args, **kwargs):
        self.player = Player(self)
        Session.__init__(self, *args, **kwargs)

    def broadcast_to_room(self, payload):
        for player in self.player.room.players:
            player.websocket.send(json.dumps(payload))

    def looking_for_room(self):
        for client in [x for x in self.clients if not x.player.room]:
            client.send(json.dumps({
                'action': 'update_room_list',
                'rooms': self.simple_room_list(),
            }))

    def simple_room_list(self):
        avail_rooms = []
        for id, room in self.rooms.items():
            room_state = room.state()
            avail_rooms.append({
                'id': id,
                'alias': room_state['alias'],
                'players': [x['alias'] for x in room_state['players']],
            })
        return avail_rooms

    def reply(self, payload):
        self.send(json.dumps(payload))

    def error(self, message):
        self.reply({
            'action': 'error',
            'message': message,
        })

    def get_room_state(self):
        self.reply({
            'action': 'room_state',
            'state': self.player.room.state(),
        })

    def get_room_list(self, **kwargs):
        return {
            'action': 'update_room_list',
            'rooms': self.simple_room_list(),
        }

    def init_room(self, **kwargs):
        if not self.player.alias:
            raise JoinError("Player must have alias before creating room")
        room = Room(owner=self.player)
        while room.id in self.rooms:
            room = Room()
        self.rooms[room.id] = room
        self.looking_for_room()
        return {
            'action': 'init_room',
            'message': 'Room Created',
            'id': room.id,
        }

    def join_room(self, **kwargs):
        if not all([x in kwargs for x in [
            'room_id',
        ]]):
            raise ArgumentError()
        room = self.rooms.get(kwargs['room_id'])
        if not self.player.alias:
            raise JoinError("Player must have alias before joining room")
        if not room:
            raise JoinError("Room does not exist")
        room.join(self.player)
        self.looking_for_room()
        return {
            'action': 'connect_room',
            'id': room.id,
        }

    def part_room(self, **kwargs):
        room = self.player.room
        if not room:
            raise JoinError("You are not currently in a room")
        room.part(self.player)
        Client.looking_for_room()

    def set_player_alias(self, **kwargs):
        if not all([x in kwargs for x in [
            'alias',
        ]]):
            raise ArgumentError()
        self.player.alias = kwargs['alias']

    def set_room_alias(self, **kwargs):
        if not all([x in kwargs for x in [
            'alias',
        ]]):
            raise ArgumentError()
        if not self.player.is_admin():
            self.error("You do not have access to this command")
        if not self.player.room:
            raise JoinError("You are not currently in a room")
        self.player.room.alias = kwargs['alias']

    def start_room(self, **kwargs):
        if not self.player.is_admin():
            self.error("You do not have access to this command")
            return
        self.player.room.start()

    def play_cards(self, **kwargs):
        if not all([x in kwargs for x in [
            'cards',
        ]]):
            raise ArgumentError()
        self.player.play_cards(kwargs['cards'])

    def vote_cards(self, **kwargs):
        if not all([x in kwargs for x in [
            'cards',
        ]]):
            raise ArgumentError()
        self.player.vote_for_cards(kwargs['cards'])

    def broadcast_chat(self, **kwargs):
        if not all([x in kwargs for x in [
            'body',
        ]]):
            raise ArgumentError()
        kwargs['body'] = kwargs['body'].strip()
        if kwargs['body']:
            self.broadcast_to_room({
                'action': 'new_message',
                'body': kwargs['body'],
                'sender': self.player.alias,
            })

    def on_open(self):
        self.clients.append(self)
        print "Client connected and placed into pool."

    def on_close(self):
        self.clients.remove(self)
        if self.player.room:
            self.player.room.part(self.player)
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

        print payload

        actions = {
            # Player Actions
            'set_player_alias': self.set_player_alias,
            'join_room': self.join_room,
            'part_room': self.part_room,
            'play_cards': self.play_cards,
            'vote_cards': self.vote_cards,
            'send_message': self.broadcast_chat,

            # Room Actions
            'init_room': self.init_room,
            'start_room': self.start_room,
            'set_room_alias': self.set_room_alias,

            # Util Actions
            'get_room_list': self.get_room_list,
        }

        if 'action' in payload:
            action = actions.get(payload['action'])
            try:
                response = None
                if action:
                    response = action(**payload)
                if response:
                    self.reply(response)
                print "%s (%s): %s" % (
                    str(self.player),
                    str(action.__name__),
                    str(response),
                )
            except Exception as e:
                print "error here"
                print e
                self.reply({
                    'action': 'error',
                    'message': str(e)
                })


def includeme(config):
    config.include('pyramid_sockjs')
    config.add_sockjs_route(prefix='/api/play', session=Client)
    pass
