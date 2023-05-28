#!/usr/bin/python3 -B
# coding: UTF-8
import time, datetime, json, memcache, requests

class exporter:
    def __init__(self):
        self.metrics_devt = []
        self.metrics_dev = {}
        self.metrics = {
            'custom': {
                'traf_from': None,
                'traf_to': None,
                'traf_updated': None,
            },
            'yandex': {
                'radar': {},
                'updated': None,
            },
        }
        self.mc = memcache.Client(["127.0.0.1:11211"])
        with open('../config.json') as f: s = f.read()
        self.config = json.loads(s)

    def run(self):
        print('starting')
        existing = self.mc.get('metrics')
        if existing:
            print('loaded existing metrics')
            self.metrics = json.loads(existing)

        while True:
            self.readYandex()
            self.readTraffic()
            self.mc.set('metrics', json.dumps(self.metrics), 300)
            time.sleep(0.5)

    def readTraffic(self):
        cacheKey = 'yandex-traffic'
        tr = self.mc.get(cacheKey)
        if tr:
            tr = json.loads(tr)
        else:
            now = datetime.datetime.now()
            date = now.strftime("%Y-%m-%d %H:%M:%S")
            url = self.config['traffic_url']
            try:
                resp = requests.get(url, timeout=10)
            except Exception as e:
                print(date + ' traffic error: ' + str(e))
                return
            tr = resp.json()
            if not ('from' in tr) or not('value' in tr['from']):
                print(date + ' bad traff resp: ' + resp.text)
                return
            self.metrics['custom']['traf_updated'] = int(now.strftime("%s"))
            self.mc.set(cacheKey, json.dumps(tr), 120)

        try:
            self.metrics['custom']['traf_from'] = tr['from']['value']
            self.metrics['custom']['traf_to'] = tr['to']['value']
        except Exception as e:
            print("Traf error " + str(e) + " " + str(tr))
            self.metrics['custom']['traf_from'] = 0
            self.metrics['custom']['traf_to'] = 0

    def readYandex(self):
        cacheKeyRadar = 'yandex-weather-radar'
        r = self.mc.get(cacheKeyRadar)
        if r:
            cur = json.loads(r)
        else:
            try:
                url = self.config['yandex_radar_url']
                resp = requests.get(url)
                cur = resp.json()
                self.mc.set(cacheKeyRadar, json.dumps(cur), 120)
            except Exception as e:
                print('yandex current error: `{0}`'.format(str(e)))
                return self.metrics
            if not cur or 'alert' not in cur or 'current' not in cur['alert']:
                print('yandex radar bad response: ' + str(resp.text.encode('utf-8')))
                return self.metrics
            print("Prec strength: {0}".format(cur['alert']['strength']))

        if not cur or 'alert' not in cur or 'current' not in cur['alert']:
            print('yandex radar bad cached: ' + str(cur))
            return self.metrics
        self.metrics['yandex']['radar'] = cur['alert']

        return self.metrics

if __name__ == "__main__":
    exporter = exporter()
    exporter.run()
