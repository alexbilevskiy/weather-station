#!/usr/bin/python3 -B
# coding: UTF-8
import paho.mqtt.client as mqtt
import memcache
import re
import json
import traceback

class listener():

    def __init__(self):
        self.client = mqtt.Client("zigbee-listener")
        self.client.on_log = self.on_log
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        
        self.mc = memcache.Client(["127.0.0.1:11211"])
        
        self.devices = {}
        
    def on_log(self, mqttc, obj, level, string):
        if level == mqtt.MQTT_LOG_DEBUG:
            return
        print('LOG: ' + str(level) + ', '+ str(string))

    def on_connect(self, client, userdata, flags, rc):
        print("Connected with result code "+str(rc))
        client.subscribe("zigbee2mqtt/#")
        client.publish('zigbee2mqtt/bridge/config/devices/get')

    def on_message(self, client, userdata, msg):
        if msg.payload == '' or msg.payload is None or msg.payload == b'':
            print('empty payload for ' + str(msg.topic))
            return
        if msg.topic == 'zigbee2mqtt/bridge/log' or msg.topic == 'zigbee2mqtt/bridge/logging' or msg.topic == 'zigbee2mqtt/bridge/groups' or msg.topic == 'zigbee2mqtt/bridge/info':
            return

        try:
            pl = json.loads(msg.payload)
        except:
            print('invalid payload for ' + str(msg.topic) + ': ' + str(msg.payload))
            traceback.print_exc()
            return

        if msg.topic == 'zigbee2mqtt/bridge/config/devices':
            print('devices: ' + str(msg.payload))
            for d in pl:
                if(d['friendly_name'] == 'Coordinator'):
                    continue
                self.devices[d['ieeeAddr']] = d
                print('query dev ' + d['friendly_name'])
                client.publish('zigbee2mqtt/{0}/get'.format(d['friendly_name']), '{"state":""}')
            self.mc.set('zigbee-devices', json.dumps(self.devices), 86400)
            return

        dev = re.match('zigbee2mqtt/(0x\w+)', msg.topic)
        if dev:
            devid = dev.group(1)
            if not 'state' in pl or pl['state'] == '':
                return
            print('received state for dev ' + str(devid) + ': ' + str(msg.payload))
            self.devices = json.loads(self.mc.get('zigbee-devices'))
            self.devices[devid]['state'] = pl
            self.mc.set('zigbee-devices', json.dumps(self.devices), 86400)

            return
        print('unknown topic ' + msg.topic + " " + str(msg.payload))

    def run(self):
        self.client.connect("localhost", 1883, 60)
        self.client.loop_forever()

l = listener()
l.run()