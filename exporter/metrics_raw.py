#!/usr/bin/python3 -B
#coding: UTF-8
import json, memcache
mc = memcache.Client(["127.0.0.1:11211"])
metrics = mc.get('metrics')

print("Content-type: application/json")
print('')

print(metrics)
