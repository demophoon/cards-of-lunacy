from pyramid.view import view_config

from websocket import Client

cards = {
    'white': [],
    'black': [],
}


@view_config(route_name='home', renderer='templates/mytemplate.pt')
def my_view(request):
    return {'project': 'lunacy'}


@view_config(route_name='render_cards', renderer='json')
def render_cards(request):
    return cards


@view_config(route_name='render_rooms', renderer='json')
def render_rooms(request):
    return [{
        'id': x.id,
        'players': len(x.players),
    } for x in Client.rooms]


def includeme(config):
    config.add_route('home', '/')
    config.add_route('render_cards', '/api/cards')
    config.add_route('render_rooms', '/api/rooms')
    config.include('lunacy.websocket')
