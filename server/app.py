from twisted.internet import reactor
from autobahn.websocket import WebSocketServerFactory, \
                                WebSocketServerProtocol, \
                                listenWS
import threading
import time
import random
import json
import string

userids = []
clients = {}
rooms = {}

class StatsServerProtocol(WebSocketServerProtocol):

    def onOpen(self):
        self.factory.register(self)

    def onMessage(self, msg, binary):
        data = json.loads(msg)
        response = {}
        if data['room'] in rooms:
            if data['action'] == "join":
                if data['roomId'] in rooms:
                    if len(rooms[data['roomId']]['users']) >= rooms[data['roomId']]['options']['maxPlayers']:
                        self.factory.clients[data['clientId']].sendMessage(json.dumps({'error':'roomFull'}))
                    else:
                        rooms[data['roomId']]['users'].append({
                            'id':data['clientId'],
                            'name':data['clientName'],
                            'score':0,
                            'canPlay':False,
                        })
                else:
                    self.factory.clients[data['clientId']].sendMessage(json.dumps({'error':'roomDoesNotExist'}))
            elif data['action'] == "playCard":
                None
                # ToDo
            elif data['action'] == "pickWinner":
                None
                # ToDo
            elif data['action'] == "sync":
                None
                # ToDo
            else:
                self.factory.clients[data['clientId']].sendMessage(json.dumps({'error':'invalidCommand'}))
                
        else:
            try:
                newRoomId = generateRoomId()
                response['action'] = "createRoom"
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
                    'options':{
                        'maxPlayers':8,
                        'private':False,
                        'seed':newRoomId,
                        'seedAdvance':0,
                    },
                }
                rooms[newRoomId] = response['gameState']
                self.factory.clients[data['clientId']].sendMessage(json.dumps(response))
            except Exception as e:
                print e

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
        global clients
        newClientId = generateUserId()
        client.id = newClientId
        self.clients[newClientId] = client
        clients[newClientId] = client
        client.sendMessage(json.dumps({"action":"register","clientId":client.id}))
        print "Client Registered: %s" % client.id
        print clients

    def unregister(self, client):
        if client.id in self.clients:
            global clients
            self.clients.pop(client.id)
            clients.pop(client.id)
            print "Client Unregistered: %s" % client.id
            print clients

    def broadcast(self, msg):
        print "Broadcasting Message to all clients..."
        for client in self.clients:
            client.sendMessage(msg)

def generateUserId():
    cid = ''.join(random.choice(string.letters + string.digits) for x in range(8))
    while cid in clients:
        cid = generateUserId()
    return cid

def generateRoomId():
    rid = ''.join(random.choice(string.letters + string.digits) for x in range(8))
    while rid in rooms:
        rid = generateRoomId()
    return rid

if __name__ == '__main__':
    print "Initalizing Server..."

    ServerFactory = StatsBroadcaster
    factory = ServerFactory("ws://localhost:9876")
    factory.protocol = StatsServerProtocol
    listenWS(factory)
    print "Reactor Running"
    reactor.run()


