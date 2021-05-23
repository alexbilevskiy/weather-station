#!/usr/bin/python3 -B
#coding: UTF-8
import telegram, memcache, cgi, json, os, math

print("Content-type: text/plain")
print('')

arguments = cgi.FieldStorage()
devid = None
if 'id' in arguments:
    devid = arguments['id'].value

cmd = {'state':'OFF'}
if 'on' in arguments and bool(int(arguments['on'].value)):
    cmd['state'] = 'ON'
    
if 'brightness' in arguments:
    cmd['brightness'] = int(math.ceil(float(arguments['brightness'].value) / 100 * 255))
    cmd['state'] = 'ON'
    
cm = 'mosquitto_pub -t zigbee2mqtt/{0}/set -m \'{1}\''.format(devid, json.dumps(cmd))
print(cm)
if not devid:
    print('wont do')
else:
    os.system(cm)
