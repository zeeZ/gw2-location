import threading
import time
import urllib2
import argparse
import logging

try: import simplejson as json
except ImportError: import json

import tornado
import tornado.httpserver
import tornado.websocket
import tornado.ioloop
import tornado.web


_NOTIFIER = None
_PLAYERS = {}


# Location data is received as a .encode('base64) encoded str containing these fields

class Player(object):
    def __init__(self, data):
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
        if not isinstance(obj, Player):
            return super(PlayerEncoder, self).default(obj)

        return obj.__dict__


class Notifier(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self.clients = set()
        self.running = True

    def register(self, client):
        self.clients.add(client)

    def unregister(self, client):
        self.clients.remove(client)

    def run(self, ):
        logging.debug("Notifier started")
        while self.running:
            try:
                output = json.dumps(_PLAYERS.values(), cls=PlayerEncoder)
                for client in self.clients:
                    try:
                        client.write_message(output)
                    except Exception, e:
                        # Look, effort!
                        logging.exception("Sending...", e)
            except Exception, e:
                # Look, effort!
                logging.exception("Looping...", e)
            time.sleep(0.1)
        # Should do something about this
        logging.debug("Notifier stopped")


class WSHandler(tornado.websocket.WebSocketHandler):
    def open(self):
        # New connection
        logging.debug("WebSocket client connect")
        _NOTIFIER.register(self)

    def on_close(self):
        # Connection closed
        logging.debug("WebSocket client disconnect")
        _NOTIFIER.unregister(self)


class PublishHandler(tornado.websocket.WebSocketHandler):
    player = None

    def open(self):
        logging.debug("Location client connect")

    def on_close(self):
        logging.debug("Location client disconnect")
        if self.player:
            logging.debug("Removal of player", self.player.name, ":", "failed" if _PLAYERS.pop(self.player.name,None) == None else "success")
        else:
            logging.debug("No player attached")

    def on_message(self, message):
        logging.debug("Received player location message")
        message = message.decode("base64")
        data = json.loads(message)
        player = Player(data)
        if self.player and self.player.name != player.name:
            logging.debug("Player name changed")
            _PLAYERS.pop(self.player.name,None)
        self.player = player
        _PLAYERS[self.player.name] = self.player


application = tornado.web.Application([
    (r'/players.json', WSHandler),
    (r'/publish', PublishHandler),
])


def main():
    loglevels = {'debug': logging.DEBUG,
                 'info': logging.INFO,
                 'warn': logging.WARN,
                 'error': logging.ERROR
                 }

    parser = argparse.ArgumentParser(description='Player Location Srever Thing (tm)')
    parser.add_argument('-p',default=8888,type=int,dest='port',help='Listen port for the WebSocket')
    parser.add_argument('-l',default='info',choices=loglevels.keys(),dest='loglevel',help='Log level')
    args = parser.parse_args()

    logging.basicConfig(format='%(asctime)s %(levelname)s %(message)s', level=loglevels[args.loglevel])

    _NOTIFIER = Notifier()
    _NOTIFIER.start()
    http_server = tornado.httpserver.HTTPServer(application)
    logging.info("Listening on port %d", args.port)
    http_server.listen(args.port)
    tornado.ioloop.IOLoop.instance().start()
    _NOTIFIER.running = False # As if


if __name__ == "__main__":
    main()
