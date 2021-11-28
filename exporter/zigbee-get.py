#!/usr/bin/python3 -B
#coding: UTF-8
import telegram, memcache, cgi, json

print("Content-type: text/plain")
print('')

mc = memcache.Client(["127.0.0.1:11211"])
print(mc.get('zigbee-devices'))