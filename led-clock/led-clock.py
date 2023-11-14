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
            self.elements = self.config["elements"]

        self.map = collections.OrderedDict()
        self.colors = collections.OrderedDict()

        self.mqcl = None

        self.icons = {}
        self.ledW = 128
        self.ledH = 64
        self.delay = 0.05

        self.debugBorders = False

        self.fontClock = graphics.Font()
        self.fontClock.LoadFont("./fonts/win_crox5h.bdf")
        self.fontClockH = 19
        self.fontReg = graphics.Font()
        # self.fontReg.LoadFont("./fonts/win_crox1h.bdf")
        self.fontReg.LoadFont("./fonts/helvR08.bdf")
        self.fontRegH = 9

        self.imgSize = 8

        self.rowH = self.fontRegH + 1

        self.userBrightness = None
        self.bri = 1
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
        options.brightness = 30
        options.show_refresh_rate = False

        self.matrix = RGBMatrix(options = options)
        self.canvas = self.matrix.CreateFrameCanvas()

        self.hassUpdated = 0
        self.hass = None

    def run(self):
        while True:
            now = time.time_ns() // 1000000
            next = now + self.delay * 1000
            self.clock()
            new = time.time_ns() // 1000000
            diff = next-new
            if diff < 0:
                #print("LAG " + str(diff) + "ms")
                continue
            #print("SLEEP " + str(diff) + "ms")
            time.sleep(diff / 1000)

    def clock(self):
        self.canvas.Clear()
        #graphics.DrawText(self.canvas, self.fontSm, 64, 10, self.colorW, u'TEST PANEL 2')
        #graphics.DrawText(self.canvas, self.fontSm, 64, 20, self.colorG, u'MEOW MEOW')
        now = datetime.datetime.now()
        self.drawTime(now)

        self.mqttLoop()

        hass = self.readHass()
        if not hass:
            graphics.DrawText(self.canvas, self.fontReg, 1, 31, self.getColor('clock'), u'NO HASS')
        else:
            self.defineBrightness(now)
            self.drawTemp(now)
            self.drawHumidity()
            self.drawForecast()
            self.drawWind()
            self.drawCo2()
            self.drawSky()
            self.drawPrecip()


        self.canvas = self.matrix.SwapOnVSync(self.canvas)

    def printText(self, text):
        self.canvas.Clear()
        now = int(time.time())
        while int(time.time()) < now + 5:
            self.canvas.Clear()
            posX = 8
            color = graphics.Color(random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))
            for line in textwrap.wrap(text, self.ledW/5):
                graphics.DrawText(self.canvas, self.fontReg, 1, posX, color, line)
                posX += 8
            self.canvas = self.matrix.SwapOnVSync(self.canvas)
            time.sleep(0.1)

    def drawTime(self, now):
        text = now.strftime("%H:%M")
        width = self.calcWidth(text, self.fontClock)
        coords = self.getCoords('clock', w=width, h=self.fontClockH)
        color = self.getColor('clock')
        graphics.DrawText(self.canvas, self.fontClock, coords['x'], coords['y'], color, text)

    def drawCo2(self):
        dev_co2 = self.getHassEntity('co2_level')
        if dev_co2 is not None:
            text = u'{0}ppm'.format(int(float(dev_co2)))
        else:
            text = 'N/A'
        width = self.calcWidth(text, self.fontReg)
        coords = self.getCoords('co2', w=width, h=self.fontRegH)
        color = self.getColor('co2')
        graphics.DrawText(self.canvas, self.fontReg, coords['x'], coords['y'], color, text)

    def drawHumidity(self):
        dev_hum = self.getHassEntity('humidity_inside')
        if dev_hum is not None:
            text = u'{0}%'.format(int(round(float(dev_hum), 0)))
        else:
            text = 'N/A'
        width = self.calcWidth(text, self.fontReg)
        coords = self.getCoords('hum', h=self.fontRegH, w=width)
        color = self.getColor('hum')
        graphics.DrawText(self.canvas, self.fontReg, coords['x'], coords['y'], color, text)

    def drawWind(self):
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
        dev_wind_speed = self.getHassEntity('wind_speed')
        dev_wind_bearing = self.getHassEntity('wind_bearing')
        text = 'N/A'
        if dev_wind_bearing is not None and dev_wind_speed is not None:
            text = u'{1} {0}m/s'.format(int(round(float(dev_wind_speed), 0)), WIND_DIRECTION_MAPPING[dev_wind_bearing])

        width = self.calcWidth(text, self.fontReg)
        coords = self.getCoords('wind', w=width, h=self.fontRegH)
        color = self.getColor('wind')
        graphics.DrawText(self.canvas, self.fontReg, coords['x'], coords['y'], color, text)

    def drawTemp(self, now):
        dev_temp_inside = self.getHassEntity('temp_inside')
        text = 'N/A'
        if dev_temp_inside is not None:
            text = u'{0}°'.format(round(float(dev_temp_inside), 1))

        width = self.calcWidth(text, self.fontReg)
        coords = self.getCoords('temp_inside', w=width, h=self.fontRegH)
        color = self.getColor('temp_inside')
        color_dot = self.getColor('temp_inside', 'dot')
        graphics.DrawText(self.canvas, self.fontReg, coords['x'], coords['y'], color, text)
        graphics.DrawText(self.canvas, self.fontReg, coords['x'], coords['y'], color_dot, '    . ')

        if now.second % 10 >= 5:
            col = self.getColor('temp_outside')
            dev_temp_outside = self.getHassEntity('temp_outside')
        else:
            col = self.getColor('temp_outside', 'provided')
            dev_temp_outside = self.getHassEntity('temp_outside_provided')

        text = 'N/A'
        if dev_temp_outside is not None:
            text = u'{0}°'.format(int(round(float(dev_temp_outside), 0)))

        width = self.calcWidth(text, self.fontReg)
        coords = self.getCoords('temp_outside', w=width, h=self.fontRegH)
        graphics.DrawText(self.canvas, self.fontReg, coords['x'], coords['y'], col, text)

        dev_current_icon = self.getHassEntity('current_weather_icon')
        if dev_current_icon is None:
            return
        coords = self.getCoords('outside_icon', w=self.imgSize, h=self.imgSize)
        self.drawImage(self.getIcon(dev_current_icon), coords['x'], coords['y'])

    def drawForecast(self):
        c = self.getColor('weather1')
        dev_forecast = self.getHassEntity('forecast')
        if dev_forecast is None:
            return

        if len(dev_forecast['forecast']) < 2:
            return

        fc1 = u'{0}{1}°'.format(self.formatDayTime(dev_forecast['forecast'][0]['datetime']), int(round(dev_forecast['forecast'][0]['temperature'])))
        coords = self.getCoords('weather1', w=self.calcWidth(fc1, self.fontReg), h=self.fontRegH)
        graphics.DrawText(self.canvas, self.fontReg, coords['x'], coords['y'], c, fc1)

        coords = self.getCoords('weather1_icon', w=self.imgSize, h=self.imgSize)
        self.drawImage(self.getIcon(dev_forecast['forecast_icons'][0]), coords['x'], coords['y'])

        fc2 = u'{0}{1}°'.format(self.formatDayTime(dev_forecast['forecast'][1]['datetime']), int(round(dev_forecast['forecast'][1]['temperature'])))
        coords = self.getCoords('weather2', w=self.calcWidth(fc2, self.fontReg), h=self.fontRegH)
        graphics.DrawText(self.canvas, self.fontReg, coords['x'], coords['y'], c, fc2)

        coords = self.getCoords('weather2_icon', w=self.imgSize, h=self.imgSize)
        self.drawImage(self.getIcon(dev_forecast['forecast_icons'][1]), coords['x'], coords['y'])

    def getIcon(self, iconName):
        #https://yastatic.net/weather/i/icons/islands/32/
        if iconName in self.icons:
            return self.icons[iconName]
        imgSize = 8
        i8 = '/opt/src/weather-station/icons8/{0}_{1}.png'.format(iconName, imgSize)
        if os.path.isfile(i8):
            i = Image.open(i8).resize((self.imgSize, self.imgSize), Image.HAMMING)
        else:
            i = Image.open('/opt/src/weather-station/icons/' + iconName + '.png').resize((self.imgSize, self.imgSize), Image.HAMMING)
        m = Image.new('RGB', i.size, "BLACK")
        m.paste(i, (0, 0), i)
        self.icons[iconName] = m
        return self.icons[iconName]

    def drawImage(self, image, posX, posY):
        img_width, img_height = image.size
        posY -= self.imgSize
        pixels = image.load()
        for x in range(max(0, -posX), min(img_width, self.ledW - posX)):
            for y in range(max(0, -posY), min(img_height, self.ledH - posY)):
                (r, g, b) = pixels[x, y]
                if r == g == b == 0:
                    continue
                self.canvas.SetPixel(x + posX, y + posY, self.c(r*0.7), self.c(g*0.7), self.c(b*0.7))

    def drawSky(self):
        dev_sun = self.getHassEntity('sun_period')
        if dev_sun is None:
            return

        curTime = datetime.datetime.now()

        sr = datetime.datetime.fromisoformat(dev_sun['next_rising'])
        ss = datetime.datetime.fromisoformat(dev_sun['next_setting'])
        dayLen = 0
        day = True
        if sr > ss:
            #day
            dayLen = (ss-sr).total_seconds()+86400
        elif sr < ss:
            #night
            day = False
            dayLen = (ss-sr).total_seconds()
        nightLen = 86400 - dayLen

        if day:
            r=255
            g=150
            b=0
            perc = (curTime.timestamp() + 86400 - sr.timestamp()) / dayLen
        else:
            r=0
            g=0
            b=150
            perc = 1 - (sr.timestamp() - curTime.timestamp()) / nightLen

        #print("dl {0}; perc {1}; cur {2}; sr {3}; ss {4}; day {5}".format(dayLen, perc, curTime.timestamp(), sr.timestamp(), ss.timestamp(), day))

        dot = int(round(round(self.ledW * perc)))
        self.canvas.SetPixel(dot, 0, r, g, b)
        self.canvas.SetPixel(dot-1, 0, r, g, b)
        self.canvas.SetPixel(dot+1, 0, r, g, b)

    def drawPrecip(self):
        prec_type = None
        prec_strength = None
        wind_speed = None

        dev_prec_type = self.getHassEntity('prec_type')
        if dev_prec_type is not None:
            prec_type = int(dev_prec_type)

        dev_prec_strength = self.getHassEntity('prec_strength')
        if dev_prec_strength is not None:
            prec_strength = float(dev_prec_strength)

        dev_wind_speed = self.getHassEntity('wind_speed')
        if dev_wind_speed is not None:
            wind_speed = int(round(dev_wind_speed, 0))

        if prec_type is None or prec_strength is None or wind_speed is None or prec_strength == 0:
            return

        maxFlakes = int(self.ledH * prec_strength)
        minX = 0
        speed = 10 # pixels per second
        if prec_type == 0: # no precipitation
            self.delay = 0.05
            return
        elif prec_type == 1: # rain
            # self.delay = 0.01
            speed = 30
        elif prec_type == 2: # rain + snow
            # self.delay = 0.04
            speed = 15
        elif prec_type == 3: # snow
            # self.delay = 0.05
            speed = 6
        self.delay = 0

        delay = 1 / speed
        interval = self.ledH / (maxFlakes * speed)
        horizontalSpeed = int(wind_speed/2)
        if horizontalSpeed > 0:
            minX = -32

        nowMicro = datetime.datetime.now().timestamp()
        if (len(self.snow) < maxFlakes) and (nowMicro - self.snowTimer > interval):
            startY = 0
            self.snow.append({'x': random.randint(minX, self.ledW - 1), 'y': startY, 'timer': time.time(), 'color': self.getColorByPrec(prec_type)})
            self.snowTimer = nowMicro

        for i, f in enumerate(self.snow):
            self.canvas.SetPixel(f['x'], f['y'], f['color'][0], f['color'][1], f['color'][2])
            if nowMicro - self.snow[i]['timer'] < delay:
                continue
            # realSpeed = 1 / (nowMicro - self.snow[i]['timer'])
            # print('real speed: ' + str(realSpeed))
            self.snow[i]['timer'] = nowMicro

            if prec_type == 1:
                self.snow[i]['color'] = self.getColorByPrec(1)
                self.snow[i]['y'] += 1
                self.snow[i]['x'] += 0 if horizontalSpeed == 0 or self.snow[i]['y'] % horizontalSpeed == 0 else 1
            elif prec_type == 2:
                self.snow[i]['y'] += 1
                self.snow[i]['x'] += random.randint(0, horizontalSpeed)
            elif prec_type == 3:
                self.snow[i]['color'] = self.getColorByPrec(3)
                self.snow[i]['y'] += 1
                self.snow[i]['x'] += random.randint(-1, 1)

            if self.snow[i]['y'] > self.ledH - 1:
                self.snow.pop(i)

    def getCoords(self, id, w, h):
        color = self.elements[id]["border_color"]
        align_x = self.elements[id]["align_x"]
        row = self.elements[id]["row"]
        rowspan = self.elements[id]["rowspan"] if "rowspan" in self.elements[id] else 1

        if align_x == 'left':
            x = 0
        else:
            x = self.ledW - 1 - w
        y = self.rowH * (row+rowspan)
        if rowspan > 1 and self.rowH * rowspan > h:
            # correction to align text to the top if rowspan is used
            y -= self.rowH * rowspan - h

        for mapId in (self.map if align_x == 'left' else self.map):
            if mapId == id:
                break
            item = self.map[mapId]
            if item['a'] != align_x:
                continue
            if (y - h) <= item['y'] and y >= (item['y'] - item['h']):
                if align_x == 'left':
                    x = x + item['w'] + 1
                else:
                    x = x - item['w'] - 1
        coords = {'id': id, 'x': x, 'y': y, 'w': w, 'h': h, 'a': align_x}
        self.map[id] = coords

        if not self.debugBorders:
            return coords

        c = graphics.Color(color[0], color[1], color[2])
        graphics.DrawLine(self.canvas, coords['x'], coords['y'], coords['x'] + w, coords['y'], c)
        graphics.DrawLine(self.canvas, coords['x'], coords['y'] - h, coords['x'] + w, coords['y'] - h, c)
        graphics.DrawLine(self.canvas, coords['x'], coords['y'], coords['x'], coords['y'] - h, c)
        graphics.DrawLine(self.canvas, coords['x'] + w, coords['y'] - h, coords['x'] + w, coords['y'], c)

        return coords

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

    def getColor(self, id, type=None):
        key = id
        if type is not None:
            key = key + "_" + type
        if key in self.colors:
            return self.colors[key]

        elem = self.elements[id]
        color_key = "color"
        if type is not None:
            color_key = type + "_color"
        color_raw = elem[color_key]

        color = graphics.Color(self.c(color_raw[0]), self.c(color_raw[1]), self.c(color_raw[2]))
        self.colors[key] = color

        return color

    def c(self, col):
        if col*self.bri>255:
            return 255
        return col*self.bri

    def calcWidth(self, text, font):
        w = 0
        for char in text:
            w += font.CharacterWidth(ord(char))
        return w

    def formatDayTime(self, time_str):
        dt = datetime.datetime.strptime(time_str, '%Y-%m-%dT%H:%M:%S.%f')
        # dt = datetime.date.fromisoformat(time_str)
        if dt.hour >= 18:
            return 'e'
        elif dt.hour >= 12:
            return 'd'
        elif dt.hour >= 6:
            return 'm'
        elif dt.hour >= 0:
            return 'n'
        return 'u'

    def defineBrightness(self, now):
        self.bri = 1
        if self.userBrightness:
            if self.userBrightness == 1:
                self.matrix.brightness = 1
                self.bri = 0.5
            else:
                self.matrix.brightness = self.userBrightness
            return

        dev_sun = self.getHassEntity('sun_current')
        if 0 <= now.hour < 6:
            if dev_sun == 'below_horizon':
                self.matrix.brightness = 1
                self.bri = 0.5
            else:
                self.matrix.brightness = 20
        elif 6 <= now.hour < 9:
            if dev_sun == 'below_horizon':
                self.matrix.brightness = 20
            else:
                self.matrix.brightness = 50
        elif 18 <= now.hour < 22:
            self.matrix.brightness = 25
        elif 22 <= now.hour < 24:
            self.matrix.brightness = 3
        else:
            self.matrix.brightness = 60

    def getHassEntity(self, configKey):
        if configKey not in self.config['devices']:
            return None
        device = self.config['devices'][configKey]
        entityKey = device['id']
        if entityKey not in self.hass:
            return None
        entity = self.hass[entityKey]
        if entity['state'] == 'unknown' or entity['state'] == 'unavailable':
            return None
        if 'attr' in device:
            if 'attributes' not in entity or device['attr'] not in entity['attributes']:
                return None

            return entity['attributes'][device['attr']]
        if 'attrs' in device:
            if 'attributes' not in entity:
                return None
            attrs = {}
            for attr in device['attrs']:
                if attr not in entity['attributes']:
                    return None
                attrs[attr] = entity['attributes'][attr]
            return attrs

        return entity['state']

    def readHass(self):
        now = time.time()
        if self.hassUpdated + self.config['metrics_period'] > now:
            return self.hass
        try:
            resp = requests.get(self.config['hass']['url'], headers={"Authorization": "Bearer {0}".format(self.config['hass']['token'])})
        except Exception as e:
            print("Cannot load hass: {0}".format(str(e)))
            graphics.DrawText(self.canvas, self.fontReg, 1, 31, self.getColor('clock'), u'HASS ERROR')
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
            graphics.DrawText(self.canvas, self.fontReg, 1, 26, self.getColor('clock'), u'MQTT ERROR')
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
