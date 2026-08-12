#!/usr/bin/python3 -B
# coding: UTF-8

import requests
from rgbmatrix import graphics, RGBMatrix, RGBMatrixOptions
from PIL import Image
import time
import datetime
import json
import random
import os
import math
import paho.mqtt.client as mqtt

class RunText:
    def __init__(self):
        # p = psutil.Process()
        # p.nice(-20)
        # p.cpu_affinity([3])

        with open('../config-clock.json') as f:
            self.config = json.load(f)
            self.elements = self.config["elements"]

        self.map = {}
        self.colors = {}

        self.mqcl = None
        self.mqtt_root_topic = None
        self.mqtt_device = None
        self.mqtt_error = False

        self.icons = {}
        self.ledW = 128
        self.ledH = 64
        self.delay = 0.05

        self.debug_borders = self.config["debug_borders"]

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
        self.custom_text = ""
        self.simulate_precip = ""
        self.simulate_precip_strength = 0
        self.simulate_wind_speed = 0
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
            next_tick = now + self.delay * 1000
            self.clock()
            new = time.time_ns() // 1000000
            diff = next_tick-new
            self.canvas = self.matrix.SwapOnVSync(self.canvas)
            if diff < 0:
                if diff < -500:
                    print(f"LAG {abs(diff)}ms")
                continue
            time.sleep(diff / 1000)

    def clock(self):
        now = datetime.datetime.now()
        self.draw_clock('clock', now)

        self.mqtt_loop()
        if self.mqtt_error:
            graphics.DrawText(self.canvas, self.fontReg, 1, 28, self.get_color('clock'), 'MQTT ERROR')

        hass = self.read_hass()
        if not hass:
            graphics.DrawText(self.canvas, self.fontReg, 1, 36, self.get_color('clock'), 'NO HASS')
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
            text = f'{int(float(dev_co2))}ppm'
        else:
            text = 'N/A'
        width = self.calc_width(text, self.fontReg)
        coords = self.get_coords_by_element(id, w=width, h=self.fontRegH, element=self.elements[id])
        color = self.get_color(id)
        graphics.DrawText(self.canvas, self.fontReg, coords['x'], coords['y'], color, text)

    def draw_humidity(self, id):
        dev_hum = self.get_hass_entity_by_device(self.elements[id]['sensors']['main'])
        if dev_hum is not None:
            text = f'{int(round(float(dev_hum), 0))}%'
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
            text = f'{WIND_DIRECTION_MAPPING[dev_wind_bearing]} {int(round(float(dev_wind_speed), 0))}m/s'

        width = self.calc_width(text, self.fontReg)
        coords = self.get_coords_by_element(id, w=width, h=self.fontRegH, element=self.elements[id])
        color = self.get_color(id)
        graphics.DrawText(self.canvas, self.fontReg, coords['x'], coords['y'], color, text)

    def draw_temp_inside(self, id):
        dev_temp_inside = self.get_hass_entity_by_device(self.elements[id]['sensors']['main'])
        text = 'N/A'
        if dev_temp_inside is not None:
            text = f'{round(float(dev_temp_inside), 1)}°'

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
            text = f'{int(round(float(dev_temp_outside), 0))}°'

        width = self.calc_width(text, self.fontReg)
        coords = self.get_coords_by_element(id, w=width, h=self.fontRegH, element=self.elements[id])
        graphics.DrawText(self.canvas, self.fontReg, coords['x'], coords['y'], col, text)

        dev_current_icon = self.get_hass_entity_by_device(self.elements[id]['sensors']['icon'])
        if dev_current_icon is None:
            return
        coords = self.get_coords_by_element(f"{id}_icon", w=self.imgSize, h=self.imgSize, element=self.elements[id])
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
            fc1 = f"{self.format_day_time(dev_forecast['forecast'][1]['datetime'])}{int(round(dev_forecast['forecast'][1]['native_temperature']))}°"
            fc2 = f"{self.format_day_time(dev_forecast['forecast'][2]['datetime'])}{int(round(dev_forecast['forecast'][2]['native_temperature']))}°"
            icon1 = dev_forecast['forecast_icons'][0]
            icon2 = dev_forecast['forecast_icons'][1]

        coords = self.get_coords_by_element(f"{id}_row_1", w=self.calc_width(fc1, self.fontReg), h=self.fontRegH, element=weather_element)
        graphics.DrawText(self.canvas, self.fontReg, coords['x'], coords['y'], c, fc1)

        coords = self.get_coords_by_element(f"{id}_row_1_icon", w=self.imgSize, h=self.imgSize, element=weather_element)
        self.draw_image(self.get_icon(icon1), coords['x'], coords['y'])

        weather_element['row'] += 1
        coords = self.get_coords_by_element(f"{id}_row_2", w=self.calc_width(fc2, self.fontReg), h=self.fontRegH, element=weather_element)
        graphics.DrawText(self.canvas, self.fontReg, coords['x'], coords['y'], c, fc2)

        coords = self.get_coords_by_element(f"{id}_row_2_icon", w=self.imgSize, h=self.imgSize, element=weather_element)
        self.draw_image(self.get_icon(icon2), coords['x'], coords['y'])

        # TODO: hack because weather_element is passed by reference (why?)
        weather_element['row'] -= 1

    def get_icon(self, icon_name):
        #https://yastatic.net/weather/i/icons/islands/32/
        #https://yastatic.net/weather/i/icons/funky/png/dark/24/ovc_ts.png
        if icon_name in self.icons:
            return self.icons[icon_name]
        img_size = 8
        i8 = f'../icons8/{icon_name}_{img_size}.png'
        i24 = f'../icons/{icon_name}.png'
        if os.path.isfile(i8):
            i = Image.open(i8).resize((self.imgSize, self.imgSize), Image.Resampling.HAMMING)
        elif os.path.isfile(i24):
            i = Image.open(i24).resize((self.imgSize, self.imgSize), Image.Resampling.HAMMING)
        else:
            return self.get_icon('na')
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

    def angle_to_border(self, angle):
        cx, cy = (self.ledW - 1) / 2, (self.ledH - 1) / 2
        hw, hh = cx, cy
        rad = (angle + 180) * math.pi / 180
        dx = math.cos(rad)
        dy = math.sin(rad)
        if abs(dx) < 1e-9:
            x = cx
            y = cy + hh if dy > 0 else cy - hh
        elif abs(dy) < 1e-9:
            x = cx + hw if dx > 0 else cx - hw
            y = cy
        else:
            t = min(hw / abs(dx), hh / abs(dy))
            x = cx + dx * t
            y = cy + dy * t
        return (int(round(x)), int(round(y)))

    def draw_sky(self, id):
        sensors = self.elements[id]['sensors']
        sr_val = self.get_hass_entity_by_device(sensors['sun_rising'])
        ss_val = self.get_hass_entity_by_device(sensors['sun_setting'])
        if sr_val is None or ss_val is None:
            return

        sr = datetime.datetime.fromisoformat(sr_val)
        ss = datetime.datetime.fromisoformat(ss_val)
        cur_time = datetime.datetime.now(sr.tzinfo)

        if sr > ss:
            day_len = (ss - sr).total_seconds() + 86400
        else:
            day_len = (ss - sr).total_seconds()

        day_angle_span = day_len / 86400 * 360

        last_sr = sr if sr < cur_time else sr - datetime.timedelta(seconds=86400)
        sun_angle = (cur_time - last_sr).total_seconds() / 86400 * 360

        for mark_angle in (0, day_angle_span):
            for offset in (-0.5, 0.5):
                ma = mark_angle + offset
                mx, my = self.angle_to_border(ma)
                self.canvas.SetPixel(mx, my, 200, 60, 0)

        self.draw_sky_body(sun_angle, 255, 220, 0)

        mr_val = self.get_hass_entity_by_device(sensors['moon_rising'])
        ms_val = self.get_hass_entity_by_device(sensors['moon_setting'])
        if mr_val is None or ms_val is None:
            return

        mr = datetime.datetime.fromisoformat(mr_val)
        ms = datetime.datetime.fromisoformat(ms_val)

        if mr > ms:
            up_len = (ms - mr).total_seconds() + 86400
        else:
            up_len = (ms - mr).total_seconds()

        up_angle_span = up_len / 86400 * 360

        last_mr = mr if mr < cur_time else mr - datetime.timedelta(seconds=86400)
        moon_angle = (cur_time - last_mr).total_seconds() / 86400 * 360

        for mark_angle in (0, up_angle_span):
            for offset in (-0.5, 0.5):
                ma = mark_angle + offset
                mx, my = self.angle_to_border(ma)
                self.canvas.SetPixel(mx, my, 130, 130, 160)

        self.draw_sky_body(moon_angle, 180, 200, 255)

    def draw_sky_body(self, angle, r, g, b):
        cx, cy = self.angle_to_border(angle)
        self.canvas.SetPixel(cx, cy, r, g, b)
        for nx, ny in self.border_neighbors(cx, cy):
            self.canvas.SetPixel(nx, ny, r, g, b)

    def border_neighbors(self, x, y):
        candidates = [(x-1, y), (x+1, y), (x, y-1), (x, y+1)]
        result = []
        for nx, ny in candidates:
            if nx < 0 or nx >= self.ledW or ny < 0 or ny >= self.ledH:
                continue
            if nx == 0 or nx == self.ledW - 1 or ny == 0 or ny == self.ledH - 1:
                result.append((nx, ny))
        if len(result) >= 2:
            return result[:2]
        return result

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
            wind_speed = int(round(float(dev_wind_speed), 0))

        if self.simulate_precip != "":
            if self.simulate_precip == "rain":
                prec_type = 1
            elif self.simulate_precip == "wet_snow":
                prec_type = 2
            elif self.simulate_precip == "snow":
                prec_type = 3

            prec_strength = self.simulate_precip_strength
            if self.simulate_wind_speed > 0:
                wind_speed = self.simulate_wind_speed

        if prec_type is None or prec_strength is None or wind_speed is None or prec_strength == 0:
            self.raindrops.clear()
            return

        max_drops = int(self.ledH * prec_strength * 0.5)
        speed_rain = 100 # pixels per second
        speed_snow = 15
        speed_wet_snow = 25
        if prec_type == 0: # no precipitation
            self.delay = 0.5
            self.raindrops.clear()
            return
        self.delay = 0.02

        if prec_type == 1:
            spawn_speed = speed_rain
        elif prec_type == 2:
            spawn_speed = speed_wet_snow
        else:
            spawn_speed = speed_snow

        interval = self.ledH / (max_drops * spawn_speed)

        if wind_speed == 0:
            horizontal_step = 0
            horizontal_every = 1
        elif wind_speed <= 10:
            horizontal_step = 1
            horizontal_every = max(1, int(10 / wind_speed))
        else:
            horizontal_step = int(wind_speed / 10)
            horizontal_every = 1

        now_micro = time.time_ns() // 1000000
        if (len(self.raindrops) < max_drops) and (now_micro - self.snow_timer > interval * 1000):
            start_y = -1
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
            self.raindrops.append({'x': random.randint(0, self.ledW - 1), 'y': start_y, 'timer': time.time_ns() // 1000000, 'color': self.get_color_by_prec(drop_type), 'type': drop_type, 'delay': delay, 'h_accum': 0.0})
            self.snow_timer = now_micro

        for i in range(len(self.raindrops) - 1, -1, -1):
            f = self.raindrops[i]
            self.canvas.SetPixel(f['x'], f['y'], f['color'][0], f['color'][1], f['color'][2])
            delta = now_micro - f['timer']
            drop_delay = f['delay'] * 1000
            if delta < drop_delay:
                continue
            distance = int(round(delta / drop_delay))
            f['timer'] = now_micro

            f['color'] = self.get_color_by_prec(f['type'])
            if f['type'] == 'rain':
                f['y'] += distance
                if horizontal_step > 0:
                    f['h_accum'] += distance * horizontal_step / horizontal_every
                    dx = int(f['h_accum'])
                    f['x'] += dx
                    f['h_accum'] -= dx
            elif f['type'] == 'wet_snow':
                f['y'] += distance
                f['x'] += random.randint(-1, 1)
            elif f['type'] == 'snow':
                f['y'] += distance
                f['x'] += random.randint(-1, 1)

            if f['y'] > self.ledH - 1:
                self.raindrops.pop(i)
                continue

            f['x'] = f['x'] % self.ledW

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

        for mapId in self.map:
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
        return [0, 0, 0]

    def get_color(self, id, type=None):
        key = id
        if type is not None:
            key = f"{key}:{type}"
        if key in self.colors:
            return self.colors[key]

        elem = self.elements[id]
        color_key = "color"
        if type is not None:
            color_key = f"{type}_color"
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
            resp = requests.get(self.config['hass']['url'], headers={"Authorization": f"Bearer {self.config['hass']['token']}"}, timeout=10)
        except Exception as e:
            print(f"Cannot load hass: {e}")
            return None

        try:
            hass = resp.json()
        except Exception as e:
            print(f"Invalid hass states `{e}`: {resp.text}")
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
        self.mqtt_root_topic = f"led-clock/{self.mqtt_device['identifiers']}"

        self.mqcl = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, self.config['mqtt']['device_id'])
        self.mqcl.enable_logger()
        self.mqcl.on_connect = self.mqtt_connect
        self.mqcl.on_disconnect = self.mqtt_disconnect
        self.mqcl.on_message = self.mqtt_message
        self.mqcl.will_set(f"{self.mqtt_root_topic}/availability", payload=b"offline", retain=True)
        try:
            self.mqcl.connect(self.config['mqtt']['host'], self.config['mqtt']['port'], 60)
            self.mqtt_error = False
        except Exception as e:
            print(f"Cannot connect to mqtt: {e}")
            self.mqtt_error = True
            self.mqcl = None

    def mqtt_connect(self, client, userdata, flags, reason_code, properties):
        print(f"mqtt connected with result code {reason_code}")
        self.mqtt_discovery_brightness()
        self.mqtt_discovery_text()
        self.mqtt_discovery_simulate_precip()
        self.mqtt_discovery_simulate_precip_strength()
        self.mqtt_discovery_simulate_wind_speed()

    def mqtt_disconnect(self, client, userdata, flags, reason_code, properties):
        print("mqtt disconnected!!!")
        exit()

    def mqtt_message(self, client, userdata, msg):
        if msg.topic.endswith('/brightness_set'):
            cmd = json.loads(msg.payload)
            if 'state' not in cmd:
                print(f'MQTT BRIGHTNESS SET INVALID: {msg.payload}')
                return
            if cmd['state'] == 'ON':
                if 'brightness' in cmd:
                    self.userBrightness = cmd['brightness']
                    print(f'set bri: {self.userBrightness}')
                else:
                    self.userBrightness = self.matrix.brightness
            else:
                self.userBrightness = None
            self.report_brightness_state()
        elif msg.topic.endswith('/text_set'):
            print(f"MQTT TEXT SET {msg.payload}")
            self.custom_text = msg.payload.decode()
            self.report_text_state()
        elif msg.topic.endswith('/precip_set'):
            print(f"MQTT PRECIP SET {msg.payload}")
            self.simulate_precip = msg.payload.decode()
            self.report_simulate_precip_state()
        elif msg.topic.endswith('/precip_str_set'):
            print(f"MQTT PRECIP STR SET {msg.payload}")
            self.simulate_precip_strength = float(msg.payload.decode())
            self.report_simulate_precip_strength_state()
        elif msg.topic.endswith('/wind_set'):
            print(f"MQTT WIND SET {msg.payload}")
            self.simulate_wind_speed = float(msg.payload.decode())
            self.report_simulate_wind_speed_state()
        else:
            print(f'UNKNOWN MQTT RECEIVED: \t{msg.topic}\t{msg.payload}')

    def mqtt_discovery_brightness(self):
        discovery_topic = f"{self.config['mqtt']['hass_discovery_prefix']}/light/{self.mqtt_device['identifiers']}-brightness/config"
        service_config = {
            "name": "brightness",
            "unique_id": f"{self.mqtt_device['identifiers']}-brightness",
            "object_id": f"{self.mqtt_device['identifiers']}-brightness",
            "command_topic": f"{self.mqtt_root_topic}/brightness_set",
            "state_topic": f"{self.mqtt_root_topic}/brightness_state",
            "availability": {
                "topic": f"{self.mqtt_root_topic}/availability"
            },
            "schema": "json",
            "icon": "mdi:clock-digital",
            "brightness": True,
            "brightness_scale": 100,
            "device": self.mqtt_device
        }
        self.mqcl.subscribe(service_config['command_topic'])
        payload = json.dumps(service_config)
        print(f'publish discovery light {payload}')
        self.mqcl.publish(discovery_topic, payload=payload, retain=True)
        self.report_brightness_state()
        self.mqcl.publish(f"{self.mqtt_root_topic}/availability", payload=b'online', retain=True)

    def mqtt_discovery_text(self):
        discovery_topic = f"{self.config['mqtt']['hass_discovery_prefix']}/text/{self.mqtt_device['identifiers']}-text/config"
        service_config = {
            "name": "text",
            "unique_id": f"{self.mqtt_device['identifiers']}-text",
            "object_id": f"{self.mqtt_device['identifiers']}-text",
            "command_topic": f"{self.mqtt_root_topic}/text_set",
            "state_topic": f"{self.mqtt_root_topic}/text_state",
            "availability": {
                "topic": f"{self.mqtt_root_topic}/availability"
            },
            "schema": "json",
            "icon": "mdi:text-short",
            "device": self.mqtt_device
        }
        self.mqcl.subscribe(service_config['command_topic'])
        payload = json.dumps(service_config)
        print(f'publish discovery text {payload}')
        self.mqcl.publish(discovery_topic, payload=payload, retain=True)
        self.report_text_state()
        self.mqcl.publish(f"{self.mqtt_root_topic}/availability", payload=b'online', retain=True)

    def mqtt_discovery_simulate_precip(self):
        discovery_topic = f"{self.config['mqtt']['hass_discovery_prefix']}/select/{self.mqtt_device['identifiers']}-simulate-precip/config"
        service_config = {
            "name": "simulate precipitation",
            "unique_id": f"{self.mqtt_device['identifiers']}-simulate-precip",
            "object_id": f"{self.mqtt_device['identifiers']}-simulate-precip",
            "command_topic": f"{self.mqtt_root_topic}/precip_set",
            "state_topic": f"{self.mqtt_root_topic}/precip_state",
            "availability": {
                "topic": f"{self.mqtt_root_topic}/availability"
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
        print(f'publish discovery precip {payload}')
        self.mqcl.publish(discovery_topic, payload=payload, retain=True)
        self.report_simulate_precip_state()
        self.mqcl.publish(f"{self.mqtt_root_topic}/availability", payload=b'online', retain=True)

    def mqtt_discovery_simulate_precip_strength(self):
        discovery_topic = f"{self.config['mqtt']['hass_discovery_prefix']}/number/{self.mqtt_device['identifiers']}-precip-strength/config"
        service_config = {
            "name": "simulated precip strength",
            "unique_id": f"{self.mqtt_device['identifiers']}-precip-strength",
            "object_id": f"{self.mqtt_device['identifiers']}-precip-strength",
            "command_topic": f"{self.mqtt_root_topic}/precip_str_set",
            "state_topic": f"{self.mqtt_root_topic}/precip_str_state",
            "availability": {
                "topic": f"{self.mqtt_root_topic}/availability"
            },
            "min": 0.0,
            "max": 2.0,
            "step": 0.5,
            "mode": "slider",
            "schema": "json",
            "icon": "mdi:wind-power",
            "device": self.mqtt_device
        }
        self.mqcl.subscribe(service_config['command_topic'])
        payload = json.dumps(service_config)
        print(f'publish discovery precip strength {payload}')
        self.mqcl.publish(discovery_topic, payload=payload, retain=True)
        self.report_simulate_precip_strength_state()
        self.mqcl.publish(f"{self.mqtt_root_topic}/availability", payload=b'online', retain=True)

    def report_brightness_state(self):
        if self.userBrightness:
            state = {"state": "ON", "brightness": self.userBrightness}
        else:
            state = {"state": "OFF"}
        payload = json.dumps(state)
        print(f'publish light state {payload}')
        self.mqcl.publish(f"{self.mqtt_root_topic}/brightness_state", payload=payload)

    def report_text_state(self):
        payload = self.custom_text
        print(f'publish text state `{payload}`')
        self.mqcl.publish(f"{self.mqtt_root_topic}/text_state", payload=payload)

    def report_simulate_precip_state(self):
        payload = self.simulate_precip
        print(f'publish precip state `{payload}`')
        self.mqcl.publish(f"{self.mqtt_root_topic}/precip_state", payload=payload)

    def report_simulate_precip_strength_state(self):
        payload = self.simulate_precip_strength
        print(f'publish precip strength state `{payload}`')
        self.mqcl.publish(f"{self.mqtt_root_topic}/precip_str_state", payload=payload)

    def mqtt_discovery_simulate_wind_speed(self):
        discovery_topic = f"{self.config['mqtt']['hass_discovery_prefix']}/number/{self.mqtt_device['identifiers']}-wind-speed/config"
        service_config = {
            "name": "simulated wind speed",
            "unique_id": f"{self.mqtt_device['identifiers']}-wind-speed",
            "object_id": f"{self.mqtt_device['identifiers']}-wind-speed",
            "command_topic": f"{self.mqtt_root_topic}/wind_set",
            "state_topic": f"{self.mqtt_root_topic}/wind_state",
            "availability": {
                "topic": f"{self.mqtt_root_topic}/availability"
            },
            "min": 0.0,
            "max": 30.0,
            "step": 1.0,
            "mode": "slider",
            "schema": "json",
            "icon": "mdi:weather-windy",
            "device": self.mqtt_device
        }
        self.mqcl.subscribe(service_config['command_topic'])
        payload = json.dumps(service_config)
        print(f'publish discovery wind speed {payload}')
        self.mqcl.publish(discovery_topic, payload=payload, retain=True)
        self.report_simulate_wind_speed_state()
        self.mqcl.publish(f"{self.mqtt_root_topic}/availability", payload=b'online', retain=True)

    def report_simulate_wind_speed_state(self):
        payload = self.simulate_wind_speed
        print(f'publish wind speed state `{payload}`')
        self.mqcl.publish(f"{self.mqtt_root_topic}/wind_state", payload=payload)


if __name__ == "__main__":
    run_text = RunText()
    run_text.run()
