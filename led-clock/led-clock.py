#!/usr/bin/python3 -B
# coding: UTF-8
import re

import requests
from rgbmatrix import graphics, RGBMatrix, RGBMatrixOptions
from PIL import Image
import time, datetime, json, textwrap, random, os, collections
import paho.mqtt.client as mqtt

class RunText:
    def __init__(self):
        # p = psutil.Process()
        # p.nice(-20)
        # p.cpu_affinity([3])

        with open('../config-clock.json') as f:
            s = f.read()
            self.config = json.loads(s)
            self.elements = self.config["elements"]

        self.map = collections.OrderedDict()
        self.colors = collections.OrderedDict()

        self.mqcl = None
        self.mqtt_root_topic = None
        self.mqtt_device = None
        self.mqtt_error = False

        self.icons = {}
        self.ledW = 128
        self.ledH = 64
        self.delay = 0.05

        self.debug_borders = False

        self.fontClock = graphics.Font()
        self.fontClock.LoadFont("./fonts/win_crox5h.bdf")
        self.fontClockH = 19
        self.fontReg = graphics.Font()
        self.fontReg.LoadFont("./fonts/helvR08.bdf")
        self.fontRegH = 9
        self.fontSm = graphics.Font()
        self.fontSm.LoadFont("./fonts/b10.bdf")
        self.fontSmH = 8

        self.imgSize = 8

        self.rowH = self.fontRegH + 1

        self.userBrightness = None
        self.custom_text = u""
        self.sumulate_precip = ""
        self.sumulate_precip_strength = 0
        self.extra_dim = False
        self.raindrops = []
        self.snow_timer = time.time_ns() // 1000000

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
            self.canvas.Clear()

            now = time.time_ns() // 1000000
            next = now + self.delay * 1000
            self.clock()
            new = time.time_ns() // 1000000
            diff = next-new
            self.canvas = self.matrix.SwapOnVSync(self.canvas)
            if diff < 0:
                if diff < -500:
                    print("LAG " + str(abs(diff)) + "ms")
                continue
            # print("SLEEP " + str(diff) + "ms")
            time.sleep(diff / 1000)

    def clock(self):
        now = datetime.datetime.now()
        self.draw_clock('clock', now)

        self.mqtt_loop()
        if self.mqtt_error:
            graphics.DrawText(self.canvas, self.fontReg, 1, 28, self.get_color('clock'), u'MQTT ERROR')

        hass = self.read_hass()
        if not hass:
            graphics.DrawText(self.canvas, self.fontReg, 1, 36, self.get_color('clock'), u'NO HASS')
            return
        self.define_brightness(now)
        self.draw_entities(now)

    def draw_entities(self, now):
        for id, entity in self.elements.items():
            if 'type' not in entity:
                continue
            if entity['type'] == 'temperature_inside' and not self.extra_dim:
                self.draw_temp_inside(id)
            elif entity['type'] == 'temperature_outside' and not self.extra_dim:
                self.draw_temp_outside(id, now)
            elif entity['type'] == 'co2' and not self.extra_dim:
                self.draw_co2(id)
            elif entity['type'] == 'humidity' and not self.extra_dim:
                self.draw_humidity(id)
            elif entity['type'] == 'wind' and not self.extra_dim:
                self.draw_wind(id)
            elif entity['type'] == 'sky':
                self.draw_sky(id)
            elif entity['type'] == 'precipitations':
                self.draw_precip(id)
            elif entity['type'] == 'mqtt_text' and not self.extra_dim:
                self.draw_mqtt_text(id)
            elif entity['type'] == 'forecast' and not self.extra_dim:
                self.draw_forecast(id)
            elif entity['type'] == 'date' and not self.extra_dim:
                self.draw_date(id, now)


    def draw_clock(self, id, now):
        text = now.strftime("%H:%M")
        width = self.calc_width(text, self.fontClock)
        coords = self.get_coords_by_element(id, w=width, h=self.fontClockH, element=self.elements[id])
        color = self.get_color(id)
        graphics.DrawText(self.canvas, self.fontClock, coords['x'], coords['y'], color, text)

    def draw_date(self, id, now):
        text = now.strftime("%a %d %b")
        width = self.calc_width(text, self.fontReg)
        coords = self.get_coords_by_element(id, w=width, h=self.fontRegH, element=self.elements[id])
        color = self.get_color(id)
        graphics.DrawText(self.canvas, self.fontReg, coords['x'], coords['y'], color, text)

    def draw_mqtt_text(self, id):
        if self.custom_text == '':
            return
        color = self.get_color(id)
        width = self.calc_width(self.custom_text, self.fontSm)
        cut_at = len(self.custom_text) - 1
        was_cut = False
        if width > self.ledW:
            was_cut = True
            while width > self.ledW or cut_at == 0:
                cut_at -= 1
                if self.custom_text[cut_at] != " ":
                    continue
                width = self.calc_width(self.custom_text[:cut_at], self.fontSm)
            if cut_at == 0:
                cut_at = len(self.custom_text) - 1
                #nowhere to cut by space
                while width > self.ledW or cut_at == 0:
                    cut_at -= 1
                    width = self.calc_width(self.custom_text[:cut_at], self.fontSm)

        if was_cut:
            coords = self.get_coords_by_element(id, w=width, h=self.fontSmH, element=self.elements[id])
            graphics.DrawText(self.canvas, self.fontSm, coords['x'], coords['y'] + 3 - self.fontSmH + 2, color, self.custom_text[:cut_at])
            graphics.DrawText(self.canvas, self.fontSm, coords['x'], coords['y'] + 3, color, self.custom_text[cut_at:])
        else:
            coords = self.get_coords_by_element(id, w=width, h=self.fontSmH, element=self.elements[id])
            graphics.DrawText(self.canvas, self.fontSm, coords['x'], coords['y'], color, self.custom_text)

    def draw_co2(self, id):
        dev_co2 = self.get_hass_entity_by_device(self.elements[id]['sensors']['main'])
        if dev_co2 is not None:
            text = u'{0}ppm'.format(int(float(dev_co2)))
        else:
            text = 'N/A'
        width = self.calc_width(text, self.fontReg)
        coords = self.get_coords_by_element(id, w=width, h=self.fontRegH, element=self.elements[id])
        color = self.get_color(id)
        graphics.DrawText(self.canvas, self.fontReg, coords['x'], coords['y'], color, text)

    def draw_humidity(self, id):
        dev_hum = self.get_hass_entity_by_device(self.elements[id]['sensors']['main'])
        if dev_hum is not None:
            text = u'{0}%'.format(int(round(float(dev_hum), 0)))
        else:
            text = 'N/A'
        width = self.calc_width(text, self.fontReg)
        coords = self.get_coords_by_element(id, h=self.fontRegH, w=width, element=self.elements[id])
        color = self.get_color(id)
        graphics.DrawText(self.canvas, self.fontReg, coords['x'], coords['y'], color, text)

    def draw_wind(self, id):
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
        dev_wind_speed = self.get_hass_entity_by_device(self.elements[id]['sensors']['speed'])
        dev_wind_bearing = self.get_hass_entity_by_device(self.elements[id]['sensors']['bearing'])
        text = 'N/A'
        if dev_wind_bearing is not None and dev_wind_speed is not None:
            text = u'{1} {0}m/s'.format(int(round(float(dev_wind_speed), 0)), WIND_DIRECTION_MAPPING[dev_wind_bearing])

        width = self.calc_width(text, self.fontReg)
        coords = self.get_coords_by_element(id, w=width, h=self.fontRegH, element=self.elements[id])
        color = self.get_color(id)
        graphics.DrawText(self.canvas, self.fontReg, coords['x'], coords['y'], color, text)

    def draw_temp_inside(self, id):
        dev_temp_inside = self.get_hass_entity_by_device(self.elements[id]['sensors']['main'])
        text = 'N/A'
        if dev_temp_inside is not None:
            text = u'{0}°'.format(round(float(dev_temp_inside), 1))

        width = self.calc_width(text, self.fontReg)
        coords = self.get_coords_by_element(id, w=width, h=self.fontRegH, element=self.elements[id])
        color = self.get_color(id)
        # color_dot = self.get_color(id, 'dot')
        graphics.DrawText(self.canvas, self.fontReg, coords['x'], coords['y'], color, text)
        # TODO: mismatched position with narrow digits, eg: 21.1
        # graphics.DrawText(self.canvas, self.fontReg, coords['x'], coords['y'], color_dot, '    . ')

    def draw_temp_outside(self, id, now):
        if now.second % 10 >= 5:
            col = self.get_color(id)
            dev_temp_outside = self.get_hass_entity_by_device(self.elements[id]['sensors']['measured'])
        else:
            col = self.get_color(id, 'provided')
            dev_temp_outside = self.get_hass_entity_by_device(self.elements[id]['sensors']['provided'])

        text = 'N/A'
        if dev_temp_outside is not None:
            text = u'{0}°'.format(int(round(float(dev_temp_outside), 0)))

        width = self.calc_width(text, self.fontReg)
        coords = self.get_coords_by_element(id, w=width, h=self.fontRegH, element=self.elements[id])
        graphics.DrawText(self.canvas, self.fontReg, coords['x'], coords['y'], col, text)

        dev_current_icon = self.get_hass_entity_by_device(self.elements[id]['sensors']['icon'])
        if dev_current_icon is None:
            return
        coords = self.get_coords_by_element("{0}_icon".format(id), w=self.imgSize, h=self.imgSize, element=self.elements[id])
        self.draw_image(self.get_icon(dev_current_icon), coords['x'], coords['y'])

    def draw_forecast(self, id):
        c = self.get_color(id)
        dev_forecast = self.get_hass_entity_by_device(self.elements[id]['sensors']['forecast'])


        weather_element = self.elements[id]

        if dev_forecast is None or len(dev_forecast['forecast']) < 2:
            fc1 = 'N/A'
            fc2 = 'N/A'
            icon1 = 'na'
            icon2 = 'na'
        else:
            # access forecast objects starting from index 1, because first object (with index 0) is probably the current weather
            fc1 = u'{0}{1}°'.format(self.format_day_time(dev_forecast['forecast'][1]['datetime']), int(round(dev_forecast['forecast'][1]['native_temperature'])))
            fc2 = u'{0}{1}°'.format(self.format_day_time(dev_forecast['forecast'][2]['datetime']), int(round(dev_forecast['forecast'][2]['native_temperature'])))
            icon1 = dev_forecast['forecast_icons'][0]
            icon2 = dev_forecast['forecast_icons'][1]

        coords = self.get_coords_by_element("{0}_row_1".format(id), w=self.calc_width(fc1, self.fontReg), h=self.fontRegH, element=weather_element)
        graphics.DrawText(self.canvas, self.fontReg, coords['x'], coords['y'], c, fc1)

        coords = self.get_coords_by_element("{0}_row_1_icon".format(id), w=self.imgSize, h=self.imgSize, element=weather_element)
        self.draw_image(self.get_icon(icon1), coords['x'], coords['y'])

        weather_element['row'] += 1
        coords = self.get_coords_by_element("{0}_row_2".format(id), w=self.calc_width(fc2, self.fontReg), h=self.fontRegH, element=weather_element)
        graphics.DrawText(self.canvas, self.fontReg, coords['x'], coords['y'], c, fc2)

        coords = self.get_coords_by_element("{0}_row_2_icon".format(id), w=self.imgSize, h=self.imgSize, element=weather_element)
        self.draw_image(self.get_icon(icon2), coords['x'], coords['y'])

        # TODO: hack because weather_element is passed by reference (why?)
        weather_element['row'] -= 1

    def get_icon(self, icon_name):
        #https://yastatic.net/weather/i/icons/islands/32/
        if icon_name in self.icons:
            return self.icons[icon_name]
        img_size = 8
        i8 = '../icons8/{0}_{1}.png'.format(icon_name, img_size)
        if os.path.isfile(i8):
            i = Image.open(i8).resize((self.imgSize, self.imgSize), Image.HAMMING)
        else:
            i = Image.open('../icons/' + icon_name + '.png').resize((self.imgSize, self.imgSize), Image.HAMMING)
        m = Image.new('RGB', i.size, "BLACK")
        m.paste(i, (0, 0), i)
        self.icons[icon_name] = m
        return self.icons[icon_name]

    def draw_image(self, image, pos_x, pos_y):
        img_width, img_height = image.size
        pos_y -= self.imgSize
        pixels = image.load()
        for x in range(max(0, -pos_x), min(img_width, self.ledW - pos_x)):
            for y in range(max(0, -pos_y), min(img_height, self.ledH - pos_y)):
                (r, g, b) = pixels[x, y]
                if r == g == b == 0:
                    continue
                self.canvas.SetPixel(x + pos_x, y + pos_y, self.c(r, 0.7), self.c(g, 0.7), self.c(b, 0.7))

    def draw_sky(self, id):
        dev_sun = self.get_hass_entity_by_device(self.elements[id]['sensors']['sun_period'])
        if dev_sun is None:
            return

        cur_time = datetime.datetime.now()

        sr = datetime.datetime.fromisoformat(dev_sun['next_rising'])
        ss = datetime.datetime.fromisoformat(dev_sun['next_setting'])
        day_len = 0
        day = True
        if sr > ss:
            #day
            day_len = (ss-sr).total_seconds()+86400
        elif sr < ss:
            #night
            day = False
            day_len = (ss-sr).total_seconds()
        night_len = 86400 - day_len

        if day:
            r=255
            g=150
            b=0
            perc = (cur_time.timestamp() + 86400 - sr.timestamp()) / day_len
        else:
            r=0
            g=0
            b=150
            perc = 1 - (sr.timestamp() - cur_time.timestamp()) / night_len

        dot = int(round(round(self.ledW * perc)))
        self.canvas.SetPixel(dot, 0, r, g, b)
        self.canvas.SetPixel(dot-1, 0, r, g, b)
        self.canvas.SetPixel(dot+1, 0, r, g, b)

    def draw_precip(self, id):
        prec_type = None
        prec_strength = None
        wind_speed = None

        dev_prec_type = self.get_hass_entity_by_device(self.elements[id]['sensors']['precipitation_type'])
        if dev_prec_type is not None:
            prec_type = int(dev_prec_type)

        dev_prec_strength = self.get_hass_entity_by_device(self.elements[id]['sensors']['precipitation_strength'])
        if dev_prec_strength is not None:
            prec_strength = float(dev_prec_strength)

        dev_wind_speed = self.get_hass_entity_by_device(self.elements[id]['sensors']['wind_speed'])
        if dev_wind_speed is not None:
            wind_speed = int(round(dev_wind_speed, 0))

        if self.sumulate_precip != "":
            if self.sumulate_precip == "rain":
                prec_type = 1
            elif self.sumulate_precip == "wet_snow":
                prec_type = 2
            elif self.sumulate_precip == "snow":
                prec_type = 3

            prec_strength = self.sumulate_precip_strength

        if prec_type is None or prec_strength is None or wind_speed is None or prec_strength == 0:
            return

        max_drops = int(self.ledH * prec_strength)
        min_x = 0
        speed_rain = 100 # pixels per second
        speed_snow = 15
        speed_wet_snow = 25
        if prec_type == 0: # no precipitation
            self.delay = 0.5
            return
        self.delay = 0.02

        interval = self.ledH / (max_drops * speed_snow)

        horizontal_speed = int(wind_speed/2)
        if horizontal_speed > 0:
            min_x = - self.ledH

        now_micro = time.time_ns() // 1000000
        if (len(self.raindrops) < max_drops) and (now_micro - self.snow_timer > interval * 1000):
            start_y = 0
            if prec_type == 1:
                drop_type = 'rain'
                speed = speed_rain
            elif prec_type == 2:
                if random.randint(0, 1) == 1:
                    drop_type = 'rain'
                    speed = speed_rain
                else:
                    drop_type = 'wet_snow'
                    speed = speed_wet_snow
            elif prec_type == 3:
                drop_type = 'snow'
                speed = speed_snow
            else:
                # impossible
                return
            delay = 1 / speed
            # print("{0}: {1}".format(drop_type, str(delay)))
            # interval = self.ledH / (max_drops * speed)
            self.raindrops.append({'x': random.randint(min_x, self.ledW - 1), 'y': start_y, 'timer': time.time_ns() // 1000000, 'color': self.get_color_by_prec(drop_type), 'type': drop_type, 'delay': delay})
            self.snow_timer = now_micro

        for i, f in enumerate(self.raindrops):
            self.canvas.SetPixel(f['x'], f['y'], f['color'][0], f['color'][1], f['color'][2])
            delta = now_micro - self.raindrops[i]['timer']
            drop_delay = self.raindrops[i]['delay'] * 1000
            if delta < drop_delay:
                continue
            distance = int(round(delta / drop_delay))
            # realSpeed = 1 / (now_micro - self.raindrops[i]['timer'])
            # print('real speed: ' + str(realSpeed))
            self.raindrops[i]['timer'] = now_micro

            self.raindrops[i]['color'] = self.get_color_by_prec(self.raindrops[i]['type'])
            if self.raindrops[i]['type'] == 'rain':
                self.raindrops[i]['y'] += distance
                self.raindrops[i]['x'] += 0 if horizontal_speed == 0 or self.raindrops[i]['y'] % horizontal_speed == 0 else 1
            if self.raindrops[i]['type'] == 'wet_snow':
                self.raindrops[i]['y'] += distance
                self.raindrops[i]['x'] += random.randint(-1, 1)
            if self.raindrops[i]['type'] == 'snow':
                self.raindrops[i]['y'] += distance
                self.raindrops[i]['x'] += random.randint(-1, 1)

            if self.raindrops[i]['y'] > self.ledH - 1:
                self.raindrops.pop(i)

    def get_coords(self, id, w, h):
        return self.get_coords_by_element(id, w, h, self.elements[id])

    def get_coords_by_element(self, id, w,  h, element):
        color = element["border_color"]
        align_x = element["align_x"]
        row = element["row"]
        rowspan = element["rowspan"] if "rowspan" in element else 1
        align_y = element["align_y"] if "align_y" in element else "bottom"
        if align_x == 'left':
            x = 1
        else:
            x = self.ledW - 1 - w
        y = self.rowH * (row+rowspan)
        if align_y == 'top' and rowspan > 1 and self.rowH * rowspan > h:
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

        if not self.debug_borders:
            return coords

        c = graphics.Color(color[0], color[1], color[2])
        graphics.DrawLine(self.canvas, coords['x'], coords['y'], coords['x'] + w, coords['y'], c)
        graphics.DrawLine(self.canvas, coords['x'], coords['y'] - h, coords['x'] + w, coords['y'] - h, c)
        graphics.DrawLine(self.canvas, coords['x'], coords['y'], coords['x'], coords['y'] - h, c)
        graphics.DrawLine(self.canvas, coords['x'] + w, coords['y'] - h, coords['x'] + w, coords['y'], c)

        return coords

    def get_color_by_prec(self, prec_type):
        if prec_type == 'rain':
            return [0, random.randint(100, 150), random.randint(200, 255)]
        elif prec_type == 'wet_snow':
                return [random.randint(100, 150), random.randint(100, 150), random.randint(100, 150)]
        elif prec_type == 'snow':
            c = random.randint(50, 255)
            return [c, c, c]

    def get_color(self, id, type=None):
        key = id
        if type is not None:
            key = key + ":" + type
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

    def c(self, col, coeff=1):
        if col*coeff>255:
            return 255
        return col*coeff

    def calc_width(self, text, font):
        w = 0
        for char in text:
            w += font.CharacterWidth(ord(char))
        return w

    def format_day_time(self, time_str):
        #2024-04-10T08:58:40+03:00

        # %:z is not supported on versions lower than 3.12, so remove colon
        r_idx = time_str.rfind(':')
        time_str = time_str[:r_idx] + time_str[r_idx+1:]

        dt = datetime.datetime.strptime(time_str, '%Y-%m-%dT%H:%M:%S.%f%z')
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

    def define_brightness(self, now):
        self.extra_dim = False
        if self.userBrightness:
            if self.userBrightness == 1:
                self.matrix.brightness = 1
                self.extra_dim = True
            else:
                self.matrix.brightness = self.userBrightness
            return

        dev_sun = self.get_hass_entity('sun_current')
        if 0 <= now.hour < 6:
            if dev_sun == 'below_horizon':
                self.matrix.brightness = 1
                self.extra_dim = True
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

    def get_hass_entity(self, config_key):
        if config_key not in self.config['devices']:
            return None
        device = self.config['devices'][config_key]
        return self.get_hass_entity_by_device(device)

    def get_hass_entity_by_device(self, device):
        entity_key = device['id']
        if entity_key not in self.hass:
            return None
        entity = self.hass[entity_key]
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

    def read_hass(self):
        now = time.time()
        if self.hassUpdated + self.config['metrics_period'] > now:
            return self.hass
        try:
            resp = requests.get(self.config['hass']['url'], headers={"Authorization": "Bearer {0}".format(self.config['hass']['token'])}, timeout=10)
        except Exception as e:
            print("Cannot load hass: {0}".format(str(e)))

            return None

        if not resp:
            return False

        try:
            hass = resp.json()
        except Exception as e:
            print("Invalid hass states `{0}`: {1}".format(str(e), resp.text))
            return None

        hass_assoc = {}
        for entity in hass:
            hass_assoc[entity['entity_id']] = entity

        self.hassUpdated = now
        self.hass = hass_assoc

        return hass_assoc

    def mqtt_loop(self):
        if not self.config['mqtt']['enabled']:
            return
        if self.mqcl is not None:
            self.mqcl.loop(0)
            return

        self.mqtt_device = {
            "identifiers": self.config['mqtt']['device_id'],
            "manufacturer": "noname",
            "model": "rpi",
            "name": "LED Panel clock",
            "sw_version": "0.1.0",
        }
        self.mqtt_root_topic = "led-clock/{0}".format(self.mqtt_device['identifiers'])

        self.mqcl = mqtt.Client(self.config['mqtt']['device_id'])
        self.mqcl.enable_logger()
        self.mqcl.on_connect = self.mqtt_connect
        self.mqcl.on_disconnect = self.mqtt_disconnect
        self.mqcl.on_message = self.mqtt_message
        self.mqcl.will_set("{0}/availability".format(self.mqtt_root_topic), payload=b"offline", retain=True)
        try:
            self.mqcl.connect(self.config['mqtt']['host'], self.config['mqtt']['port'], 60)
            self.mqtt_error = False
        except Exception as e:
            print("Cannot connect to mqtt: {0}".format(str(e)))
            self.mqtt_error = True
            self.mqcl = None

    def mqtt_connect(self, client, userdata, flags, rc):
        print("mqtt connected with result code "+str(rc))
        self.mqtt_discovery_brightness()
        self.mqtt_discovery_text()
        self.mqtt_discovery_simulate_precip()
        self.mqtt_discovery_simulate_precip_strength()

    def mqtt_disconnect(self, client, userdata, rc):
        print("mqtt disconnected!!!")
        exit()

    def mqtt_message(self, client, userdata, msg):
        # print('MQTT RECEIVED: ' + "\t" + str(msg.topic) + "\t" + str(msg.payload))
        if re.match('.+/brightness_set$', msg.topic):
            cmd = json.loads(msg.payload)
            if 'state' not in cmd:
                print('MQTT BRIGHTNESS SET INVALID: ' + str(msg.payload))
                return
            if cmd['state'] == 'ON':
                if 'brightness' in cmd:
                    self.userBrightness = cmd['brightness']
                    print('set bri: ' + str(self.userBrightness))
                else:
                    self.userBrightness = self.matrix.brightness
            else:
                self.userBrightness = None
            self.report_brightness_state()
        elif re.match('.+/text_set$', msg.topic):
            print("MQTT TEXT SET " + str(msg.payload))
            self.custom_text = msg.payload.decode()
            self.report_text_state()
        elif re.match('.+/precip_set$', msg.topic):
            print("MQTT PRECIP SET " + str(msg.payload))
            self.sumulate_precip = msg.payload.decode()
            self.report_simulate_precip_state()
        elif re.match('.+/precip_str_set$', msg.topic):
            print("MQTT PRECIP STR SET " + str(msg.payload))
            self.sumulate_precip_strength = float(msg.payload.decode())
            self.report_simulate_precip_strength_state()
        else:
            print('UNKNOWN MQTT RECEIVED: ' + "\t" + str(msg.topic) + "\t" + str(msg.payload))

    def mqtt_discovery_brightness(self):
        discovery_topic = "{0}/light/{1}-brightness/config".format(self.config['mqtt']['hass_discovery_prefix'], self.mqtt_device['identifiers'])
        service_config = {
            "name": "brightness",
            "unique_id": "{0}-brightness".format(self.mqtt_device['identifiers']),
            "object_id": "{0}-brightness".format(self.mqtt_device['identifiers']),
            "command_topic": "{0}/brightness_set".format(self.mqtt_root_topic),
            "state_topic": "{0}/brightness_state".format(self.mqtt_root_topic),
            "availability": {
                "topic": "{0}/availability".format(self.mqtt_root_topic)
            },
            "schema": "json",
            "icon": "mdi:clock-digital",
            "brightness": True,
            "brightness_scale": 100,
            "device": self.mqtt_device
        }
        self.mqcl.subscribe(service_config['command_topic'])
        payload = json.dumps(service_config)
        print('publish discovery light ' + payload)
        self.mqcl.publish(discovery_topic, payload=payload, retain=True)
        self.report_brightness_state()
        self.mqcl.publish("{0}/availability".format(self.mqtt_root_topic), payload=b'online', retain=True)

    def mqtt_discovery_text(self):
        discovery_topic = "{0}/text/{1}-text/config".format(self.config['mqtt']['hass_discovery_prefix'], self.mqtt_device['identifiers'])
        service_config = {
            "name": "text",
            "unique_id": "{0}-text".format(self.mqtt_device['identifiers']),
            "object_id": "{0}-text".format(self.mqtt_device['identifiers']),
            "command_topic": "{0}/text_set".format(self.mqtt_root_topic),
            "state_topic": "{0}/text_state".format(self.mqtt_root_topic),
            "availability": {
                "topic": "{0}/availability".format(self.mqtt_root_topic)
            },
            "schema": "json",
            "icon": "mdi:text-short",
            "device": self.mqtt_device
        }
        self.mqcl.subscribe(service_config['command_topic'])
        payload = json.dumps(service_config)
        print('publish discovery text ' + payload)
        self.mqcl.publish(discovery_topic, payload=payload, retain=True)
        self.report_text_state()
        self.mqcl.publish("{0}/availability".format(self.mqtt_root_topic), payload=b'online', retain=True)

    def mqtt_discovery_simulate_precip(self):
        discovery_topic = "{0}/select/{1}-simulate-precip/config".format(self.config['mqtt']['hass_discovery_prefix'], self.mqtt_device['identifiers'])
        service_config = {
            "name": "simulate precipitation",
            "unique_id": "{0}-simulate-precip".format(self.mqtt_device['identifiers']),
            "object_id": "{0}-simulate-precip".format(self.mqtt_device['identifiers']),
            "command_topic": "{0}/precip_set".format(self.mqtt_root_topic),
            "state_topic": "{0}/precip_state".format(self.mqtt_root_topic),
            "availability": {
                "topic": "{0}/availability".format(self.mqtt_root_topic)
            },
            "options": [
                "",
                "snow",
                "rain",
                "wet_snow",
            ],
            "schema": "json",
            "icon": "mdi:sun-snowflake",
            "device": self.mqtt_device
        }
        self.mqcl.subscribe(service_config['command_topic'])
        payload = json.dumps(service_config)
        print('publish discovery precip ' + payload)
        self.mqcl.publish(discovery_topic, payload=payload, retain=True)
        self.report_simulate_precip_state()
        self.mqcl.publish("{0}/availability".format(self.mqtt_root_topic), payload=b'online', retain=True)

    def mqtt_discovery_simulate_precip_strength(self):
        discovery_topic = "{0}/number/{1}-precip-strength/config".format(self.config['mqtt']['hass_discovery_prefix'], self.mqtt_device['identifiers'])
        service_config = {
            "name": "simulated precip strength",
            "unique_id": "{0}-precip-strength".format(self.mqtt_device['identifiers']),
            "object_id": "{0}-precip-strength".format(self.mqtt_device['identifiers']),
            "command_topic": "{0}/precip_str_set".format(self.mqtt_root_topic),
            "state_topic": "{0}/precip_str_state".format(self.mqtt_root_topic),
            "availability": {
                "topic": "{0}/availability".format(self.mqtt_root_topic)
            },
            "min": 0.0,
            "max": 5.0,
            "mode": "slider",
            "schema": "json",
            "icon": "mdi:wind-power",
            "device": self.mqtt_device
        }
        self.mqcl.subscribe(service_config['command_topic'])
        payload = json.dumps(service_config)
        print('publish discovery precip strength ' + payload)
        self.mqcl.publish(discovery_topic, payload=payload, retain=True)
        self.report_simulate_precip_strength_state()
        self.mqcl.publish("{0}/availability".format(self.mqtt_root_topic), payload=b'online', retain=True)

    def report_brightness_state(self):
        if self.userBrightness:
            state = {"state": "ON", "brightness": self.userBrightness}
        else:
            state = {"state": "OFF"}
        payload = json.dumps(state)
        print('publish light state ' + payload)
        self.mqcl.publish("{0}/brightness_state".format(self.mqtt_root_topic), payload=payload)

    def report_text_state(self):
        payload = self.custom_text
        print('publish text state `{0}`'.format(payload))
        self.mqcl.publish("{0}/text_state".format(self.mqtt_root_topic), payload=payload)

    def report_simulate_precip_state(self):
        payload = self.sumulate_precip
        print('publish precip state `{0}`'.format(payload))
        self.mqcl.publish("{0}/precip_state".format(self.mqtt_root_topic), payload=payload)

    def report_simulate_precip_strength_state(self):
        payload = self.sumulate_precip_strength
        print('publish precip strength state `{0}`'.format(payload))
        self.mqcl.publish("{0}/precip_str_state".format(self.mqtt_root_topic), payload=payload)


if __name__ == "__main__":
    run_text = RunText()
    run_text.run()
