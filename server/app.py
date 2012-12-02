from twisted.internet import reactor
from autobahn.websocket import WebSocketServerFactory, \
                                WebSocketServerProtocol, \
                                listenWS
import threading
import time
import random
import json
import string
import sys

from twisted.python import log
log.startLogging(open("./errors.log",'a'))

def logging_handler(type, value, tb):
    f=open('./errors.log','a')
    fstr = "Uncaught exception: " + value + "\n" + tb
    print fstr
    f.write(fstr)
    f.close()

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
        data = json.loads(msg)
        print data
        response = {}
        if 'clientName' in data and not(data['clientName'] == None):
            self.currentInfo['clientName'] = data['clientName']
            for admin in self.factory.administrators:
                admin.sendMessage(json.dumps({'action':'updateClients'}))
        if 'room' in data:
            if data['room'] in rooms:
                room = rooms[data['room']]
            if data['action'] == "join":
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
                nextCard = room['decks']['white'].pop(random.choice(range(len(room['decks']['white']))))
                print nextCard, decks['white'][nextCard]
                self.factory.clients[data['clientId']].sendMessage(json.dumps({"action":"drawCard","card":nextCard}))

            elif data['action'] == "startGame":
                if data['clientId'] == adminToken or self.factory.clients[data['clientId']].peerstr == self.peerstr:
                    rooms[data['room']]['judge'] = rooms[data['room']]['users'][rooms[data['room']]['judgeIndex']]['id']
                    if room["newRound"]:
                        room["newRound"] = False
                        room["judgeCard"] = room['decks']['black'].pop(random.choice(range(len(room['decks']['black']))))
                    for player in rooms[data['room']]['users']:
                        self.factory.clients[player['id']].sendMessage(json.dumps({
                            "action":"newJudgeCard",
                            "judge":rooms[data['room']]['users'][rooms[data['room']]['judgeIndex']]['id'],
                            "judgeCard":room['judgeCard']
                        }))
                    rooms[data['room']]['judgeIndex'] += 1
                    if rooms[data['room']]['judgeIndex'] >= len(rooms[data['room']]['users']):
                        rooms[data['room']]['judgeIndex'] = 0
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
                for player in rooms[data['room']]['users']:
                    if not(self.id == player['id']):
                        self.factory.clients[player["id"]].sendMessage(json.dumps({'action':'discardCard'}))
                    
            elif data['action'] == "pickWinner":
                room["newRound"] = True
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
                        'waitTime':10
                    }))
                reactor.callLater(10, self.onMessage, msg=json.dumps({
                    "action":"startGame",
                    "room":data['room'],
                    "clientId":adminToken,
                    "clientName":"admin",
                }), binary=False)

            elif data['action'] == "newMessage":
                if self.currentInfo['clientName'] == None:
                    self.currentInfo['clientName'] == data['clientName']
                for player in rooms[data['room']]['users']:
                    self.factory.clients[player['id']].sendMessage(json.dumps({
                        'action':'newMessage',
                        'text':data['text'],
                        'from':self.currentInfo['clientName'],
                    }))
                
            elif data['action'] == "sync":
                self.currentInfo['clientName'] = data['clientName']
            else:
                self.factory.clients[data['clientId']].sendMessage(json.dumps({'error':'invalidCommand'}))
                
        elif data['action'] == "createRoom":
            if not(self.factory.clients[data['clientId']].currentInfo['activeRoom']):
                try:
                    newRoomId = generateRoomId()
                    if "roomId" in data:
                        if data["roomId"] not in rooms:
                            newRoomId = data['roomId']
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
                            'seedAdvance':0,
                            'cardsInHand':10,
                            'open':True,
                            'started':False,
                            'permenant':False,
                        },
                        'newRound':True,
                        'judgeCard':None,
                        'ping':-1,
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
        elif data['action'] == "clientList":
            if 'token' in data and data['token'] == adminToken:
                self.sendMessage(json.dumps({
                    "clients":[{
                        'clientId':self.factory.clients[x].id,
                        'activeRoom':self.factory.clients[x].currentInfo['activeRoom'] or " - ",
                        'clientName':self.factory.clients[x].currentInfo['clientName'],
                        'peerstr':self.factory.clients[x].peerstr
                        } for x in self.factory.clients],
                    "action":"clientList",
                }))
        elif data['action'] == "checkAdminToken":
            if not(self.currentInfo['adminTokenCheck']):
                self.currentInfo['adminTokenCheck'] = True
                self.sendMessage(json.dumps({'action':'validate','auth':data['token'] == adminToken}))
                if data['token'] == adminToken:
                    self.factory.administrators.append(self)
                    print self.factory.administrators
        elif data['action'] == "listRooms":
            self.sendMessage(json.dumps({
                "action":"roomsList",
                "rooms":json.dumps(rooms),
            }))
        elif data['action'] == "broadcastMessage":
            if 'token' in data and data['token'] == adminToken:
                self.sendMessage(json.dumps(rooms))
                self.factory.broadcast(json.dumps({
                        'action':'newMessage',
                        'text':data['text'],
                        'from':data['from'],
                        'textClass':data['textClass'],
                    }))
        
        elif data['action'] == "pong":
            self.currentInfo['ping'] = (time.time() - self.currentInfo['lastPingTime']) * 1000
            if self.currentInfo['activeRoom'] in rooms:
                for userId in rooms[self.currentInfo['activeRoom']]['users']:
                    if self.factory.clients[userId['id']].currentInfo['ping'] > rooms[self.currentInfo['activeRoom']]['ping']:
                        rooms[self.currentInfo['activeRoom']]['ping'] = self.factory.clients[userId['id']].currentInfo['ping']

        else:
            self.sendMessage(json.dumps({'action':'createRoom'}));

    def connectionLost(self, reason):
        WebSocketServerProtocol.connectionLost(self, reason)
        self.factory.unregister(self)


