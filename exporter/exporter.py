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
            'sensors': {
                't_in': None,
                't_out': None,
                'h_in': None,
                'h_out': None,
                'light': None,
                'light_updated': None,
                'pr_mBar': None,
                'pr_mmHg': None,
                'pr_temp': None,
                'co2_ppm': None,
                'co2_ppm_cm11': None,
                'co2_temp': None,
                'uptime_01': None,
                'uptime_02': None,
                'esp01_fail': 0,
                'esp01_updated': 0,
                'esp02_fail': 0,
                'esp02_updated': 0,
                'esp_air_02_fail': 0,
                'size': 0,
                'lag': 0,
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

            self.metrics['sensors']['esp01_fail'] = 0
            self.metrics['sensors']['esp02_fail'] = 0
            try:
                self.metrics['sensors']['esp01_updated']
                if self.metrics['sensors']['esp01_updated'] < self.metrics['custom']['utime'] - 60:
                    self.metrics['sensors']['esp01_fail'] = 1
                    self.metrics['devices']['ESP_weather']['state'] = 0
            except:
                self.metrics['sensors']['esp01_fail'] = 1
            try:
                self.metrics['sensors']['esp02_updated']
                if self.metrics['sensors']['esp02_updated'] < self.metrics['custom']['utime'] - 60:
                    self.metrics['sensors']['esp02_fail'] = 1
                    self.metrics['devices']['ESP_air']['state'] = 0
            except:
                self.metrics['sensors']['esp02_fail'] = 1

            self.readYandex()
            self.readTraffic()
            self.mc.set('metrics', json.dumps(self.metrics), 300)
            time.sleep(0.5)

    def readEsp01(self, esp_data):
        temp = {
            't_out': {'v': 0, 't': 'float'},
            'h_out': {'v': 0, 't': 'float'},
            'light': {'v': 0, 't': 'int'},
            'pr_mBar': {'v': 0, 't': 'float'},
            'pr_temp': {'v': 0, 't': 'float'}
        }
        try:
            temp['t_out']['v'] = esp_data['dht22_temp']
            temp['h_out']['v'] = esp_data['dht22_humidity']
            temp['light']['v'] = esp_data['light']
            temp['pr_mBar']['v'] = esp_data['bmp180_pressure']
            temp['pr_temp']['v'] = esp_data['bmp180_temp']
            uptime = esp_data['uptime']
        except Exception as e:
            print('Bad rcv unpacked 01: ' + str(esp_data) + ', ' + str(e))
            self.metrics['sensors']['esp01_fail'] = 1
            self.metrics['devices']['ESP_weather']['state'] = 0
            return False
        try:
            for name in temp:
                temp[name]['v'] = self.normalize(name, temp[name]['v'], temp[name]['t'])
        except ValueError:
            print('Cant convert some variables ' + str(esp_data))
            self.metrics['sensors']['esp01_fail'] = 1
            self.metrics['devices']['ESP_weather']['state'] = 0
            return False
        if self.metrics['sensors']['light'] != temp['light']['v']:
            self.metrics['sensors']['light_updated'] = self.metrics['custom']['utime']
        for name in temp:
            self.metrics['sensors'][name] = temp[name]['v']
        self.metrics['sensors']['esp01_updated'] = self.metrics['custom']['utime']
        self.metrics['sensors']['uptime_01'] = uptime

        self.metrics['sensors']['esp01_fail'] = 0
        return self.metrics

    def readEsp02(self, esp_data):
        temp = {
            't_in': {'v': 0, 't': 'float'},
            'h_in': {'v': 0, 't': 'float'},
            'co2_ppm': {'v': 0, 't': 'float'},
            'co2_s1': {'v': 0, 't': 'fixed'},
            'co2_s2': {'v': 0, 't': 'fixed'},
            'co2_s3': {'v': 0, 't': 'fixed'},
            'co2_abc': {'v': 0, 't': 'fixed'}
        }
        try:
            temp['t_in']['v'] = esp_data['dht22_temp']
            temp['h_in']['v'] = esp_data['dht22_humidity']
            temp['co2_ppm']['v'] = esp_data['co2_ppm']
            temp['co2_s1']['v'] = esp_data['co2_s1']
            temp['co2_s2']['v'] = esp_data['co2_s2']
            temp['co2_s3']['v'] = esp_data['co2_s3']
            temp['co2_abc']['v'] = esp_data['co2_abc']
            uptime = esp_data['uptime']
        except Exception as e:
            print('Bad rcv unpacked 02: ' + str(esp_data) + ' ' + str(e))
            self.metrics['sensors']['esp02_fail'] = 1
            self.metrics['devices']['ESP_air']['state'] = 0
            return False
        try:
            for name in temp:
                temp[name]['v'] = self.normalize(name, temp[name]['v'], temp[name]['t'])
        except ValueError as e:
            print('Cant convert some variables ' + str(esp_data) + ', ' + str(e))
            self.metrics['sensors']['esp02_fail'] = 1
            self.metrics['devices']['ESP_air']['state'] = 0
            return False
        for name in temp:
            self.metrics['sensors'][name] = temp[name]['v']
        self.metrics['sensors']['esp02_updated'] = self.metrics['custom']['utime']
        self.metrics['sensors']['uptime_02'] = uptime
        self.metrics['sensors']['esp02_fail'] = 0
        return self.metrics

    def readEspAir02(self, esp_data):
        temp = {
            'co2_ppm_cm11': {'v': 0, 't': 'float'},
        }
        try:
            temp['co2_ppm_cm11']['v'] = esp_data['co2_ppm']
        except Exception as e:
            print('Bad rcv unpacked 02: ' + str(esp_data) + ' ' + str(e))
            self.metrics['sensors']['esp_air_02_fail'] = 1
            #self.metrics['devices']['ESP_air_02']['state'] = 0
            return False
        try:
            for name in temp:
                temp[name]['v'] = self.normalize(name, temp[name]['v'], temp[name]['t'])
        except ValueError as e:
            print('Cant convert some variables ' + str(esp_data) + ', ' + str(e))
            self.metrics['sensors']['esp_air_02_fail'] = 1
            return False
        for name in temp:
            self.metrics['sensors'][name] = temp[name]['v']
        self.metrics['sensors']['esp_air_02_fail'] = 0
        return self.metrics

    def normalize(self, name, val, paramType ='float'):
        if name not in self.metrics_dev:
            self.metrics_dev[name] = []

        if paramType == 'int':
            val = int(val)
        elif paramType == 'float':
            val = float(val)

        self.metrics_devt.append(self.metrics['custom']['utime'])
        self.metrics_dev[name].append(val)
        if len(self.metrics_dev[name]) > self.config['sensors_moving_avg_limit']:
            self.metrics_dev[name].pop(0)
            self.metrics_devt.pop(0)
        self.metrics['sensors']['size'] = len(self.metrics_dev[name])
        self.metrics['sensors']['lag'] = self.metrics['custom']['utime'] - self.metrics_devt[0]

        if paramType == 'int':
            val = int(round(sum(self.metrics_dev[name])/len(self.metrics_dev[name]), 0))
        elif paramType == 'float':
            val = round(sum(self.metrics_dev[name])/len(self.metrics_dev[name]), 1)

        return val

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
        stateFields = ['state', 'state_left', 'state_right']
        for f in stateFields:
            try:
                data[f] = self.convertState(data[f])
            except:
                pass

        try:
            data.pop('update')
            data.pop('update_available')
        except:
            pass
        self.metrics['devices'][topic] = data
        self.metrics['devices'][topic]['updated'] = self.metrics['custom']['utime']

    def readR4sValue(self, deviceId, field, value):
        # if deviceId not in self.metrics['devices']:
        #     self.metrics['devices'][deviceId] = {}
        # self.metrics['devices'][deviceId][field] = value
        print("R4S DEVICE {0}: {1} [{2}]".format(deviceId, field, value))

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

    def mqtt_disconnected(self, client, userdata, rc):
        print("Disconnected with result code " + str(rc))
        self.mqtt_connect()

    def mqtt_message(self, client, userdata, msg):
        m = re.match('.*?wifi2mqtt/(\w+)$', msg.topic)
        if m:
            data = json.loads(msg.payload)
            self.readZigbee(m.group(1), data)
            if m.group(1) == 'ESP_air':
                self.readEsp02(data)
            elif m.group(1) == 'ESP_air_02':
                self.readEspAir02(data)
            elif m.group(1) == 'ESP_weather':
                self.readEsp01(data)
            return

        m = re.match('.*?zigbee2mqtt/(\w+)$', msg.topic)
        if m:
            data = json.loads(msg.payload)
            self.readZigbee(m.group(1), data)
            return

        m = re.match('^r4s/(\w+?)/rsp/(\w+)$', msg.topic)
        if m:
            data = json.loads(msg.payload)
            self.readR4sValue(m.group(1), m.group(2), data)
            return
        m = re.match('^r4s/(\w+?)$', msg.topic)
        if m:
            data = json.loads(msg.payload)
            self.readR4sValue("r4sgate", m.group(1), data)
            return
        #print('MQTT SKIP: ' + "\t" + str(msg.topic) + "\t" + str(msg.payload))

if __name__ == "__main__":
    exporter = exporter()
    exporter.run()
