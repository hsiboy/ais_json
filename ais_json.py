#!/usr/bin/python

import warnings
warnings.simplefilter(action='ignore', category=FutureWarning)
import json
import datetime
import time
import random
import requests

POSITION_TYPES = {1, 2, 3, 18}
POSITION_DEDUP_INTERVAL = 120  # seconds


def parsed_to_ais_msg(parsed, rxtime=None):
    """Convert a parsed AIS message dict to an ais_msg dict."""
    if rxtime is None:
        rxtime = datetime.datetime.utcnow().strftime("%Y%m%d%H%M%S")

    ais_msg = {
            'msgtype': parsed['id'],
            'mmsi': parsed['mmsi'],
            'rxtime': rxtime
            }

    if 'x' in parsed:
      ais_msg['lon'] = parsed['x']
    if 'y' in parsed:
      ais_msg['lat'] = parsed['y']
    if 'sog' in parsed:
      ais_msg['speed'] = parsed['sog']
    if 'cog' in parsed:
      ais_msg['course'] = parsed['cog']
    if 'true_heading' in parsed:
      ais_msg['heading'] = parsed['true_heading']
    if 'nav_status' in parsed:
      ais_msg['status'] = parsed['nav_status']
    if 'type_and_cargo' in parsed:
      ais_msg['shiptype'] = parsed['type_and_cargo']
    if 'part_num' in parsed:
      ais_msg['partno'] = parsed['part_num']
    if 'callsign' in parsed:
      ais_msg['callsign'] = parsed['callsign']
    if 'name' in parsed:
      ais_msg['shipname'] = parsed['name']
    if 'vendor_id' in parsed:
      ais_msg['vendorid'] = parsed['vendor_id']
    if 'dim_a' in parsed:
      ais_msg['ref_front'] = parsed['dim_a']
    if 'dim_c' in parsed:
      ais_msg['ref_left'] = parsed['dim_c']
    if 'draught' in parsed:
      ais_msg['draught'] = parsed['draught']
    if 'length' in parsed:
      ais_msg['length'] = parsed['length']
    if 'width' in parsed:
      ais_msg['width'] = parsed['width']
    if 'destination' in parsed:
      ais_msg['destination'] = parsed['destination']
    if 'persons' in parsed:
      ais_msg['persons_on_board'] = parsed['persons']

    return ais_msg


def build_jsonais_batch(msgs, name, url, rxtime=None):
    """Wrap a list of ais_msg dicts into a jsonais output structure."""
    if rxtime is None:
        rxtime = datetime.datetime.utcnow().strftime("%Y%m%d%H%M%S")

    path = {
            "name": name,
            "url": url }

    groups = {
            "path": [path],
            "msgs": msgs }

    output = {
            "encodetime": rxtime,
            "protocol": 'jsonais',
            "groups": [groups]
            }

    return output


def parsed_to_jsonais(parsed, name, url, rxtime=None):
    """Convert a parsed AIS message dict to a jsonais output dict."""
    ais_msg = parsed_to_ais_msg(parsed, rxtime=rxtime)
    return build_jsonais_batch([ais_msg], name, url, rxtime=rxtime)


class AISCache:
    def __init__(self, dedup_interval=POSITION_DEDUP_INTERVAL):
        self.cache = {}              # (mmsi, msgtype) -> ais_msg
        self.last_sent_pos = {}      # mmsi -> (lon, lat, monotonic_time)
        self.dedup_interval = dedup_interval

    def add(self, ais_msg):
        key = (ais_msg['mmsi'], ais_msg['msgtype'])
        self.cache[key] = ais_msg

    def flush(self, now=None):
        if now is None:
            now = time.monotonic()
        msgs = []
        for (mmsi, msgtype), msg in self.cache.items():
            if msgtype in POSITION_TYPES:
                pos = (msg.get('lon'), msg.get('lat'))
                last = self.last_sent_pos.get(mmsi)
                if last and last[0] == pos[0] and last[1] == pos[1] \
                        and (now - last[2]) < self.dedup_interval:
                    continue
                self.last_sent_pos[mmsi] = (pos[0], pos[1], now)
            msgs.append(msg)
        self.cache.clear()
        return msgs


def post_jsonais(url, output):
    """POST a jsonais output dict to the given URL. Returns the response."""
    post = json.dumps(output)
    r = requests.post(url, files={'jsonais': (None, post)})
    return r


if __name__ == '__main__':
    from termcolor import colored
    import ais.stream
    import socket
    from settings import URL, NAME

    IP = '127.0.0.1'
    PORT = 5000

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((IP, PORT))

    cache = AISCache()
    next_send = time.monotonic() + 28 + random.uniform(0, 4)

    while True:
      for msg in ais.stream.decode(sock.makefile('r'), keep_nmea=True):
        parsed = json.loads(json.dumps(msg))
        ais_msg = parsed_to_ais_msg(parsed)
        cache.add(ais_msg)

        now = time.monotonic()
        if now >= next_send:
          msgs = cache.flush(now)
          if msgs:
            output = build_jsonais_batch(msgs, NAME, URL)
            try:
              post_jsonais(URL, output)
            except requests.exceptions.RequestException as e:
              print(e)
          next_send = now + 28 + random.uniform(0, 4)
