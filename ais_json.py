#!/usr/bin/python

import warnings
warnings.simplefilter(action='ignore', category=FutureWarning)
import json
import datetime
import requests


def parsed_to_jsonais(parsed, name, url, rxtime=None):
    """Convert a parsed AIS message dict to a jsonais output dict."""
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

    path = {
            "name": name,
            "url": url }

    groups = {
            "path": [path],
            "msgs": [ais_msg] }

    output = {
            "encodetime": rxtime,
            "protocol": 'jsonais',
            "groups": [groups]
            }

    return output


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

    while True:
      for msg in ais.stream.decode(sock.makefile('r'), keep_nmea=True):
        parsed = json.loads(json.dumps(msg))
        output = parsed_to_jsonais(parsed, NAME, URL)

        try:
          r = post_jsonais(URL, output)
          #dump non common packets for debugging
          if parsed['id'] not in (1, 2, 3, 4):
            print(colored('-- Uncommon packet recieved\n', 'red'))
            print(colored('id:', 'green'), parsed['id'])
            print(colored('NMEA:', 'green'), parsed['nmea'])
            print(colored('Parsed:', 'green'), parsed)
            print(colored('Post:', 'green'), json.dumps(output))
            print(colored('Result:', 'green'), json.loads(r.text)['description'])
        except requests.exceptions.RequestException as e:
          print(e)
