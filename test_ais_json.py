from unittest.mock import patch, MagicMock
from ais_json import parsed_to_jsonais, parsed_to_ais_msg, build_jsonais_batch, post_jsonais, AISCache


def test_parsed_to_jsonais_position_report():
    parsed = {
        'id': 1,
        'mmsi': 211234567,
        'x': 24.9384,
        'y': 60.1699,
        'sog': 12.3,
        'cog': 45.6,
        'true_heading': 47,
        'nav_status': 0,
    }

    output = parsed_to_jsonais(parsed, 'TestStation', 'http://example.com/post', rxtime='20260223120000')

    assert output['protocol'] == 'jsonais'
    assert output['encodetime'] == '20260223120000'
    assert len(output['groups']) == 1

    group = output['groups'][0]
    assert group['path'] == [{'name': 'TestStation', 'url': 'http://example.com/post'}]

    msg = group['msgs'][0]
    assert msg['msgtype'] == 1
    assert msg['mmsi'] == 211234567
    assert msg['lon'] == 24.9384
    assert msg['lat'] == 60.1699
    assert msg['speed'] == 12.3
    assert msg['course'] == 45.6
    assert msg['heading'] == 47
    assert msg['status'] == 0
    assert msg['rxtime'] == '20260223120000'


def test_parsed_to_jsonais_minimal():
    parsed = {'id': 5, 'mmsi': 123456789}

    output = parsed_to_jsonais(parsed, 'Sta', 'http://x.com', rxtime='20260101000000')

    msg = output['groups'][0]['msgs'][0]
    assert msg['msgtype'] == 5
    assert msg['mmsi'] == 123456789
    assert 'lon' not in msg
    assert 'lat' not in msg


def test_parsed_to_jsonais_static_fields():
    parsed = {
        'id': 5,
        'mmsi': 123456789,
        'callsign': 'ABCD',
        'name': 'TESTSHIP',
        'type_and_cargo': 70,
        'dim_a': 100,
        'dim_c': 10,
        'draught': 5.5,
        'destination': 'HELSINKI',
    }

    output = parsed_to_jsonais(parsed, 'Sta', 'http://x.com', rxtime='20260101000000')
    msg = output['groups'][0]['msgs'][0]

    assert msg['callsign'] == 'ABCD'
    assert msg['shipname'] == 'TESTSHIP'
    assert msg['shiptype'] == 70
    assert msg['ref_front'] == 100
    assert msg['ref_left'] == 10
    assert msg['draught'] == 5.5
    assert msg['destination'] == 'HELSINKI'


@patch('ais_json.requests.post')
def test_post_jsonais(mock_post):
    mock_post.return_value = MagicMock(status_code=200)

    output = {'protocol': 'jsonais', 'groups': []}
    r = post_jsonais('http://example.com/post', output)

    mock_post.assert_called_once()
    call_args = mock_post.call_args
    assert call_args[0][0] == 'http://example.com/post'
    assert 'jsonais' in call_args[1]['files']
    assert r.status_code == 200


def test_parsed_to_ais_msg():
    parsed = {
        'id': 1,
        'mmsi': 211234567,
        'x': 24.9384,
        'y': 60.1699,
        'sog': 12.3,
        'cog': 45.6,
        'true_heading': 47,
        'nav_status': 0,
    }

    msg = parsed_to_ais_msg(parsed, rxtime='20260223120000')

    assert msg['msgtype'] == 1
    assert msg['mmsi'] == 211234567
    assert msg['lon'] == 24.9384
    assert msg['lat'] == 60.1699
    assert msg['speed'] == 12.3
    assert msg['course'] == 45.6
    assert msg['heading'] == 47
    assert msg['status'] == 0
    assert msg['rxtime'] == '20260223120000'


def test_build_jsonais_batch():
    msgs = [
        {'msgtype': 1, 'mmsi': 111, 'rxtime': '20260101000000'},
        {'msgtype': 5, 'mmsi': 222, 'rxtime': '20260101000000'},
    ]

    output = build_jsonais_batch(msgs, 'TestStation', 'http://example.com/post', rxtime='20260101000000')

    assert output['protocol'] == 'jsonais'
    assert output['encodetime'] == '20260101000000'
    group = output['groups'][0]
    assert group['path'] == [{'name': 'TestStation', 'url': 'http://example.com/post'}]
    assert group['msgs'] == msgs
    assert len(group['msgs']) == 2


def test_cache_keeps_latest_per_mmsi_and_type():
    cache = AISCache()
    cache.add({'mmsi': 111, 'msgtype': 1, 'lon': 1.0, 'lat': 2.0, 'speed': 5.0})
    cache.add({'mmsi': 111, 'msgtype': 1, 'lon': 1.1, 'lat': 2.1, 'speed': 6.0})

    msgs = cache.flush(now=1000.0)

    assert len(msgs) == 1
    assert msgs[0]['lon'] == 1.1
    assert msgs[0]['speed'] == 6.0


def test_cache_position_dedup():
    cache = AISCache()

    cache.add({'mmsi': 111, 'msgtype': 1, 'lon': 1.0, 'lat': 2.0})
    msgs1 = cache.flush(now=1000.0)
    assert len(msgs1) == 1

    # Same position within 120s - should be deduplicated
    cache.add({'mmsi': 111, 'msgtype': 1, 'lon': 1.0, 'lat': 2.0})
    msgs2 = cache.flush(now=1050.0)
    assert len(msgs2) == 0


def test_cache_position_dedup_changed_position():
    cache = AISCache()

    cache.add({'mmsi': 111, 'msgtype': 1, 'lon': 1.0, 'lat': 2.0})
    cache.flush(now=1000.0)

    # Changed position within 120s - should pass through
    cache.add({'mmsi': 111, 'msgtype': 1, 'lon': 1.5, 'lat': 2.5})
    msgs = cache.flush(now=1050.0)
    assert len(msgs) == 1
    assert msgs[0]['lon'] == 1.5


def test_cache_position_dedup_expired():
    cache = AISCache()

    cache.add({'mmsi': 111, 'msgtype': 1, 'lon': 1.0, 'lat': 2.0})
    cache.flush(now=1000.0)

    # Same position but after 120s - should pass through
    cache.add({'mmsi': 111, 'msgtype': 1, 'lon': 1.0, 'lat': 2.0})
    msgs = cache.flush(now=1200.0)
    assert len(msgs) == 1
