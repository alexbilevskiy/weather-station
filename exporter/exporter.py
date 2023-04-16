#!/usr/bin/python3 -B
# coding: UTF-8
import time, datetime, os, json, memcache, random, requests, re
import paho.mqtt.client as mqtt

class exporter:
    def __init__(self):
        self.mqtt_connect()

        self.metrics_devt = []
        self.metrics_dev = {}
        self.metrics = {
            'custom': {
                'datetime': None,
                'utime': None,
                'traf_from': None,
                'traf_to': None,
                'traf_updated': None,
                'day_length': None,
                'day_percent': None,
            },
            'devices': {},
            'yandex': {
                'fact': {},
                'radar': {},
                'forecast': {},
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
            for i in range(1, 5):
                self.mqcl.loop(0)
            now = datetime.datetime.now()
            date = now.strftime("%Y-%m-%d %H:%M:%S")
            utime = int(now.strftime("%s"))
            self.metrics['custom']['datetime'] = date
            self.metrics['custom']['utime'] = utime


            # for devicekey in self.metrics['devices']:
            #     if 'updated' not in self.metrics['devices'][devicekey]:
            #         continue
            #     if self.metrics['devices'][devicekey]['updated'] < utime - 300:
            #         self.metrics['devices'].pop("device")
            #         print('would remove devie {0}'.format(devicekey))
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
        keys = self.config['yandex_weather_keys']
        cacheKey = 'yandex-weather'
        cacheKeyRadar = 'yandex-weather-radar'
        cacheKeyBad = 'yandex-weather-bad'
        w = self.mc.get(cacheKey)
        if self.mc.get(cacheKeyBad):
            print("weather broken")
            return self.metrics

        if w:
            w = json.loads(w)
        else:
            print("load weather")
            now = datetime.datetime.now()
            date = now.strftime("%Y-%m-%d %H:%M:%S")
            url = self.config['yandex_weather_url']
            headers = {'X-Yandex-API-Key': random.choice(keys)}
            try:
                resp = requests.get(url, headers=headers)
            except Exception as e:
                print(date + ' yandex errror: ' + str(e))
                return self.metrics
            w = resp.json()
            if not ('fact' in w):
                print(date + ' Bad yandex response: ' + resp.text)
                self.mc.set(cacheKeyBad, True, 300)
                return self.metrics

            print(date + ' yandex weather loaded')
            w['updated'] = int(now.strftime("%s"))
            self.mc.set(cacheKey, json.dumps(w), 1800)

        if type(w['forecast']['parts']) == dict:
            parts = []
            for partKey in w['forecast']['parts']:
                part = w['forecast']['parts'][partKey]
                part['part_name'] = partKey
                parts.append(part)
            w['forecast']['parts'] = parts

        self.metrics['yandex']['fact'] = w['fact']
        self.metrics['yandex']['forecast'] = w['forecast']
        self.metrics['yandex']['updated'] = w['updated']

        for f in w['forecast']['parts']:
            p = self.config['icons_path']
            icon = p + f['icon'] + '.png'
            if os.path.isfile(icon):
                continue
            print('loading icon ' + f['icon'])
            url = self.config['icons_url_format'].format(f['icon'])
            resp = requests.get(url, timeout=5)
            f = open(icon, 'wb')
            f.write(resp.content)
            f.close()
            print('loaded icon ' + icon)

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

        sr = datetime.datetime.strptime(w['forecast']['sunrise'], '%H:%M')
        ss = datetime.datetime.strptime(w['forecast']['sunset'], '%H:%M')
        dayLen = (ss-sr).total_seconds()
        curTime = datetime.datetime.strptime(datetime.datetime.now().strftime('%H:%M'), '%H:%M')
        perc = (curTime-sr).total_seconds() / dayLen

        self.metrics['custom']['day_length'] = dayLen
        self.metrics['custom']['day_percent'] = perc

        return self.metrics

    def readZigbee(self, topic, data):
        for f in data:
            if f.find('state') == 0:
                data[f] = self.convertState(data[f])

        try:
            data.pop('update')
            data.pop('update_available')
        except:
            pass
        self.metrics['devices'][topic] = data
        self.metrics['devices'][topic]['updated'] = self.metrics['custom']['utime']

    def readR4sValue(self, deviceId, field, value):
        if field == 'nightlight_rgb' or field == 'rgb' or field == 'ip' or field == 'st_jpg_url' or field == 'st_jpg_url':
            return
        if type(value) == int:
            # nothing to do
            pass
        elif type(value) == bytes:
            value = value.decode('utf-8')

        if field == 'total_energy':
            value = float(value)
        elif field == 'working_time':
            h, m, s = map(int, value.split(':'))
            value = h * 3600 + m * 60 + s

        if type(value) == str:
            if value.isdigit():
                value = int(value)
            elif is_float(value):
                value = float(value)
            else:
                if re.match('^-?\d+$', value):
                    value = int(value)
                elif re.match('^on(line)?$', value, flags=re.IGNORECASE):
                    value = 1
                elif re.match('^off(line)?$', value, flags=re.IGNORECASE):
                    value = 0

        # print("R4S DEVICE {0}: {1} [{2}]".format(deviceId, field, value))
        if deviceId not in self.metrics['devices']:
            self.metrics['devices'][deviceId] = {}
        self.metrics['devices'][deviceId][field] = value

    def convertState(self, value):
        if value == 'ON':
            return 1
        return 0

    def mqtt_connect(self):
        print("Connecting mqtt")
        self.mqcl = mqtt.Client("exporter")
        self.mqcl.enable_logger()
        self.mqcl.on_connect = self.mqtt_connected
        self.mqcl.on_message = self.mqtt_message
        self.mqcl.on_disconnect = self.mqtt_disconnected
        self.mqcl.connect("localhost", 1883, 60)

    def mqtt_connected(self, client, userdata, flags, rc):
        print("Connected with result code "+str(rc))
        self.mqcl.subscribe('wifi2mqtt/#')
        self.mqcl.subscribe('zigbee2mqtt/#')
        self.mqcl.subscribe('r4s/#')
        self.mqcl.subscribe('r4s0/#')
        self.mqcl.subscribe('r4s1/#')

    def mqtt_disconnected(self, client, rc):
        print("Disconnected with result code " + str(rc))
        self.mqtt_connect()

    def mqtt_message(self, client, userdata, msg):
        m = re.match('.*?wifi2mqtt/(\w+)$', msg.topic)
        if m:
            try:
                data = json.loads(msg.payload)
            except Exception as e:
                print("Failed to decode {0} `{1}`: {2}".format(msg.topic, str(msg.payload), str(e)))
                return
            self.readZigbee(m.group(1), data)
            return

        m = re.match('.*?zigbee2mqtt/(\w+)$', msg.topic)
        if m:
            data = json.loads(msg.payload)
            self.readZigbee(m.group(1), data)
            return

        # r4s/f4ad35a94031/rssi
        # r4s/f4ad35a94031/rsp/json
        m = re.match('^r4s\d*/(\w+?)/(?:rsp/)?(\w+)$', msg.topic)
        if m:
            if m.group(2) == 'json':
                data = json.loads(msg.payload)
                for field in data:
                    self.readR4sValue(m.group(1), field, data[field])
                return
            self.readR4sValue(m.group(1), m.group(2), msg.payload)
            return
        m = re.match('^r4s0/(\w+?)$', msg.topic)
        if m:
            self.readR4sValue("r4sgate", m.group(1), msg.payload)
            return
        m = re.match('^r4s1/(\w+?)$', msg.topic)
        if m:
            self.readR4sValue("r4sgate1", m.group(1), msg.payload)
            return
        #print('MQTT SKIP: ' + "\t" + str(msg.topic) + "\t" + str(msg.payload))


def is_float(value):
    if value is None:
        return False
    try:
        float(value)
        return True
    except:
        return False

if __name__ == "__main__":
    exporter = exporter()
    exporter.run()
