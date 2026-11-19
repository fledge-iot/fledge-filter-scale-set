#!/usr/bin/env python3
"""Reproduces the scale-set restart issue against the Fledge in this container.

South service "asd" emits temp=10, humidity=20. Filter "temp" (category asd_temp)
gets two per-datapoint factors:
    temp     * 2.0 + 0    -> expect 20
    humidity * 1.0 + 100  -> expect 120
If datapoint matching is ignored, every factor hits every datapoint and the
values come out as temp=120, humidity=140.

The factors are first applied to the running service (reconfigure path), then
the service is restarted (plugin_init path). Both must give the expected values.
"""
import glob
import os
import json
import sys
import time
import urllib.error
import urllib.request

BASE = 'http://localhost:8081/fledge'
SERVICE = 'asd'
FILTER = 'temp'
FACTORS = {'factors': [
    {'asset': 'asd', 'datapoint': 'temp', 'scale': '2.0', 'offset': '0.0'},
    {'asset': 'asd', 'datapoint': 'humidity', 'scale': '1.0', 'offset': '100.0'},
]}
EXPECTED = {'temp': 20, 'humidity': 120}
TOKEN = None  # set by login(); default credentials of a fresh test install
ASAN_LOGS = '/var/log/asan/asan.*'  # only written in ASan builds


def call(method, path, body=None, ok_missing=False):
    data = json.dumps(body).encode() if body is not None else None
    headers = {'Content-Type': 'application/json'}
    if TOKEN:
        headers['Authorization'] = TOKEN
    req = urllib.request.Request(BASE + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            text = resp.read().decode()
            return json.loads(text) if text else None
    except urllib.error.HTTPError as e:
        if ok_missing and e.code in (404, 400):
            return None
        raise SystemExit(f'{method} {path} -> {e.code}: {e.read().decode()}')


def asan_check():
    """Fail immediately if AddressSanitizer reported an error in the south service."""
    logs = glob.glob(ASAN_LOGS)
    if logs:
        print('  AddressSanitizer report -> FAIL')
        for path in logs:
            with open(path) as f:
                print('    ' + '\n    '.join(f.read().splitlines()[:40]))
        sys.exit(1)


def wait_for(cond, timeout, what):
    end = time.time() + timeout
    while time.time() < end:
        asan_check()
        try:
            if cond():
                return
        except Exception:
            pass
        time.sleep(1)
    raise SystemExit(f'Timed out waiting for {what}')


def latest():
    rows = call('GET', f'/asset/{SERVICE}?limit=1', ok_missing=True) or []
    return rows[0] if rows else None


def fresh_reading(after_ts):
    """Wait for a reading newer than after_ts, then let a few more arrive."""
    wait_for(lambda: (r := latest()) and r['timestamp'] > after_ts, 60, 'new readings')
    time.sleep(3)
    return latest()


def check(label, row):
    values = {k: row['reading'].get(k) for k in EXPECTED}
    good = all(abs(float(values[k]) - v) < 1e-6 for k, v in EXPECTED.items())
    asan_check()
    print(f'  {label:<22} {values}  expected {EXPECTED}  -> {"PASS" if good else "FAIL"}')
    return good


def service_running():
    svcs = call('GET', '/service')['services']
    return any(s['name'] == SERVICE and s['status'] == 'running' for s in svcs)


def main():
    global TOKEN
    wait_for(lambda: call('GET', '/ping'), 120, 'Fledge API')
    TOKEN = call('POST', '/login', {'username': 'admin', 'password': 'fledge'})['token']

    # Clean slate so the script can be rerun.
    for path in glob.glob(ASAN_LOGS):
        os.remove(path)
    call('DELETE', f'/service/{SERVICE}', ok_missing=True)
    call('DELETE', f'/filter/{FILTER}', ok_missing=True)
    call('DELETE', f'/asset/{SERVICE}', ok_missing=True)

    call('POST', '/service', {'name': SERVICE, 'type': 'south', 'plugin': 'constant', 'enabled': True})
    call('POST', '/filter', {'name': FILTER, 'plugin': 'scale-set', 'filter_config': {'enable': 'true'}})
    call('PUT', f'/filter/{SERVICE}/pipeline?allow_duplicates=true&append_filter=true', {'pipeline': [FILTER]})
    wait_for(service_running, 60, 'south service to start')
    ts = fresh_reading('')['timestamp']

    # 1. Apply factors to the running service (plugin_reconfigure).
    category = f'{SERVICE}_{FILTER}'
    if call('GET', f'/category/{category}', ok_missing=True) is None:
        category = FILTER
    call('PUT', f'/category/{category}/factors', {'value': json.dumps(FACTORS)})
    print(f'Filter category: {category}')
    print('Factors:', json.dumps(FACTORS['factors']))
    live_ok = check('live reconfigure', fresh_reading(ts))

    # 2. Restart the south service (plugin_init with the stored config).
    ts = latest()['timestamp']
    call('PUT', '/schedule/disable', {'schedule_name': SERVICE})
    wait_for(lambda: not service_running(), 60, 'south service to stop')
    time.sleep(2)
    call('PUT', '/schedule/enable', {'schedule_name': SERVICE})
    wait_for(service_running, 60, 'south service to restart')
    restart_ok = check('after restart', fresh_reading(ts))

    sys.exit(0 if live_ok and restart_ok else 1)


if __name__ == '__main__':
    main()
