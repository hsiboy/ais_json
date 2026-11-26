#!/usr/bin/python

import warnings
warnings.simplefilter(action='ignore', category=FutureWarning)
import json
import datetime
import time
import random
import socket
import requests

POSITION_TYPES = {1, 2, 3, 18}
# aprs.fi ignores these message types, they do not have position information
IGNORED_TYPES = {7, 10, 11, 12, 13, 15, 16, 20, 22, 23}
POSITION_DEDUP_INTERVAL = 120  # seconds
SEND_INTERVAL = 28  # seconds, plus 0-4 seconds of random jitter
IDLE_TIMEOUT = 1.0  # seconds to wait for a UDP packet before checking timers


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
      ais_msg['lon'] = round(parsed['x'], 6)
    if 'y' in parsed:
      ais_msg['lat'] = round(parsed['y'], 6)
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


def build_jsonais_batch(msgs, name, rxtime=None):
    """Wrap a list of ais_msg dicts into a jsonais output structure."""
    if rxtime is None:
        rxtime = datetime.datetime.utcnow().strftime("%Y%m%d%H%M%S")

    path = {
            "name": name }

    groups = {
            "path": [path],
            "msgs": msgs }

    output = {
            "encodetime": rxtime,
            "protocol": 'jsonais',
            "groups": [groups]
            }

    return output


def parsed_to_jsonais(parsed, name, rxtime=None):
    """Convert a parsed AIS message dict to a jsonais output dict."""
    ais_msg = parsed_to_ais_msg(parsed, rxtime=rxtime)
    return build_jsonais_batch([ais_msg], name, rxtime=rxtime)


class AISCache:
    def __init__(self, dedup_interval=POSITION_DEDUP_INTERVAL):
        self.cache = {}              # (mmsi, msgtype, partno) -> ais_msg
        self.last_sent_pos = {}      # mmsi -> (lon, lat, status, monotonic_time)
        self.dedup_interval = dedup_interval

    def add(self, ais_msg):
        if ais_msg['msgtype'] in IGNORED_TYPES:
            return
        # Type 24 part A (name) and part B (callsign, dimensions) carry
        # different fields, so keep the latest of each part separately.
        key = (ais_msg['mmsi'], ais_msg['msgtype'], ais_msg.get('partno'))
        self.cache[key] = ais_msg

    def flush(self, now=None):
        if now is None:
            now = time.monotonic()
        msgs = []
        for (mmsi, msgtype, _partno), msg in self.cache.items():
            if msgtype in POSITION_TYPES:
                lon = round(msg.get('lon', 0), 6)
                lat = round(msg.get('lat', 0), 6)
                # A changed navigation status is worth sending even if the
                # position has not changed. Heading, course and speed are
                # not compared, since they drift even on a moored vessel.
                status = msg.get('status')
                last = self.last_sent_pos.get(mmsi)
                if last and last[:3] == (lon, lat, status) \
                        and (now - last[3]) < self.dedup_interval:
                    continue
                self.last_sent_pos[mmsi] = (lon, lat, status, now)
            msgs.append(msg)
        self.cache.clear()
        return msgs


def post_jsonais(url, output):
    """POST a jsonais output dict to the given URL. Returns the response."""
    post = json.dumps(output)
    r = requests.post(url, files={'jsonais': (None, post)}, timeout=30)
    return r


def next_send_time(now):
    return now + SEND_INTERVAL + random.uniform(0, 4)


class BatchSender:
    """Posts the cached messages to the server when the send interval has passed."""

    def __init__(self, cache, name, url, now):
        self.cache = cache
        self.name = name
        self.url = url
        self.next_send = next_send_time(now)

    def tick(self, now):
        if now < self.next_send:
            return
        self.next_send = next_send_time(now)
        msgs = self.cache.flush(now)
        if not msgs:
            return
        output = build_jsonais_batch(msgs, self.name)
        try:
            post_jsonais(self.url, output)
        except requests.exceptions.RequestException as e:
            print(e)


def udp_lines(sock, tick, timeout=IDLE_TIMEOUT):
    """Yield NMEA lines received on a UDP socket.

    Calls tick() after each packet and whenever no packet arrives within
    the timeout, so that timed work gets done even when the receiver is
    quiet.
    """
    sock.settimeout(timeout)
    while True:
        try:
            data = sock.recv(65535)
        except socket.timeout:
            tick()
            continue
        for line in data.decode('ascii', errors='replace').splitlines(keepends=True):
            yield line
        tick()


if __name__ == '__main__':
    from termcolor import colored
    import ais.stream
    from settings import URL, NAME

    IP = '127.0.0.1'
    PORT = 5000

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((IP, PORT))

    cache = AISCache()
    sender = BatchSender(cache, NAME, URL, time.monotonic())

    def tick():
        sender.tick(time.monotonic())

    for msg in ais.stream.decode(udp_lines(sock, tick), keep_nmea=True):
        parsed = json.loads(json.dumps(msg))
        cache.add(parsed_to_ais_msg(parsed))
