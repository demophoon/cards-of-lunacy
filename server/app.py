from twisted.internet import reactor
from autobahn.websocket import WebSocketServerFactory, \
                                WebSocketServerProtocol, \
                                listenWS
import threading
import time
import random
import json
import string

clients = {}
rooms = {}

adminToken = "" 

deckLocation = "./cards.json"

decks = json.loads(open(deckLocation, 'r').read())

class StatsServerProtocol(WebSocketServerProtocol):

    def onOpen(self):
        self.factory.register(self)

    def onMessage(self, msg, binary):
        global rooms
        print binary
        data = json.loads(msg)
        print data
        response = {}
        if 'room' in data:
            if data['action'] == "join":
                self.currentInfo['clientName'] = data['clientName']
                if data['room'] in rooms:
                    if self.factory.clients[data['clientId']].currentInfo['activeRoom'] == None:
                        if len(rooms[data['room']]['users']) >= rooms[data['room']]['options']['maxPlayers']:
                            self.factory.clients[data['clientId']].sendMessage(json.dumps({'error':'roomFull'}))
                        else:
                            self.factory.clients[data['clientId']].currentInfo['activeRoom'] = data['room']
                            rooms[data['room']]['users'].append({
                                'id':data['clientId'],
                                'name':data['clientName'],
                                'score':0,
                                'canPlay':False,
                            })
                            self.factory.clients[data['clientId']].sendMessage(json.dumps({
                                "action":"gameJoined",
                                "gameState":rooms[data['room']],
                                "roomId":data['room'],
                            }))
                            for player in rooms[data['room']]['users']:
                                self.factory.clients[player['id']].sendMessage(json.dumps({
                                    "action":"playerJoined",
                                    "gameState":rooms[data['room']],
                                    "playerName":data['clientName'],
                                }))
                                if len(rooms[data['room']]['users']) >= 2 and not(rooms[data['room']]['options']['started']):
                                    rooms[data['room']]['options']['started'] = True
                                    reactor.callLater(3, self.onMessage, msg=json.dumps({
                                        "action":"startGame",
                                        "room":data['room'],
                                        "clientId":adminToken,
                                        "clientName":"admin",
                                    }), binary=False)

                    else:
                        self.sendMessage(json.dumps({'error':'activeInAnotherRoom'}))
                else:
                    self.sendMessage(json.dumps({'error':'roomDoesNotExist'}))
                    self.sendMessage(json.dumps({'action':'createRoom'}))
            elif data['action'] == "requestDrawCard":
                for playerId in [x['id'] for x in rooms[data['room']]['users'] if not(x['id'] == data['clientId'])]:
                    self.factory.clients[playerId].sendMessage(json.dumps({"action":"discardCard"}))
                self.factory.clients[data['clientId']].sendMessage(json.dumps({"action":"drawCard"}))
                rooms[data['room']]['options']['seedAdvance'] += 1

            elif data['action'] == "drawnCard":
                rooms[data['room']]['decks'][data['type']][:] = [x for x in rooms[data['room']]['decks'][data['type']] if not(x==data['card'])]
            elif data['action'] == "startGame":
                if data['clientId'] == adminToken or self.factory.clients[data['clientId']].peerstr == self.peerstr:
                    rooms[data['room']]['judge'] = rooms[data['room']]['users'][rooms[data['room']]['judgeIndex']]['id']
                    for player in rooms[data['room']]['users']:
                        self.factory.clients[player['id']].sendMessage(json.dumps({
                            "action":"newJudgeCard",
                            "judge":rooms[data['room']]['users'][rooms[data['room']]['judgeIndex']]['id'],
                        }))
                    rooms[data['room']]['judgeIndex'] += 1
                    if rooms[data['room']]['judgeIndex'] >= len(rooms[data['room']]['users']):
                        rooms[data['room']]['judgeIndex'] = -1
                    rooms[data['room']]['options']['open'] = False
                    rooms[data['room']]['options']['seedAdvance'] += 1
                else:
                    self.sendMessage(json.dumps({
                        "error":"authenticationError",
                    }))
            elif data['action'] == "sendToJudge":
                self.factory.clients[rooms[data['room']]['judge']].sendMessage(json.dumps({
                    'action':'playerChoice',
                    'id':data['clientId'],
                    'card':data['card'],
                }))
            elif data['action'] == "pickWinner":
                for x in range(len(rooms[data['room']]['users'])):
                    print rooms[data['room']]['users'][x]['id'], data['player']
                    if rooms[data['room']]['users'][x]['id'] == data['player']:
                        rooms[data['room']]['users'][x]['score'] += 1
                for player in rooms[data['room']]['users']:
                    self.factory.clients[player['id']].sendMessage(json.dumps({
                        'action':'winningPick',
                        'player':self.factory.clients[data['player']].currentInfo['clientName'],
                        'cardId':data['card'],
                        'gameState':rooms[data['room']],
                        'waitTime':7
                    }))
                reactor.callLater(7, self.onMessage, msg=json.dumps({
                    "action":"startGame",
                    "room":data['room'],
                    "clientId":adminToken,
                    "clientName":"admin",
                }), binary=False)

            elif data['action'] == "sync":
                None
                # ToDo
            else:
                self.factory.clients[data['clientId']].sendMessage(json.dumps({'error':'invalidCommand'}))
                
        elif data['action'] == "createRoom":
            if not(self.factory.clients[data['clientId']].currentInfo['activeRoom']):
                try:
                    newRoomId = generateRoomId()
                    response['action'] = "gameJoined"
                    response['roomId'] = newRoomId
                    response['gameState'] = {
                        'users':[
                            {
                                'id':data['clientId'],
                                'name':data['clientName'],
                                'score':0,
                                'canPlay':False,
                            }
                        ],
                        'judge':data['clientId'],
                        'judgeIndex':-1,
                        'options':{
                            'maxPlayers':16,
                            'private':False,
                            'seed':random.random(),
                            'seedAdvance':0,
                            'cardsInHand':10,
                            'open':True,
                            'started':False
                        },
                        'owner':data['clientId'],
                        'decks':{
                            'white':range(0,len(decks['white'])-1),
                            'black':range(0,len(decks['black'])-1),
                        },
                    }
                    rooms[newRoomId] = response['gameState']
                    self.sendMessage(json.dumps(response))
                    self.currentInfo['activeRoom'] = newRoomId
                except Exception as e:
                    print e
            else:
                self.sendMessage(json.dumps({'error':'activeInAnotherRoom'}))
        else:
            self.sendMessage({'action':'createRoom'});


    def connectionLost(self, reason):
        WebSocketServerProtocol.connectionLost(self, reason)
        self.factory.unregister(self)