class StatsBroadcaster(WebSocketServerFactory):

    def __init__(self, url, debug=False, debugCodePaths=False):
        WebSocketServerFactory.__init__(self, url, debug=debug, debugCodePaths=debugCodePaths)
        self.clients = {}
        self.administrators = []
        reactor.callLater(15, self.pingClients)

    def pingClients(self):
        pingCommand = {'action':'ping'}
        for clientKey in self.clients:
            self.clients[clientKey].currentInfo['lastPingTime'] = time.time()
            self.clients[clientKey].sendMessage(json.dumps(pingCommand))
        reactor.callLater(15, self.pingClients)
        
    def register(self, client):
        newClientId = generateUserId()
        client.id = newClientId
        client.currentInfo = {
            "activeRoom":None,
            "clientName":None,
            "adminTokenCheck":False,
            "hand":[],
            "ping":-1,
            "lastPingTime":time.time(),
        }
        self.clients[newClientId] = client
        client.sendMessage(json.dumps({"action":"register","clientId":client.id}))
        print "Client Registered: %s" % client.id
        for admin in self.administrators:
            admin.sendMessage(json.dumps({'action':'updateClients'}))

    def unregister(self, client):
        global rooms
        if client in self.administrators:
            self.administrators[:] = [x for x in self.administrators if not(x == client)]
        if client.id in self.clients:
            if client.currentInfo['activeRoom']:
                rooms[client.currentInfo['activeRoom']]['users'][:] = [x for x in rooms[client.currentInfo['activeRoom']]['users'] if not(x['id'] == client.id)]
                for player in rooms[client.currentInfo['activeRoom']]['users']:
                    self.clients[player['id']].sendMessage(json.dumps({
                        "gameState":rooms[client.currentInfo['activeRoom']],
                        "action":"playerLeft",
                    }))
                if len(rooms[client.currentInfo['activeRoom']]['users']) == 0:
                    reactor.callLater(300, self.removeRoom, roomId=client.currentInfo['activeRoom'])
                if rooms[client.currentInfo['activeRoom']]['judge'] == client.id:
                    rooms[client.currentInfo['activeRoom']]['judgeIndex'] += 1
                    if rooms[client.currentInfo['activeRoom']]['judgeIndex'] >= len(rooms[client.currentInfo['activeRoom']]['users']):
                        rooms[client.currentInfo['activeRoom']]['judgeIndex'] = 0
                    rooms[client.currentInfo['activeRoom']]['judge'] = rooms[client.currentInfo['activeRoom']]['users'][rooms[client.currentInfo['activeRoom']]['judgeIndex']]['id']
                    for player in rooms[client.currentInfo['activeRoom']]['users']:
                        self.clients[player['id']].sendMessage(json.dumps({
                            "action":"newJudgeCard",
                            "judge":rooms[client.currentInfo['activeRoom']]['users'][rooms[client.currentInfo['activeRoom']]['judgeIndex']]['id'],
                            "judgeCard":rooms[client.currentInfo['activeRoom']]['judgeCard']
                        }))
            self.clients = {k:v for k, v in self.clients.items() if not(k == client.id)}
            print "Client Unregistered: %s" % client.id
        for admin in self.administrators:
            admin.sendMessage(json.dumps({'action':'updateClients'}))

    def removeRoom(self, roomId):
        global rooms
        if len(rooms[roomId]['users']) == 0:
            rooms = {k:v for k,v in rooms.items() if k=="roomId" and v==roomId}
            print "Empty Room Removed"
        
    
    def broadcast(self, msg):
        print "Broadcasting Message to all clients..."
        for client in self.clients:
            self.clients[client].sendMessage(msg)

def generateUserId(l=4):
    cid = ''.join(random.choice(string.letters + string.digits) for x in range(l))
    while cid in clients:
        cid = generateUserId(l+1)
    return cid

def generateRoomId(l=4):
    rid = ''.join(random.choice(string.lowercase + string.digits) for x in range(l))
    while rid in rooms:
        rid = generateRoomId(l+1)
    return rid

if __name__ == '__main__':
    print "Initalizing Server..."
    adminToken = generateUserId(64)
    f = open('adminToken.txt','w')
    f.write(adminToken)
    f.close()
    print "Admin Token Generated: %s " % adminToken

    ServerFactory = StatsBroadcaster
    factory = ServerFactory("ws://localhost:9876")
    factory.protocol = StatsServerProtocol
    listenWS(factory)
    print "Reactor Running"
    reactor.run()


