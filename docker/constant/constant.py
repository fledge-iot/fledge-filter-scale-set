"""Test-only south plugin: emits one reading per poll with fixed datapoint values,
so the effect of each scale-set factor is easy to check."""

import copy
from datetime import datetime, timezone

_DEFAULT_CONFIG = {
    'plugin': {
        'description': 'Constant test readings',
        'type': 'string',
        'default': 'constant',
        'readonly': 'true'
    },
    'assetName': {
        'description': 'Asset name',
        'type': 'string',
        'default': 'asd',
        'displayName': 'Asset Name',
        'order': '1'
    }
}


def plugin_info():
    return {
        'name': 'constant',
        'version': '1.0.0',
        'mode': 'poll',
        'type': 'south',
        'interface': '1.0',
        'config': _DEFAULT_CONFIG
    }


def plugin_init(config):
    return copy.deepcopy(config)


def plugin_poll(handle):
    return {
        'asset': handle['assetName']['value'],
        'timestamp': datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S.%f+00:00'),
        'readings': {'temp': 10, 'humidity': 20}
    }


def plugin_reconfigure(handle, new_config):
    return copy.deepcopy(new_config)


def plugin_shutdown(handle):
    pass
