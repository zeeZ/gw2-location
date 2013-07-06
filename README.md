gw2-location
============

Python Guild Wars 2 location distribution server thing


## server
Provides two hooks for *WebSockets*:

* / players.json / **key** *(used by map)*: Will continually push location updates for all senders providing data for **key**.
* / publish / **key** *(used by client)*: Expects a stream of base64 encoded JSON strings of (already adjusted) player location data.

## client
Attempts to read [MumbleLink](http://mumble.sourceforge.net/Link) in-memory data provided by *Guild Wars 2*, fetch some necessary information from the API to adjust player location, and send it to the server.

## web
A basic map displaying player location for a given key

Note
====

The while thing was perpetually drawn together, torn apart and put together from a different angle, and I have no idea what I'm doing, so it looks how it looks :P I'm open to comments, suggestions, requests (-ish)