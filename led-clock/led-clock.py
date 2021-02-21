#!/usr/bin/python3 -B
# coding: UTF-8
import re
from rgbmatrix import graphics, RGBMatrix, RGBMatrixOptions
from PIL import Image
import time, datetime, json, memcache, textwrap, random, os, psutil, collections
import paho.mqtt.client as mqtt

class RunText:
    def __init__(self):
        p = psutil.Process()
        p.cpu_affinity([3])

        self.map = collections.OrderedDict()

        self.mqcl = mqtt.Client("led-clock")
        self.mqcl.enable_logger()
        self.mqcl.on_connect = self.mqtt_connect
        self.mqcl.on_message = self.mqtt_message
        self.mqcl.connect("localhost", 1883, 60)

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

        self.mc = memcache.Client(["127.0.0.1:11211"])

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
            self.mqcl.loop(0)
            if self.mc.get('led-snake'):
                time.sleep(1)
                continue
            text = self.mc.get('led-text')
            if text:
                self.printText(text.encode('utf-8'))
            else:
                self.clock()
                time.sleep(self.delay)

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

    def clock(self):
        self.canvas.Clear()
        #graphics.DrawText(self.canvas, self.fontSm, 64, 10, self.colorW, u'TEST PANEL 2')
        #graphics.DrawText(self.canvas, self.fontSm, 64, 20, self.colorG, u'MEOW MEOW')
        now = datetime.datetime.now()
        self.drawTime(now.strftime("%H"), now.strftime("%M"))

        metrics = self.readArduino()
        if (not metrics) or (metrics['sensors']['esp01_fail'] and metrics['sensors']['esp02_fail']):
            graphics.DrawText(self.canvas, self.fontSm, 1, 25, self.colorW, u'NO DATA')
        elif metrics['sensors']['esp01_fail']:
            graphics.DrawText(self.canvas, self.fontSm, 1, 23, graphics.Color(50, 0, 0), u'ESP01 fail')
        elif metrics['sensors']['esp02_fail']:
            graphics.DrawText(self.canvas, self.fontSm, 1, 23, graphics.Color(50, 0, 0), u'ESP02 fail')

        self.defineBrightness(metrics, now)

        self.drawTemp(metrics)
        self.drawForecast(metrics)
        self.drawCo2(metrics)
        self.drawHumidity(metrics)
        self.drawWind(metrics)
        self.drawPrecip(metrics)
        self.drawSky(metrics)

        self.canvas = self.matrix.SwapOnVSync(self.canvas)

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

    def drawCo2(self, metrics):
        if metrics['sensors']['co2_ppm']:
            co2text = u'{0}p'.format(int(int(metrics['sensors']['co2_ppm'])/1))
        else:
            co2text = 'N/A'
        width = len(co2text) * self.fontSmW
        coords = self.getCoords('co2', self.co2Pos[1], width, self.fontSmH, 'left', [255, 0, 255])
        graphics.DrawText(self.canvas, self.fontSm, coords['x'], self.co2Pos[1], self.co2Color, co2text)

    def drawHumidity(self, metrics):
        if metrics['sensors']['h_in']:
            hinText = u'{0}%'.format(int(int(metrics['sensors']['h_in'])/1))
        else:
            hinText = 'N/A'
        width = len(hinText) * self.fontSmW
        coords = self.getCoords('hum', self.humPos[1], width, self.fontSmH, color=[255, 100, 100], a='left')
        graphics.DrawText(self.canvas, self.fontSm, coords['x'], self.humPos[1], self.humColor, hinText)

    def drawWind(self, metrics):
        try:
            windSpeedText = u'{1}{0}'.format(int(round(metrics['yandex']['fact']['wind_speed'], 0)), metrics['yandex']['fact']['wind_dir'])
        except:
            windSpeedText = 'N/A'

        width = len(windSpeedText) * self.fontSmW
        coords = self.getCoords('wind', self.windSpPos[1], width, self.fontSmH, a='right', color=[100, 255, 150], padding=0)
        graphics.DrawText(self.canvas, self.fontSm, coords['x'], self.windSpPos[1], self.windColor, windSpeedText)

    def drawTemp(self, metrics):
        if metrics['sensors']['t_in']:
            r, d = str(round(metrics['sensors']['t_in'], 1)).split('.')
        else:
            r = 'N'
            d = 'A'

        width = 17
        coords = self.getCoords('temp_inside', self.tempPos[1], width, self.fontSmH, a='right', color=[160, 100, 90])
        graphics.DrawText(self.canvas, self.fontSm, coords['x'], coords['y'], self.insideTempColor, u'{0}'.format(r))
        graphics.DrawText(self.canvas, self.fontSm, coords['x'] + 10, coords['y'], self.insideTempColor, u'{0}'.format(d))
        graphics.DrawText(self.canvas, self.fontSm, coords['x'] + 14, coords['y'], self.insideTempColor, u'°')
        self.canvas.SetPixel(coords['x'] + 9, coords['y'] - 1, self.tempDotColor.red, self.tempDotColor.green, self.tempDotColor.blue)

        if int(datetime.datetime.now().strftime("%s")) % 10 >= 5:
            temp = metrics['sensors']['t_out']
            col = self.outsideTempColor
        else:
            temp = metrics['yandex']['fact']['temp']
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

    def drawSky(self, metrics):
        try:
            metrics['yandex']['forecast']['sunrise']
        except TypeError:
            self.canvas.SetPixel(0, 0, 255, 0, 0)
            return
        dot = int(round(round(self.ledW * metrics['custom']['day_percent'])))
        self.canvas.SetPixel(dot, 0, 255, 150, 0)
        self.canvas.SetPixel(dot-1, 0, 255, 150, 0)
        self.canvas.SetPixel(dot+1, 0, 255, 150, 0)

        self.drawSkyBorder(metrics)

    def drawSkyBorder(self, metrics):
        return
        sky = []
        for x in range(0,self.ledW-1):
            sky.append([x,0])
        for y in range(0,self.ledH-1):
            sky.append([self.ledW-1,y])
        for x in range(self.ledW-1, 0, -1):
            sky.append([x,self.ledH-1])
        for y in range(self.ledH-1, 0, -1):
            sky.append([0,y])

        ofs = int(2.0/12.0 * len(sky))
        for i in range(0, ofs):
            a = sky.pop(i)
            sky.append(a)
        for dot in sky:
            pass
            #self.canvas.SetPixel(dot[0], dot[1], 100,100,100)

        day = (86400 - metrics['custom']['day_length']) / 86400.0 * 360

        ss = day / 2
        pos = int(round(ss/360.0 * (len(sky) - 1)))
        self.canvas.SetPixel(sky[pos][0], sky[pos][1], 100,0,0)

        sr = -day / 2
        pos = int(round(sr/360.0 * (len(sky) - 1)))
        self.canvas.SetPixel(sky[pos][0], sky[pos][1], 100,0,0)

        #cur = ss * metrics['ya_current']['day_length']

    def drawPrecip(self, metrics):
        # metrics['yandex']['radar']['current']['prec_type'] = 1
        # metrics['yandex']['radar']['current']['prec_strength'] = 1
        # metrics['yandex']['fact']['wind_speed'] = 5

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

        maxFlakes = int(30 * strength)
        minX = 0
        delay = 0.1
        if metrics['yandex']['radar']['current']['prec_type'] == 0:
            self.delay = 0.05
            return
        elif metrics['yandex']['radar']['current']['prec_type'] == 1:
            self.delay = 0.01
            delay = 0.01
        elif metrics['yandex']['radar']['current']['prec_type'] == 2:
            minX = 0 - self.ledH * 2
            self.delay = 0.04
            delay = 0.01
        elif metrics['yandex']['radar']['current']['prec_type'] == 3:
            self.delay = 0.05
            delay = 0.1

        now = time.time()

        if (len(self.snow) < maxFlakes) and (now - self.snowTimer >= self.ledH * delay / maxFlakes):
            startY = 0
            self.snow.append({'x': random.randint(minX, self.ledW - 1), 'y': startY, 'timer': time.time(), 'color': self.getColorByPrec(metrics['yandex']['radar']['current']['prec_type'])})
            self.snowTimer = now

        for i, f in enumerate(self.snow):
            self.canvas.SetPixel(f['x'], f['y'], f['color'][0], f['color'][1], f['color'][2])
            if now - self.snow[i]['timer'] < delay:
                continue
            self.snow[i]['timer'] = now

            if metrics['yandex']['radar']['current']['prec_type'] == 1:
                self.snow[i]['color'] = self.getColorByPrec(1)
                self.snow[i]['y'] += 1
                self.snow[i]['x'] += 0
            elif metrics['yandex']['radar']['current']['prec_type'] == 2:
                self.snow[i]['y'] += 1
                self.snow[i]['x'] += random.randint(0, int(metrics['yandex']['fact']['wind_speed']/4))
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

    def readArduino(self):
        jsn = self.mc.get('metrics')
        if not jsn:
            return False
        metrics = json.loads(jsn)
        if metrics['sensors']['t_out'] is not None:
            metrics['sensors']['t_out'] = int(round(metrics['sensors']['t_out'], 0))

        return metrics

    def defineBrightness(self, metrics, now):
        if self.userBrightness:
            self.matrix.brightness = self.userBrightness
            return
        # and now.minute >= 30
        self.bri = 1
        if 22 <= now.hour < 24:  # or (now.hour >=6 and now.hour < 9):
            self.matrix.brightness = 3
            self.bri = 1
        elif 0 <= now.hour <= 5:
            self.matrix.brightness = 2
            self.bri = 0.5
        else:
            self.bri = 1

            if not metrics['sensors']['light']:
                light = 20
            else:
                light = metrics['sensors']['light']
            self.defineBrightnessByLight(light)
        self.initColors()

    def defineBrightnessByLight(self, light):
        if light >= 400:
            self.matrix.brightness = 55
            self.bri = 2
        elif light >= 300:
            self.matrix.brightness = 55
            self.bri = 1
        elif light >= 200:
            self.matrix.brightness = 45
        elif light >= 100:
            self.matrix.brightness = 40
        elif light >= 50:
            self.matrix.brightness = 35
        elif light >= 25:
            self.matrix.brightness = 30
        elif light >= 20:
            self.matrix.brightness = 25
        elif light >= 15:
            self.matrix.brightness = 20
        else:
            self.matrix.brightness = 15

    def mqtt_connect(self, client, userdata, flags, rc):
        print("Connected with result code "+str(rc))
        config = {
            "~": "homeassistant/light/led-clock",
            "name": "Led clock",
            "unique_id": "led-clock",
            "command_topic": "~/set",
            "state_topic": "~/state",
            "schema": "json",
            "brightness": True
        }
        self.mqcl.subscribe(config['~'] + '/#')
        self.mqcl.publish('homeassistant/light/led-clock/config', json.dumps(config))

    def mqtt_message(self, client, userdata, msg):
        if re.match('.+state$', msg.topic):
            self.mqtt_state()
        elif re.match('.+set$', msg.topic):
            cmd = json.loads(msg.payload)
            if 'state' not in cmd:
                print('MQTT SET INVALID: ' + str(msg.payload))
                return
            if cmd['state'] == 'ON':
                if 'brightness' in cmd:
                    if cmd['brightness'] == 1:
                        self.bri = 0.5
                    else:
                        self.bri = 1
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
