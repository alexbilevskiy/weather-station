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

    'yandex.fact.feels_like': {'title': 'Yandex temperature feels like', 'key': 't_ya_feel'},
    'yandex.fact.temp': {'title': 'Yandex real temperature', 'key': 't_ya_real'},
    'yandex.fact.condition': {'title': 'Yandex weather condition', 'key': 'ya_condition', "name_as_key": True},
    'yandex.fact.icon': {'title': 'Yandex weather icon', 'key': 'ya_icon', "name_as_key": True},
    'yandex.fact.wind_dir': {'title': 'Yandex wind direction', 'key': 'ya_w_direction', "name_as_key": True},
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

excludedFiels = [
    'update_available',
    'action',
    'click',
    'power_on_behavior',
    'switch_type',
    'sensitivity',
    'indicator_mode',
    'power_outage_memory',
    'volume',
    'self_test',
    'cli'
]
types = []
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

        if metricname not in types:
            print('# TYPE {0} gauge'.format(metricname))
            types.append(metricname)
        if type(metricVal) != dict:
            if name:
                print('{0}{{sensor="{1}", name="{2}"}} {3}'.format(metricname, deviceId, name, metricVal))
            else:
                print('{0}{{sensor="{1}"}} {2}'.format(metricname, deviceId, metricVal))
        else:
            for subKey in metricVal:
                if name:
                    print('{0}{{sensor="{1}", subid="{2}" name="{3}"}} {4}'.format(metricname, deviceId, subKey, name, metricVal[subKey]))
                else:
                    print('{0}{{sensor="{1}", subid="{2}"}} {3}'.format(metricname, deviceId, subKey, metricVal[subKey]))

