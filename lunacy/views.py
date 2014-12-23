from pyramid.view import view_config
from pyramid.httpexceptions import HTTPFound

from websocket import Client
import lunacy.decks as decks


@view_config(route_name='home', renderer='templates/mytemplate.pt')
def my_view(request):
    raise HTTPFound(location='/static/')
    return {'project': 'lunacy'}


@view_config(route_name='render_cards', renderer='json')
def render_cards(request):
    return decks.default


@view_config(route_name='render_rooms', renderer='json')
def render_rooms(request):
    rooms = []
    for k, v in Client.rooms.items():
        rooms.append(v.state())
    return rooms


@view_config(route_name='render_clients', renderer='json')
def render_clients(request):
    clients = [{
        'id': x.player.id,
        'alias': x.player.alias,
        'room': x.player.room,
    } for x in Client.clients]
    for client in clients:
        if client['room']:
            client['room'] = client['room'].id
    return clients


def includeme(config):
    config.add_route('home', '/')
    config.add_route('render_cards', '/api/cards')
    config.add_route('render_rooms', '/api/rooms')
    config.add_route('render_clients', '/api/clients')
    config.include('lunacy.websocket')
