#!/usr/bin/python3 -B
#coding: UTF-8
import json, memcache
mc = memcache.Client(["127.0.0.1:11211"])
metrics = mc.get('metrics')
metrics = json.loads(metrics)
help = {
    'custom.traf_from': {'title': 'Traffic: to metro', 'key': 'traf_from'},
    'custom.traf_to': {'title': 'Traffic: home', 'key': 'traf_to'},
    'custom.day_length': {'title': 'Day lenngth', 'key': 'day_length'},
    'custom.day_percent': {'title': 'Day percent', 'key': 'day_percent'},

    'sensors.uptime_02': {'title': 'Uptime ESP02', 'key': 'uptime_02'},
    'sensors.esp02_fail': {'title': 'ESP02 error', 'key': 'esp02_fail'},
    'sensors.lag': {'title': 'Metrics lag', 'key': 'lag'},
    'sensors.size': {'title': 'Metrics size', 'key': 'size'},

    'yandex.fact.feels_like': {'title': 'Yandex temperature feels like', 'key': 't_ya_feel'},
    'yandex.fact.temp': {'title': 'Yandex real temperature', 'key': 't_ya_real'},
    'yandex.fact.humidity': {'title': 'Yandex humidity real', 'key': 'h_ya'},
    'yandex.fact.pressure_pa': {'title': 'Yandex pressure in mBar', 'key': 'pr_ya_pa'},
    'yandex.fact.wind_speed': {'title': 'Yandex wind speed m/s', 'key': 'ya_w_speed'},
    'yandex.radar.current.prec_strength': {'title': 'Precipitation strength', 'key': 'prec_strength'},
    'yandex.radar.current.prec_type': {'title': 'Precipitation type', 'key': 'prec_type'},
    'yandex.radar.current.cloudness': {'title': 'Cloudness', 'key': 'cloudness'},
}
print("Content-type: text/plain")
print('')

def getNested(metrics, key):
    keys = key.split('.')
    l = len(keys)
    if l == 1:
        return metrics[keys[0]]
    if l == 2:
        return metrics[keys[0]][keys[1]]
    if l == 3:
        return metrics[keys[0]][keys[1]][keys[2]]
    if l == 4:
        return metrics[keys[0]][keys[1]][keys[2]][keys[3]]


for m in help:
    metricname = 'arduino_' + help[m]['key']
    print('# HELP {0} {1}'.format(metricname, help[m]['title']))
    print('# TYPE {0} untyped'.format(metricname, help[m]['title']))
    print('{0} {1}'.format(metricname, getNested(metrics, m)))

excludedFiels = [
    'update',
    'action',
    'click',
    'power_on_behavior',
    'switch_type'
]
for deviceId in metrics['devices']:
    name = metrics['devices'][deviceId].pop('name', None)
    for devField in metrics['devices'][deviceId]:
        skip = False
        for f in excludedFiels:
            if devField.find(f) == 0:
                skip = True
        if skip:
            continue
        metricname = 'st_' + devField
        metricVal = metrics['devices'][deviceId][devField]
        if metricVal is None:
            continue
        if type(metricVal) == bool:
            metricVal = int(metricVal)
        print('# TYPE {0} gauge'.format(metricname))
        if name:
            print('{0}{{sensor="{1}", name="{2}"}} {3}'.format(metricname, deviceId, name, metricVal))
        else:
            print('{0}{{sensor="{1}"}} {2}'.format(metricname, deviceId, metricVal))