class StatsBroadcaster(WebSocketServerFactory):

    def __init__(self, url, debug=False, debugCodePaths=False):
        WebSocketServerFactory.__init__(self, url, debug=debug, debugCodePaths=debugCodePaths)
        self.clients = {}

    def pingClients(self):
        pingCommand = {'action':'ping'}
        for client in self.clients:
            self.clients[client.peerstr]['lastping'] = time.time()
            client.sendMessage(json.dumps(pingCommand))
        
    def register(self, client):
        newClientId = generateUserId()
        client.id = newClientId
        client.currentInfo = {
            "activeRoom":None,
            "clientName":None,
        }
        self.clients[newClientId] = client
        client.sendMessage(json.dumps({"action":"register","clientId":client.id}))
        print "Client Registered: %s" % client.id
        print clients

    def unregister(self, client):
        global rooms
        if client.id in self.clients:
            if client.currentInfo['activeRoom']:
                rooms[client.currentInfo['activeRoom']]['users'][:] = [x for x in rooms[client.currentInfo['activeRoom']]['users'] if not(x['id'] == client.id)]
                for player in rooms[client.currentInfo['activeRoom']]['users']:
                    self.clients[player['id']].sendMessage(json.dumps({
                        "gameState":rooms[client.currentInfo['activeRoom']],
                        "action":"playerLeft",
                    }))
                if len(rooms[client.currentInfo['activeRoom']]['users']) == 0:
                    rooms = {k:v for k,v in rooms.items() if k=="roomId" and v==client.currentInfo['activeRoom']}
                    print "Empty Room Removed"
            self.clients.pop(client.id)
            print "Client Unregistered: %s" % client.id
            print clients

    def broadcast(self, msg):
        print "Broadcasting Message to all clients..."
        for client in self.clients:
            client.sendMessage(msg)

def generateUserId(l=8):
    cid = ''.join(random.choice(string.letters + string.digits) for x in range(l))
    while cid in clients:
        cid = generateUserId()
    return cid

def generateRoomId(l=8):
    rid = ''.join(random.choice(string.letters + string.digits) for x in range(l))
    while rid in rooms:
        rid = generateRoomId()
    return rid

if __name__ == '__main__':
    print "Initalizing Server..."
    adminToken = generateUserId(24)
    print "Admin Token Generated: %s " % adminToken

    ServerFactory = StatsBroadcaster
    factory = ServerFactory("ws://localhost:9876")
    factory.protocol = StatsServerProtocol
    listenWS(factory)
    print "Reactor Running"
    reactor.run()

