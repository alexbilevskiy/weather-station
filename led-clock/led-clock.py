#!/usr/bin/python3 -B
# coding: UTF-8
import re

import requests
from rgbmatrix import graphics, RGBMatrix, RGBMatrixOptions
from PIL import Image
import time, datetime, json, textwrap, random, os, psutil, collections
import paho.mqtt.client as mqtt

class RunText:
    def __init__(self):
        p = psutil.Process()
        p.cpu_affinity([3])

        with open('../config-clock.json') as f:
            s = f.read()
            self.config = json.loads(s)

        self.map = collections.OrderedDict()

        self.mqcl = None

        self.icons = {}
        self.ledW = 64
        self.ledH = 32
        self.delay = 0.05

        self.clockPos = [0, 14]
        self.tempPos = [46, 7]
        self.co2Pos = [1, 31]
        self.humPos = [1, 23]
        self.windSpPos = [25, 23]
        self.forecastPos = [41, 23]

        self.fontReg = graphics.Font()
        self.fontReg.LoadFont("./fonts/10x20.bdf")
        self.fontRegW = 8
        self.fontRegH = 14
        self.fontSm = graphics.Font()
        self.fontSm.LoadFont("./fonts/5x8.bdf")
        self.fontSmW = 5
        self.fontSmH = 7
        self.fontSmm = graphics.Font()
        self.fontSmm.LoadFont("./fonts/4x6.bdf")
        self.fontSmmW = 4

        self.imgW = 8
        self.imgH = 7

        self.userBrightness = None
        self.bri = 1
        self.prevBri = None
        self.initColors()
        self.snow = []
        self.snowTimer = time.time()

        options = RGBMatrixOptions()
        options.rows = self.ledH
        options.cols = self.ledW
        options.chain_length = 1
        options.parallel = 1
        options.multiplexing = 0
        options.pwm_bits = 11
        options.pwm_lsb_nanoseconds = 130
        options.gpio_slowdown = 2
        options.disable_hardware_pulsing = False
        options.hardware_mapping = 'regular'
        options.row_address_type = 0
        options.brightness = 100
        options.show_refresh_rate = False

        self.matrix = RGBMatrix(options = options)
        self.canvas = self.matrix.CreateFrameCanvas()

        self.hassUpdated = 0
        self.hass = None

    def initColors(self):
        if self.bri == self.prevBri:
            return
        self.prevBri = self.bri
        self.colorW = graphics.Color(self.c(255), self.c(255), self.c(255))
        self.colorR = graphics.Color(self.c(110), self.c(0), self.c(0))
        self.colorG = graphics.Color(self.c(0), self.c(255), self.c(0))
        self.colorB = graphics.Color(self.c(0), self.c(0), self.c(255))
        self.colorY = graphics.Color(self.c(255), self.c(255), self.c(0))
        self.colorGray = graphics.Color(self.c(90), self.c(90), self.c(90))

        #self.insideTempColor = graphics.Color(self.c(30), self.c(250), self.c(50))
        #self.insideTempColor = graphics.Color(self.c(3), self.c(160), self.c(20))
        self.insideTempColor = graphics.Color(self.c(2), self.c(100), self.c(12))
        self.tempDotColor = self.colorR
        self.outsideTempYaColor = graphics.Color(self.c(10), self.c(60), self.c(60))
        #self.outsideTempColor = graphics.Color(self.c(100), self.c(255), self.c(255))
        self.outsideTempColor = graphics.Color(self.c(20), self.c(110), self.c(110))
        self.forecastColor = graphics.Color(self.c(60), self.c(20), self.c(60))
        self.co2Color = graphics.Color(self.c(80), self.c(80), self.c(80))
        self.humColor = graphics.Color(self.c(80), self.c(80), self.c(80))
        self.windColor = graphics.Color(self.c(20), self.c(60), self.c(110))

    def c(self, col):
        if col*self.bri>255:
            return 255
        return col*self.bri

    def run(self):
        while True:
            self.clock()
            time.sleep(self.delay)

    def clock(self):
        self.canvas.Clear()
        #graphics.DrawText(self.canvas, self.fontSm, 64, 10, self.colorW, u'TEST PANEL 2')
        #graphics.DrawText(self.canvas, self.fontSm, 64, 20, self.colorG, u'MEOW MEOW')
        now = datetime.datetime.now()
        self.drawTime(now.strftime("%H"), now.strftime("%M"))

        self.mqttLoop()

        hass = self.readHass()
        if not hass:
            graphics.DrawText(self.canvas, self.fontSm, 1, 31, self.colorW, u'NO HASS')
        else:
            self.defineBrightness(now, hass)
            self.drawTemp(hass)
            self.drawHumidity(hass)
            self.drawWind(hass)
            self.drawCo2(hass)
            self.drawSky(hass)

            #not implemented yet
            #self.drawForecast(hass)

            #requires yandex "radar" sensor
            #self.drawPrecip(hass)


        self.canvas = self.matrix.SwapOnVSync(self.canvas)

    def printText(self, text):
        self.canvas.Clear()
        now = int(time.time())
        while int(time.time()) < now + 5:
            self.canvas.Clear()
            posX = 8
            color = graphics.Color(random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))
            for line in textwrap.wrap(text, self.ledW/5):
                graphics.DrawText(self.canvas, self.fontSm, 1, posX, color, line)
                posX += 8
            self.canvas = self.matrix.SwapOnVSync(self.canvas)
            time.sleep(0.1)

    def getCoords(self, id, y, w, h, a='left', color=None, padding = 0, overlapY = False):
        if color is None:
            color = [255, 0, 0]
        if a == 'left':
            x = 0
        else:
            x = 63 - w
        for mapId in (self.map if a == 'left' else self.map):
            if mapId == id:
                break
            if overlapY == True:
                break
            item = self.map[mapId]
            if item['a'] != a:
                continue
            if (y - h) <= item['y'] and y >= (item['y'] - item['h']):
                if a == 'left':
                    x = x + item['w'] + 1 + padding
                else:
                    x = x - item['w'] - 1 - padding
        coords = {'id': id, 'x': x, 'y': y, 'w': w, 'h': h, 'a': a}
        self.map[id] = coords

        # c = graphics.Color(color[0], color[1], color[2])
        # graphics.DrawLine(self.canvas, coords['x'], coords['y'], coords['x'] + w, coords['y'], c)
        # graphics.DrawLine(self.canvas, coords['x'], coords['y'] - h, coords['x'] + w, coords['y'] - h, c)
        # graphics.DrawLine(self.canvas, coords['x'], coords['y'], coords['x'], coords['y'] - h, c)
        # graphics.DrawLine(self.canvas, coords['x'] + w, coords['y'] - h, coords['x'] + w, coords['y'], c)

        return coords

    def drawTime(self, h, m):
        coords = self.getCoords('clock', self.clockPos[1], 44, 14, 'left')
        graphics.DrawText(self.canvas, self.fontReg, coords['x'], self.clockPos[1], self.colorW, h)
        graphics.DrawText(self.canvas, self.fontReg, coords['x'] + 17, self.clockPos[1], self.colorW, ':')
        graphics.DrawText(self.canvas, self.fontReg, coords['x'] + 25, self.clockPos[1], self.colorW, m)

    def drawCo2(self, hass):
        dev_co2 = self.config['devices']['co2_level']
        if dev_co2['id'] in hass:
            co2text = u'{0}p'.format(int(float(hass[dev_co2['id']]['state'])))
        else:
            co2text = 'N/A'
        width = len(co2text) * self.fontSmW
        coords = self.getCoords('co2', self.co2Pos[1], width, self.fontSmH, 'left', [255, 0, 255])
        graphics.DrawText(self.canvas, self.fontSm, coords['x'], self.co2Pos[1], self.co2Color, co2text)

    def drawHumidity(self, hass):
        dev_hum = self.config['devices']['humidity_inside']
        if dev_hum['id'] in hass:
            hinText = u'{0}%'.format(int(round(float(hass[dev_hum['id']]['state']), 0)))
        else:
            hinText = 'N/A'
        width = len(hinText) * self.fontSmW
        coords = self.getCoords('hum', self.humPos[1], width, self.fontSmH, color=[255, 100, 100], a='left')
        graphics.DrawText(self.canvas, self.fontSm, coords['x'], self.humPos[1], self.humColor, hinText)

    def drawWind(self, hass):
        dev_wind_speed = self.config['devices']['wind_speed']
        dev_wind_bearing = self.config['devices']['wind_bearing']
        WIND_DIRECTION_MAPPING = {
            315: "nw",
            360: "n",
            45: "ne",
            90: "e",
            135: "se",
            180: "s",
            225: "sw",
            270: "w",
            0: "c",
        }
        try:
            windSpeedText = u'{1}{0}'.format(int(round(float(hass[dev_wind_speed['id']]['attributes'][dev_wind_speed['attr']]), 0)), WIND_DIRECTION_MAPPING[hass[dev_wind_bearing['id']]['attributes'][dev_wind_bearing['attr']]])
        except:
            windSpeedText = 'N/A'

        width = len(windSpeedText) * self.fontSmW
        coords = self.getCoords('wind', self.windSpPos[1], width, self.fontSmH, a='right', color=[100, 255, 150], padding=0)
        graphics.DrawText(self.canvas, self.fontSm, coords['x'], self.windSpPos[1], self.windColor, windSpeedText)

    def drawTemp(self, hass):
        dev_temp_in = self.config['devices']['temp_inside']
        if dev_temp_in['id'] in hass:
            r, d = str(round(float(hass[dev_temp_in['id']]['state']), 1)).split('.')
        else:
            r = 'N/'
            d = 'A'

        width = 17
        coords = self.getCoords('temp_inside', self.tempPos[1], width, self.fontSmH, a='right', color=[160, 100, 90])
        graphics.DrawText(self.canvas, self.fontSm, coords['x'], coords['y'], self.insideTempColor, u'{0}'.format(r))
        graphics.DrawText(self.canvas, self.fontSm, coords['x'] + 10, coords['y'], self.insideTempColor, u'{0}'.format(d))
        graphics.DrawText(self.canvas, self.fontSm, coords['x'] + 14, coords['y'], self.insideTempColor, u'°')
        self.canvas.SetPixel(coords['x'] + 9, coords['y'] - 1, self.tempDotColor.red, self.tempDotColor.green, self.tempDotColor.blue)

        if int(datetime.datetime.now().strftime("%s")) % 10 >= 5:
            dev_out = self.config['devices']['temp_outside']
            if dev_out['id'] in hass:
                temp = int(round(float(hass[dev_out['id']]['state']), 0))
            else:
                temp = None
            col = self.outsideTempColor
        else:
            dev_out = self.config['devices']['temp_outside_provided']
            temp = int(round(float(hass[dev_out['id']]['attributes'][dev_out['attr']]), 0))
            col = self.outsideTempYaColor

        if temp is not None:
            sign = self.getSign(temp)
            temp = abs(temp)
        else:
            temp = 'NA'
            sign = '?'

        tempStr = u'{0}'.format(temp)
        width = len(tempStr) * self.fontSmW + len(sign) * self.fontSmmW + 2 # ° correction
        coords = self.getCoords('temp_outside', self.tempPos[1] + 7, width, self.fontSmH, a='right', overlapY = True, color=[90, 100, 160])
        ofs = 0
        if sign:
            ofs = self.fontSmmW
        graphics.DrawText(self.canvas, self.fontSmm, coords['x'], self.tempPos[1] + 7, col, sign)
        graphics.DrawText(self.canvas, self.fontSm, coords['x'] + ofs, self.tempPos[1] + 7, col, tempStr)
        graphics.DrawText(self.canvas, self.fontSm, coords['x'] + width - 3, self.tempPos[1] + 7, col, u'°')

    def drawForecast(self, metrics):
        c = self.forecastColor
        if not metrics['yandex']['forecast'] or len(metrics['yandex']['forecast']['parts']) <= 0:
            graphics.DrawText(self.canvas, self.fontSm, self.forecastPos[0], self.forecastPos[1], c, 'NO WEATHER')
            return

        fc1 = u'{0}{1}'.format(self.formatDayTime(metrics['yandex']['forecast']['parts'][0]['part_name']), metrics['yandex']['forecast']['parts'][0]['temp_avg'])
        width = len(fc1) * self.fontSmW + 2 # corection for "°"
        coords = self.getCoords('weather1', self.forecastPos[1], width, self.fontSmH, a='right', color=[100, 100, 255])
        graphics.DrawText(self.canvas, self.fontSm, coords['x'], self.forecastPos[1], c, fc1)
        graphics.DrawText(self.canvas, self.fontSm, coords['x'] + width - 3, self.forecastPos[1], c, u'°')

        coords = self.getCoords('weather1_icon', self.forecastPos[1], self.imgW, self.imgH, a='right', color=[255, 100, 255])
        self.drawImage(self.getIcon(metrics['yandex']['forecast']['parts'][0]['icon']), coords['x'], coords['y'])

        fc2 = u'{0}{1}'.format(self.formatDayTime(metrics['yandex']['forecast']['parts'][1]['part_name']), metrics['yandex']['forecast']['parts'][1]['temp_avg'])
        width = len(fc2) * self.fontSmW + 2 # corection for "°"
        coords = self.getCoords('weather2', self.forecastPos[1] + 8, width, self.fontSmH, a='right', color=[100, 100, 255])
        graphics.DrawText(self.canvas, self.fontSm, coords['x'], self.forecastPos[1] + 8, c, fc2)
        graphics.DrawText(self.canvas, self.fontSm, coords['x'] + width - 3, self.forecastPos[1] + 8, c, u'°')

        coords = self.getCoords('weather2_icon', self.forecastPos[1] + 8, self.imgW, self.imgH, a='right', color=[255, 100, 255])
        self.drawImage(self.getIcon(metrics['yandex']['forecast']['parts'][1]['icon']), coords['x'], coords['y'])

    def getIcon(self, iconName):
        #https://yastatic.net/weather/i/icons/islands/32/
        if iconName in self.icons:
            return self.icons[iconName]
        i8 = '/opt/src/station/icons8/' + iconName + '_8.png'
        if os.path.isfile(i8):
            i = Image.open(i8)
        else:
            i = Image.open('/opt/src/station/icons/' + iconName + '.png').resize((8, 8), Image.HAMMING)
        m = Image.new('RGB', i.size, "BLACK")
        m.paste(i, (0, 0), i)
        self.icons[iconName] = m
        return self.icons[iconName]

    def drawImage(self, image, posX, posY):
        img_width, img_height = image.size
        posY -= self.imgH
        pixels = image.load()
        for x in range(max(0, -posX), min(img_width, self.ledW - posX)):
            for y in range(max(0, -posY), min(img_height, self.ledH - posY)):
                (r, g, b) = pixels[x, y]
                if r == g == b == 0:
                    continue
                self.canvas.SetPixel(x + posX, y + posY, self.c(r*0.7), self.c(g*0.7), self.c(b*0.7))

    def drawSky(self, hass):
        dev_sun = self.config['devices']['sun']
        sun = hass[dev_sun['id']]

        sr = datetime.datetime.fromisoformat(sun['attributes']['next_rising'])
        ss = datetime.datetime.fromisoformat(sun['attributes']['next_setting'])
        dayLen = (ss-sr).total_seconds()
        curTime = datetime.datetime.now()
        perc = (curTime.timestamp()+86400-sr.timestamp()) / dayLen

        dot = int(round(round(self.ledW * perc)))
        self.canvas.SetPixel(dot, 0, 255, 150, 0)
        self.canvas.SetPixel(dot-1, 0, 255, 150, 0)
        self.canvas.SetPixel(dot+1, 0, 255, 150, 0)

    def drawPrecip(self, metrics):
        # metrics['yandex']['radar']['current']['prec_type'] = 2
        # metrics['yandex']['radar']['strength'] = 'avg'
        # metrics['yandex']['fact']['wind_speed'] = 2

        try:
            metrics['yandex']['radar']['current']['prec_type']
            metrics['yandex']['fact']['wind_speed']
            metrics['yandex']['radar']['current']['prec_strength']

        except Exception as e:
            print('prec exc: ' + str(e))
            return

        strength = 0
        if metrics['yandex']['radar']['current']['prec_strength'] == 0:
            try:
                metrics['yandex']['radar']['strength']
            except:
                metrics['yandex']['radar']['strength'] = 'avg'
            if metrics['yandex']['radar']['strength'] == 'avg':
                strength = 0.5
            else:
                strength = 1
        else:
            strength = metrics['yandex']['radar']['current']['prec_strength']

        maxFlakes = int(self.ledH * strength)
        minX = 0
        speed = 10 # pixels per second
        if metrics['yandex']['radar']['current']['prec_type'] == 0: # no precipitation
            self.delay = 0.05
            return
        elif metrics['yandex']['radar']['current']['prec_type'] == 1: # rain
            # self.delay = 0.01
            speed = 30
        elif metrics['yandex']['radar']['current']['prec_type'] == 2: # rain + snow
            # self.delay = 0.04
            speed = 15
        elif metrics['yandex']['radar']['current']['prec_type'] == 3: # snow
            # self.delay = 0.05
            speed = 6
        self.delay = 0

        delay = 1 / speed
        interval = self.ledH / (maxFlakes * speed)
        horizontalSpeed = int(metrics['yandex']['fact']['wind_speed']/3)
        if horizontalSpeed > 0:
            minX = -16

        nowMicro = datetime.datetime.now().timestamp()
        if (len(self.snow) < maxFlakes) and (nowMicro - self.snowTimer > interval):
            startY = 0
            self.snow.append({'x': random.randint(minX, self.ledW - 1), 'y': startY, 'timer': time.time(), 'color': self.getColorByPrec(metrics['yandex']['radar']['current']['prec_type'])})
            self.snowTimer = nowMicro

        for i, f in enumerate(self.snow):
            self.canvas.SetPixel(f['x'], f['y'], f['color'][0], f['color'][1], f['color'][2])
            if nowMicro - self.snow[i]['timer'] < delay:
                continue
            # realSpeed = 1 / (nowMicro - self.snow[i]['timer'])
            # print('real speed: ' + str(realSpeed))
            self.snow[i]['timer'] = nowMicro

            if metrics['yandex']['radar']['current']['prec_type'] == 1:
                self.snow[i]['color'] = self.getColorByPrec(1)
                self.snow[i]['y'] += 1
                self.snow[i]['x'] += 0
                self.snow[i]['x'] += int(metrics['yandex']['fact']['wind_speed']/4)
            elif metrics['yandex']['radar']['current']['prec_type'] == 2:
                self.snow[i]['y'] += 1
                self.snow[i]['x'] += random.randint(0, horizontalSpeed)
            elif metrics['yandex']['radar']['current']['prec_type'] == 3:
                self.snow[i]['color'] = self.getColorByPrec(3)
                self.snow[i]['y'] += 1
                self.snow[i]['x'] += random.randint(-1, 1)

            if self.snow[i]['y'] > self.ledH - 1:
                self.snow.pop(i)

    def getColorByPrec(self, prec):
        if prec == 1:
            return [0, random.randint(100, 150), random.randint(200, 255)]
        elif prec == 2:
            if random.randint(0, 1) == 1:
                return [random.randint(100, 150), random.randint(100, 150), random.randint(100, 150)]
            else:
                return [0, random.randint(100, 150), random.randint(200, 255)]
        elif prec == 3:
            c = random.randint(50, 255)
            return [c, c, c]

    def formatDayTime(self, n):
        if n == 'night':
            return 'n'
        elif n == 'morning':
            return 'm'
        elif n == 'day':
            return 'd'
        elif n == 'evening':
            return 'e'
        return n

    def defineBrightness(self, now, hass):
        if self.userBrightness:
            if self.userBrightness == 1:
                self.matrix.brightness = 2
                self.bri = 0.5
            else:
                self.matrix.brightness = self.userBrightness
                self.bri = 1
            self.initColors()
            return
        self.bri = 1
        dev_sun = self.config['devices']['sun']
        if 0 <= now.hour < 6:
            if hass[dev_sun['id']]['state'] == 'below_horizon':
                self.bri = 0.5
                self.matrix.brightness = 2
            else:
                self.bri = 1
                self.matrix.brightness = 20
        elif 6 <= now.hour < 9:
            if hass[dev_sun['id']]['state'] == 'below_horizon':
                self.bri = 1
                self.matrix.brightness = 20
            else:
                self.bri = 1
                self.matrix.brightness = 50
        elif 18 <= now.hour < 22:
            self.bri = 1
            self.matrix.brightness = 25
        elif 22 <= now.hour < 24:
            self.bri = 1
            self.matrix.brightness = 3
        else:
            self.bri = 1
            self.matrix.brightness = 60
        self.initColors()

    def readHass(self):
        now = time.time()
        if self.hassUpdated + self.config['metrics_period'] > now:
            return self.hass
        try:
            resp = requests.get(self.config['hass']['url'], headers={"Authorization": "Bearer {0}".format(self.config['hass']['token'])})
        except Exception as e:
            print("Cannot load hass: {0}".format(str(e)))
            graphics.DrawText(self.canvas, self.fontSm, 1, 31, self.colorW, u'HASS ERROR')
            return None

        if not resp:
            return False

        try:
            hass = resp.json()
        except Exception as e:
            print("Invalid hass states `{0}`: {1}".format(str(e), resp.text))
            return None

        hassAssoc = {}
        for entity in hass:
            hassAssoc[entity['entity_id']] = entity

        self.hassUpdated = now
        self.hass = hassAssoc

        return hassAssoc

    def mqttLoop(self):
        if not self.config['mqtt']['enabled']:
            return
        if self.mqcl is not None:
            self.mqcl.loop(0)
            return

        self.mqcl = mqtt.Client("led-clock")
        self.mqcl.enable_logger()
        self.mqcl.on_connect = self.mqtt_connect
        self.mqcl.on_disconnect = self.mqtt_disconnect
        self.mqcl.on_message = self.mqtt_message
        try:
            self.mqcl.connect(self.config['mqtt']['host'], self.config['mqtt']['port'], 60)
        except Exception as e:
            print("Cannot connect to mqtt: {0}".format(str(e)))
            graphics.DrawText(self.canvas, self.fontSm, 1, 26, self.colorW, u'MQTT ERROR')
            self.mqcl = None

    def mqtt_connect(self, client, userdata, flags, rc):
        print("Connected with result code "+str(rc))
        config = {
            "~": "homeassistant/light/led-clock",
            "name": "Led clock",
            "unique_id": "led-clock",
            "command_topic": "~/set",
            "state_topic": "~/state",
            "schema": "json",
            "brightness": True,
            "brightness_scale": 100
        }
        self.mqcl.subscribe(config['~'] + '/#')
        self.mqcl.publish('homeassistant/light/led-clock/config', payload=json.dumps(config), retain=True)

    def mqtt_disconnect(self, client, userdata, rc):
        print("mqtt disconnected!!!")
        exit()

    def mqtt_message(self, client, userdata, msg):
        #if re.match('.+state$', msg.topic):
            #self.mqtt_state()
        if re.match('.+set$', msg.topic):
            cmd = json.loads(msg.payload)
            if 'state' not in cmd:
                print('MQTT SET INVALID: ' + str(msg.payload))
                return
            if cmd['state'] == 'ON':
                if 'brightness' in cmd:
                    self.userBrightness = cmd['brightness']
                    print('set bri: ' + str(self.userBrightness))
                else:
                    self.userBrightness = self.matrix.brightness
            else:
                self.userBrightness = None
            self.mqtt_state()
        else:
            print('MQTT: ' + "\t" + str(msg.topic) + "\t" + str(msg.payload))

    def mqtt_state(self):
        if self.userBrightness:
            state = {"state": "ON", "brightness": self.userBrightness}
        else:
            state = {"state": "OFF"}
        #print('publish state ' + json.dumps(state))
        self.mqcl.publish('homeassistant/light/led-clock/state', json.dumps(state))

    def getSign(self, num):
        if num is None:
            return ''
        elif num > 0:
            return ''
        elif num == 0:
            return ''
        elif num < 0:
            return '-'
        else:
            return '?'

if __name__ == "__main__":
    run_text = RunText()
    run_text.run()
