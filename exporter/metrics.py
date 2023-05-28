#!/usr/bin/python3 -B
#coding: UTF-8
import json, memcache
mc = memcache.Client(["127.0.0.1:11211"])
metrics = mc.get('metrics')
metrics = json.loads(metrics)
help = {
    'custom.traf_from': {'title': 'Traffic: to metro', 'key': 'traf_from'},
    'custom.traf_to': {'title': 'Traffic: home', 'key': 'traf_to'},

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
    value = getNested(metrics, m)
    if value is None:
        continue
    metricname = 'arduino_' + help[m]['key']
    print('# HELP {0} {1}'.format(metricname, help[m]['title']))
    print('# TYPE {0} untyped'.format(metricname, help[m]['title']))
    if 'name_as_key' not in help[m]:
        print('{0} {1}'.format(metricname, value))
    else:
        print('{0}{{subname="{1}"}} {2}'.format(metricname, value, 1))
