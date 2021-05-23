#!/usr/bin/python3 -B
#coding: UTF-8
import json, memcache
mc = memcache.Client(["127.0.0.1:11211"])
metrics = mc.get('metrics')
metrics = json.loads(metrics)
help = {
    'custom.traf_from': {'title': 'Traffic: to metro', 'key': 'traf_from'},
    'custom.traf_to': {'title': 'Traffic: home', 'key': 'traf_to'},

    'sensors.t_in': {'title': 'Temperature inside', 'key': 't_in'},
    'sensors.t_out': {'title': 'Temperature outside', 'key': 't_out'},
    'sensors.h_in': {'title': 'Humidity inside', 'key': 'h_in'},
    'sensors.h_out': {'title': 'Humidity outside', 'key': 'h_out'},
    'sensors.light': {'title': 'Light level', 'key': 'light'},
    'sensors.pr_mBar': {'title': 'Pressure in mBar', 'key': 'pr_mBar'},
    'sensors.pr_temp': {'title': 'Temperature from pressure sensor', 'key': 'pr_temp'},
    'sensors.co2_ppm': {'title': 'CO2 PPM', 'key': 'co2_ppm'},
    'sensors.co2_s1': {'title': 'CO2 debug - S1', 'key': 'co2_s1'},
    'sensors.co2_s2': {'title': 'CO2 debug - S1', 'key': 'co2_s2'},
    'sensors.co2_s3': {'title': 'CO2 debug - S1', 'key': 'co2_s3'},
    'sensors.co2_abc': {'title': 'CO2 debug - ABC', 'key': 'co2_abc'},
    'sensors.uptime_01': {'title': 'Uptime ESP01', 'key': 'uptime'},
    'sensors.uptime_02': {'title': 'Uptime ESP02', 'key': 'uptime_02'},
    'sensors.esp01_fail': {'title': 'ESP01 error', 'key': 'esp01_fail'},
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

for deviceId in metrics['devices']:
    for devField in metrics['devices'][deviceId]:
        if devField == 'update' or devField == 'action' or devField == 'click':
            continue
        metricname = 'st_' + devField
        metricVal = metrics['devices'][deviceId][devField]
        print('# TYPE {0} gauge'.format(metricname))
        print('{0}{{sensor="{1}"}} {2}'.format(metricname, deviceId, metricVal))
