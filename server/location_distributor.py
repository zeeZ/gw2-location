#!/usr/bin/env python2
import threading
import time
import urllib2
import argparse
import logging

try: import simplejson as json
except ImportError: import json

# https://pypi.python.org/pypi/tornado/
import tornado
import tornado.httpserver
import tornado.websocket
import tornado.ioloop
import tornado.web


_NOTIFIER = None
_PLAYERS = {}


# Location data is received as a .encode('base64) encoded str containing these fields

class Player(object):
    def __init__(self, key):
        self._key = key

    def _update(self, data):
        self.name = data['name']            # str identity
        self.map = data['map']              # int from context
        self.face = data['face']            # float -(math.atan2(fAvatarFront[2],fAvatarFront[0])*180/math.pi)%360
        self.continent = data['continent']  # int continent_id from maps.json
        self.elevation = data['elevation']  # float fAvatarPosition[1]
        self.position = data['position']    # float[3] already calculated from map_rect to continent_rect, possibly using this:
                                            # def continent_coords(continent_rect, map_rect, point):
                                            #    return (
                                            #        ( point[0]-map_rect[0][0])/(map_rect[1][0]-map_rect[0][0])*(continent_rect[1][0]-continent_rect[0][0])+continent_rect[0][0],
                                            #        (-point[1]-map_rect[0][1])/(map_rect[1][1]-map_rect[0][1])*(continent_rect[1][1]-continent_rect[0][1])+continent_rect[0][1]
                                            #    )



class PlayerEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Player):
            return dict((name, getattr(obj, name)) for name  in dir(obj) if not name.startswith("_"))
        elif isinstance(obj, set):
            return tuple(obj)
        return super(PlayerEncoder, self).default(obj)



class Notifier(threading.Thread):
    def __init__(self, freq):
        threading.Thread.__init__(self)
        self.clients = {}
        self.running = True
        self.frequency = freq

    def register(self, client):
        if client.key not in self.clients:
            logging.debug("New key: %s", client.key)
            self.clients[client.key] = set()
        self.clients[client.key].add(client)
        logging.debug("Client registered for %s", client.key)

    def unregister(self, client):
        logging.debug("Client unregistering for %s", client.key)
        if client.key in self.clients:
            self.clients[client.key].remove(client)
            logging.debug("Client key removed")
            if len(self.clients[client.key]) == 0:
                logging.debug("No more clients for key %s", client.key)
                del self.clients[client.key]
        logging.debug("There are now %d keys left", len(self.clients.keys()))

    def run(self, ):
        logging.debug("Notifier started")
        while self.running:
            try:
                for key, clients in self.clients.items():
                    output = json.dumps(_PLAYERS.get(key,()), cls=PlayerEncoder)
                    for client in clients:
                        try:
                            client.write_message(output)
                        except Exception, e:
                            # Look, effort!
                            logging.error("Exception while sending or something")
                            logging.exception(e)
            except Exception, e:
                # Look, effort!
                logging.error("Exception in outer loop or something")
                logging.exception(e)
            time.sleep(self.frequency)
        # Should do something about this
        logging.debug("Notifier stopped")


class WSHandler(tornado.websocket.WebSocketHandler):
    def open(self, key=''):
        # New connection
        self.key = hash(key)
        logging.debug("WebSocket client connect with key '%s' hash %d", key, self.key)
        _NOTIFIER.register(self)

    def on_close(self):
        # Connection closed
        logging.debug("WebSocket client disconnect")
        _NOTIFIER.unregister(self)


class PublishHandler(tornado.websocket.WebSocketHandler):
    player = None
    key = None

    def open(self, key=''):
        self.key = hash(key)
        logging.debug("Location client connect for key '%s' hash %d", key, self.key)
        if not self.key in _PLAYERS:
            _PLAYERS[self.key] = set()
        self.player = Player(self.key)
        _PLAYERS[self.key].add(self.player)

    def get(self):
        logging.debug("Got self")


    def on_close(self):
        logging.debug("Location client disconnect")
        _PLAYERS[self.key].discard(self.player)
        if len(_PLAYERS[self.key]) == 0:
            del _PLAYERS[self.key]
            logging.debug("No more players for %s", self.key)
        logging.debug("There are now %s players left", len(_PLAYERS))

    def on_message(self, message):
        logging.debug("Received player location message")
        message = message.decode("base64")
        data = json.loads(message)
        self.player._update(data)


application = tornado.web.Application([
    (r'/players.json(?:/(.*))?', WSHandler),
    (r'/publish(?:/(.*))?', PublishHandler)
])


def main():
    global _NOTIFIER
    loglevels = {'debug': logging.DEBUG,
                 'info': logging.INFO,
                 'warn': logging.WARN,
                 'error': logging.ERROR
                 }

    parser = argparse.ArgumentParser(description='Player Location Srever Thing (tm)')
    parser.add_argument('-p',default=8888,type=int,dest='port',help='Listen port for the WebSocket')
    parser.add_argument('-l',default='info',choices=loglevels.keys(),dest='loglevel',help='Log level')
    parser.add_argument('-f',default=0.1,type=float,dest='frequency',help='Web client update frequency')
    args = parser.parse_args()

    logging.basicConfig(format='%(asctime)s %(levelname)s %(message)s', level=loglevels[args.loglevel])

    _NOTIFIER = Notifier(args.frequency)
    _NOTIFIER.start()


    http_server = tornado.httpserver.HTTPServer(application)
    logging.info("Listening on port %d", args.port)
    try:
        http_server.listen(args.port)
        tornado.ioloop.IOLoop.instance().start()
    except KeyboardInterrupt:
        logging.info("Shutting down")
        tornado.ioloop.IOLoop.instance().stop()
        _NOTIFIER.running = False # As if
        return


if __name__ == "__main__":
    main()
