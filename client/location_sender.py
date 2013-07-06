#!/usr/bin/env python2
import argparse
import ctypes
import logging
import math
import mmap
import sys
import threading
import time
import urllib2

try: import simplejson as json
except ImportError: import json

# https://pypi.python.org/pypi/tornado/
try:
    import tornado
    import tornado.ioloop
    import tornado.websocket
except ImportError:
    print "Tornado framework required, get it at http://www.tornadoweb.org/"
    sys.exit(1)

_MULTIPLIER = 39.3701  # meters to inches
_MAP_INFO_URL = "https://api.guildwars2.com/v1/maps.json?map_id=%d"
_RUNNING = True


class Link(ctypes.Structure):
    _fields_ = [
        ("uiVersion",       ctypes.c_uint32),
        ("uiTick",          ctypes.c_ulong),
        ("fAvatarPosition", ctypes.c_float * 3),
        ("fAvatarFront",    ctypes.c_float * 3),
        ("fAvatarTop",      ctypes.c_float * 3),
        ("name",            ctypes.c_wchar * 256),
        ("fCameraPosition", ctypes.c_float * 3),
        ("fCameraFront",    ctypes.c_float * 3),
        ("fCameraTop",      ctypes.c_float * 3),
        ("identity",        ctypes.c_wchar * 256),
        ("context_len",     ctypes.c_uint32),
        ("context",         ctypes.c_uint32 * (256/4)), # is actually 256 bytes of whatever
        ("description",     ctypes.c_wchar * 2048)

    ]


def Unpack(ctype, buf):
    cstring = ctypes.create_string_buffer(buf)
    ctype_instance = ctypes.cast(ctypes.pointer(cstring), ctypes.POINTER(ctype)).contents
    return ctype_instance


def continent_coords(continent_rect, map_rect, point):
    return (
        ( point[0]-map_rect[0][0])/(map_rect[1][0]-map_rect[0][0])*(continent_rect[1][0]-continent_rect[0][0])+continent_rect[0][0],
        (-point[1]-map_rect[0][1])/(map_rect[1][1]-map_rect[0][1])*(continent_rect[1][1]-continent_rect[0][1])+continent_rect[0][1]
    )


def on_open(ws):
    def run():
        logging.debug("Initializing MumbleLink thingy")
        current_map = 0
        current_map_data = None
        previous_tick = 0
        first = True

        memfile = mmap.mmap(0, ctypes.sizeof(Link), "MumbleLink")
        while _RUNNING:
            memfile.seek(0)
            data = memfile.read(ctypes.sizeof(Link))
            result = Unpack(Link, data)
            if result.uiVersion == 0 and result.uiTick == 0:
                logging.debug("MumbleLink contains no data, setting up and waiting")
                try:
                    init = Link(2,name="Guild Wars 2")
                    memfile.seek(0)
                    memfile.write(init)
                except Exception, e:
                    logging.exception("Error writing init data",e)
            if result.uiTick != previous_tick:
                if first:
                    logging.debug("MumbleLink seems to be active, hope for the best")
                    first = False
                if result.context[7] != current_map:
                    # Map change
                    logging.debug("Player changed maps (%d->%d)", current_map, result.context[7])
                    current_map = result.context[7]
                    try:
                        fp = urllib2.urlopen(_MAP_INFO_URL % current_map)
                        current_map_data = json.load(fp)["maps"][str(current_map)]
                        fp.close()
                    except urllib2.HTTPError:
                        logging.warning("API call for current map information failed")
                        current_map_data = None
                        current_map = 0
                        time.sleep(ws.args.retry_delay)

                data = {
                    "name": result.identity,
                    "map": result.context[7],
                    "face": -(math.atan2(result.fAvatarFront[2],result.fAvatarFront[0])*180/math.pi)%360
                }

                if current_map_data:
                    data.update({
                        "continent": current_map_data["continent_id"],
                        "elevation": result.fAvatarPosition[1]*_MULTIPLIER,
                        "position": continent_coords(current_map_data["continent_rect"], current_map_data["map_rect"], (result.fAvatarPosition[0]*_MULTIPLIER, result.fAvatarPosition[2]*_MULTIPLIER))
                        })
                    logging.debug(data)
                    con.write_message(json.dumps(data).encode("base64"))
            previous_tick = result.uiTick
            time.sleep(ws.args.frequency)

    def status():
        if ws.thread != None and not ws.thread.is_alive():
            logging.info("Restarting update thread")
            start_thread()

    def start_thread():
        ws.thread = threading.Thread(target=run)
        ws.thread.start()

    con = ws.result()
    start_thread()
    tornado.ioloop.PeriodicCallback(status, 1000, tornado.ioloop.IOLoop.instance()).start()


def main():
    global _RUNNING
    loglevels = {'debug': logging.DEBUG,
                 'info': logging.INFO,
                 'warn': logging.WARN,
                 'error': logging.ERROR
                 }

    parser = argparse.ArgumentParser(description='Player Location Sender Thing')
    parser.add_argument('server', help='Destination server address')
    parser.add_argument('-p', default=8888, type=int, dest='port', help='Destination port')
    parser.add_argument('-f', default=0.1, type=float, dest='frequency', help='Update frequency in seconds')
    parser.add_argument('-r', default=5.0, type=float, dest='retry_delay', help='API call retry delay in seconds')
    parser.add_argument('-l', default='info', choices=loglevels.keys(), dest='loglevel', help='Log level')
    parser.add_argument('-k', default='', dest='key', help="Secret key to join")

    args = parser.parse_args()

    logging.basicConfig(format='%(asctime)s %(levelname)s %(message)s', level=loglevels[args.loglevel])

    try:        
        io = tornado.ioloop.IOLoop.instance()
        
        # Empty callback to allow KeyboardInterrupt to slip through
        tornado.ioloop.PeriodicCallback(lambda: None, 1000, io).start()
        
        logging.debug("Connecting to %s on port %d", args.server, args.port)
        ws = tornado.websocket.websocket_connect("ws://%s:%d/publish%s" % (args.server, args.port, "/%s" % args.key))
        ws.args = args
        ws.add_done_callback(on_open)
        io.start()
        # We should probably reconnect on disconnect...
    except KeyboardInterrupt:
        _RUNNING = False
        tornado.ioloop.IOLoop.instance().stop()


if __name__ == "__main__":
    main()
