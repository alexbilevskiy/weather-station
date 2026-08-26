# ESPHome HUB75 + LVGL Migration Plan

> ## WARNING: AI GENERATED

Migrating the weather station from Python/RPi (`led-clock.py` + `rpi-rgb-led-matrix`) to ESPHome with LVGL on ESP32-S3.

## Source Project

- **Main file**: `led-clock/led-clock.py` (1060 lines, single `RunText` class)
- **Config**: `config-clock.json` (elements layout, device mappings, MQTT, HA URL/token)
- **Display**: 128x64 HUB75 LED panel
- **Data source**: Home Assistant HTTP API (`/api/states`) polled every 30s
- **MQTT**: Auto-discovery for brightness, text, precip simulation, RGB light, debug borders
- **FPS**: ~20fps (delay=0.05s, drops to 0.02s during precipitation)

## Target Platform

- **ESPHome**: Built-in `hub75` display component with **LVGL** for UI rendering
- **Board**: ESP32-S3 with octal PSRAM (80MHz), ESP-IDF framework
- **Panel**: 128x64 HUB75, 1/32 scan (5 address lines, `e_pin` required)
- **Display config**: `platform: hub75`, via substitutions (`panel_width: "128"`, `panel_height: "64"`), `update_interval: never`, `auto_clear_enabled: false`, `double_buffer: false`
- **Pin mapping**: R1=GPIO4, G1=GPIO1, B1=GPIO5, R2=GPIO6, G2=GPIO2, B2=GPIO7, A=GPIO15, B=GPIO41, C=GPIO16, D=GPIO40, E=GPIO42, LAT=GPIO39, OE=GPIO18, CLK=GPIO17
- **Onboard LEDs**: WS2812 RGB (GPIO48), TX indicator (GPIO43, inverted), Status LED (GPIO44)
- **LVGL**: `buffer_size: 25%`, `refresh_interval: 16ms` (fixed ~60 FPS)
- **HUB75 docs**: https://esphome.io/components/display/hub75/
- **LVGL docs**: https://esphome.io/components/lvgl/

## LVGL Reference

See [lvgl.md](./lvgl.md) for comprehensive LVGL usage facts gathered from ESPHome source code and docs.

## Architecture: YAML + LVGL vs C++ Component Split

**Principle**: LVGL widgets (labels, images) for stateless text/icon rendering. C++ external component for all stateful logic (particle system, sky arc positions, simulation state). Canvas widget for per-pixel drawing driven by the component.

| Feature | Lives in | How | Status |
|---------|----------|-----|--------|
| Clock | LVGL label widget | `text: { time_format: "%H:%M", time: esptime }` | Done |
| Date | LVGL label widget | `text: { time_format: "%a %d %b", time: esptime }` | Done |
| Temp inside/outside | LVGL label widgets | Lambda text from HA sensors, `lvgl.widget.refresh` on interval | Done |
| CO2, humidity, wind | LVGL label widgets | Same pattern | Done |
| Forecast text + icons | LVGL label + image widgets | HA template sensors via ESPHome `homeassistant` platform | Done |
| Custom text | LVGL label widget | `text: !lambda return id(custom_text).state;` | Not started |
| Weather icons | LVGL image widgets | `image:` + `mapping:`, `lvgl.widget.refresh` to update | Done |
| Layout (positioning) | LVGL widget x/y/align | Hardcoded positions, no collision avoidance needed | Done |
| Brightness logic | YAML automations / interval | Time-of-day + sun position, `hub75.set_brightness` action | Done |
| RGB light mode | LVGL lambda / interval | `lv_canvas_fill_bg` on full-screen canvas when switch is ON | Not started |
| Debug borders | LVGL canvas `draw_rectangle` | Toggle via template switch | Not started |
| **Precipitation particles** | **C++ component + canvas** | Component holds particle state, `get_pixels()` → YAML lambda draws via `lv_canvas_set_px` | Done |
| **Sun/moon border arc** | **C++ component + canvas** | Component calculates border pixel positions, adds to `get_pixels()` vector | Done |
| Temp outside blinking | LVGL label update | Alternates measured/provided temp every 5s based on `esptime.now().second` | Done |
| Custom text word wrap | Two LVGL labels + lambda | `font_small` (b10.bdf, monospace 5px/char), 25 chars/line, split at last space ≤25 | Done |

## Component Design: `weather_station`

Single generic C++ external component, not specific to precipitation. Holds all stateful weather station logic.

### Component structure

```
components/weather_station/
├── __init__.py              # config schema + codegen (no separate weather_station.py)
├── weather_station.h        # class declaration
└── weather_station.cpp      # implementation
```

Note: The plan originally called for a separate `weather_station.py` for config validation/codegen, but in practice the schema is minimal enough to live in `__init__.py` directly.

### Config schema (Python)

Minimal schema (in `__init__.py`):
- `id` (required) — component ID
- `panel_width` (required, int)
- `panel_height` (required, int)

### C++ class: `WeatherStation`

Extends `Component`. Holds state for:

- **Particle system**: `std::vector<Particle>` (x, y, timer, color, type, delay, h_accum), `snow_timer`
- **Simulation settings**: precip type (none/rain/wet_snow/snow), precip strength (0-2), wind speed (0-30)
- **Real weather data**: precip type, precip strength, wind speed (from HA sensors)
- **Sky arc state**: sun/moon rise/set datetime strings, recalculated each loop iteration

### Architecture: get_pixels() pattern

The component does **not** draw directly to canvas. Instead:
1. `loop()` calls `update_sky_()` then `update_particles_()`, both of which append to a shared `pixels_` vector
2. YAML interval lambda reads `get_pixels()` and draws each pixel via `lv_canvas_set_px()`

This keeps the component LVGL-agnostic and lets the YAML control rendering timing.

### Public methods (implemented)

```cpp
// Returns const ref to pixel vector for YAML lambda to draw
const std::vector<Pixel> &get_pixels() const;

// Simulation setters (from template entities)
void set_simulate_precip(const std::string &v);
void set_simulate_precip_strength(float v);
void set_simulate_wind_speed(float v);

// Real weather data setters (from HA sensors via on_value)
void set_precip_type(int v);
void set_precip_strength(float v);
void set_wind_speed_real(int v);

// Sky data setters (from HA text sensors)
void set_sun_rising(const std::string &v);
void set_sun_setting(const std::string &v);
void set_moon_rising(const std::string &v);
void set_moon_setting(const std::string &v);
```

### Public methods (not yet implemented)

```cpp
// (all currently needed methods are implemented)
```

### loop() method

The component has a `loop()` method that clears `pixels_`, then calls `update_sky_()` and `update_particles_()` (both append to the shared vector). The actual canvas drawing happens in the YAML interval lambda (50ms), not in `loop()`.

## LVGL Widget Layout

### Current layout (128x64 panel)

Using production fonts: `win_crox5h` (18px clock), `helvR08` (8px regular).

Positions calculated from Python layout (`rowH=10`, y=baseline, `y = rowH * (row + rowspan)`), converted to LVGL top-left coordinates (`LVGL y = baseline - font_ascent`).

Font ascent values (from BDF FONT_ASCENT, used by ESPHome/FreeType):
- `win_crox5h` (font_clock): ascent=23, height=29. Visible digit pixels at bitmap rows 6-22 (17px).
- `helvR08` (font_reg): ascent=10, height=12. Visible digit pixels at bitmap rows 0-7 (8px, offset_y=2).

Conversion: `LVGL label_y = Python baseline - ascent`. Images: `LVGL y = baseline - imgSize`.

Right-aligned text: `align: TOP_RIGHT, x: -1` → right edge at pixel 126 (matching Python `x = 127 - width`).
Icons placed to the left of text with 1px gap: `x = -(2 + typical_text_width)`.

| Widget | Font | x | y (LVGL) | Align | Python row/rowspan | Python baseline |
|--------|------|---|----------|-------|--------------------|-----------------|
| clock_label | font_clock | 1 | -4 | TOP_LEFT | row=0, rowspan=2, align_y=top | 19 |
| date_label | font_reg | 1 | 20 | TOP_LEFT | row=2 | 30 |
| temp_inside_label | font_reg | -1 | 0 | TOP_RIGHT | row=0 | 10 |
| temp_outside_group (obj) | — | -1 | 10 | TOP_RIGHT | row=1 | 20 |
| ├─ weather_icon | 8x8 image | — | — | flex child | left of temp text | — |
| └─ temp_outside_label | font_reg | — | — | flex child | row=1 | 20 |
| humidity_label | font_reg | 1 | 30 | TOP_LEFT | row=3 | 40 |
| co2_label | font_reg | 1 | 40 | TOP_LEFT | row=4 | 50 |
| wind_label | font_reg | -1 | 40 | TOP_RIGHT | row=4 | 50 |
| forecast_group_1 (obj) | — | -1 | 20 | TOP_RIGHT | row=2 | 30 |
| ├─ forecast_icon_1 | 8x8 image | — | — | flex child | left of forecast text | — |
| └─ forecast_label_1 | font_reg | — | — | flex child | row=2 | 30 |
| forecast_group_2 (obj) | — | -1 | 30 | TOP_RIGHT | row=3 | 40 |
| ├─ forecast_icon_2 | 8x8 image | — | — | flex child | left of forecast text | — |
| └─ forecast_label_2 | font_reg | — | — | flex child | row=3 | 40 |
| custom_text_line1 | font_small | 1 | 49 | TOP_LEFT | row=5, two-line mode line 1 | 57 |
| custom_text_line2 | font_small | 1 | 54 | TOP_LEFT | row=5, two-line mode line 2 | 63 |
| particle_canvas | — | 0 | 0 | — | full screen overlay | — |

### Canvas strategy

One full-screen transparent canvas (`128x64`, `transparent: true`) overlaid on top of all labels. Used for:
- Precipitation particles (per-pixel via `lv_canvas_set_px`)
- Sun/moon border arc indicators (per-pixel)
- Debug borders (`lv_canvas_draw_rectangle`) — not yet implemented
- RGB light mode (`lv_canvas_fill_bg` when switch is ON, hides all labels) — not yet implemented

The canvas is cleared and redrawn each frame in an `interval:` block. Labels below it are rendered by LVGL's normal refresh cycle; the canvas on top composites particles/arc on top.

### Vertical layout

| Y range | Content |
|---------|---------|
| 2-18 | Clock (font_clock, visible pixels) |
| 20-29 | Date, temp_inside, temp_outside + icon, forecast row 1 + icon |
| 30-39 | Humidity, CO2, wind, forecast row 2 + icon |
| 40-48 | (spare) |
| 49-62 | Custom text (font_small, two lines: line1 at y=49, line2 at y=55) |
| 63 | (spare) |

Sun/moon arc draws on the canvas border pixels (x=0/127, y=0/63), overlapping all rows.

### Horizontal alignment

- Left-aligned elements: `x: 1`
- Right-aligned elements: `align: TOP_RIGHT` with `x: -1` offset
- Icon+label pairs (weather_icon+temp_outside, forecast_icon_1/2+forecast_label_1/2) are wrapped in `obj` containers with flex layout. The container is `align: TOP_RIGHT, width: SIZE_CONTENT, height: SIZE_CONTENT`, so it shrinks to fit its children and stays anchored to the right edge. Children are `[icon, label]` in `flex_flow: row` with `pad_column: 1px` — LVGL automatically packs them left-to-right with a 1px gap. When label text changes width, the container auto-resizes and the icon stays glued to the label. No C++ lambda or manual re-alignment needed.
  ```yaml
  - obj:
      id: temp_outside_group
      x: -1
      y: 10
      align: TOP_RIGHT
      width: SIZE_CONTENT
      height: SIZE_CONTENT
      pad_all: 0
      border_width: 0
      bg_opa: TRANSP
      layout:
        type: flex
        flex_flow: row
        flex_align_main: start
        flex_align_cross: center
        pad_column: 1px
      widgets:
        - image:
            id: weather_icon
            src: ...
        - label:
            id: temp_outside_label
            text: ...
  ```
  - `extra_dim` mode hides/shows the container `obj` (e.g. `id(temp_outside_group)`) instead of individual children — simpler and fewer API calls.

## Home Assistant Data Integration

### Drop MQTT entirely

ESPHome native API replaces MQTT. Auto-discovery is automatic with `api:` component.

### HA sensor platform

Use `platform: homeassistant` to import entity states:

```yaml
sensor:
  - platform: homeassistant
    id: temp_inside
    entity_id: sensor.aqara_weather_02_temperature
  - platform: homeassistant
    id: temp_outside_measured
    entity_id: sensor.tuya_weather_02_temperature
  - platform: homeassistant
    id: co2
    entity_id: sensor.d1_co2_co2_scd30
  - platform: homeassistant
    id: humidity
    entity_id: sensor.aqara_weather_02_humidity
  - platform: homeassistant
    id: wind_speed
    entity_id: sensor.wind_speed
  - platform: homeassistant
    id: precip_type
    entity_id: sensor.precipitation_type
  - platform: homeassistant
    id: precip_strength
    entity_id: sensor.precipitation_strength

text_sensor:
  - platform: homeassistant
    id: temp_outside_provided
    entity_id: weather.yandex_weather
    attribute: temperature
  - platform: homeassistant
    id: wind_bearing
    entity_id: weather.yandex_weather
    attribute: wind_bearing
  - platform: homeassistant
    id: current_icon
    entity_id: sensor.fact_icon
  - platform: homeassistant
    id: sun_state
    entity_id: sun.sun
  - platform: homeassistant
    id: sun_rising
    entity_id: sun.sun
    attribute: next_rising
  - platform: homeassistant
    id: sun_setting
    entity_id: sun.sun
    attribute: next_setting
  - platform: homeassistant
    id: moon_rising
    entity_id: sensor.home_moon_rise
  - platform: homeassistant
    id: moon_setting
    entity_id: sensor.home_moon_set
```

### Forecast data (HA-side template sensors)

HA `weather.yandex_weather` has `forecast` (array) and `forecast_icons` (array) attributes. HA's ESPHome integration serializes attribute values via `str()`, producing Python `repr()` (single quotes, `True`/`False`) — not valid JSON. So JSON parsing on ESP32 is not viable for these attributes.

**Created HA-side template sensors** that flatten forecast into individual entities:

1. `sensor.forecast_temp_1` — numeric sensor from `forecast[1].native_temperature`
2. `sensor.forecast_icon_1` — text sensor from `forecast_icons[0]`
3. `sensor.forecast_period_1` — text sensor (morning/day/evening/night based on forecast datetime hour: >=18→`e`, >=12→`d`, >=6→`m`, else→`n`)
4. `sensor.forecast_temp_2` — numeric sensor from `forecast[2].native_temperature`
5. `sensor.forecast_icon_2` — text sensor from `forecast_icons[1]`
6. `sensor.forecast_period_2` — text sensor

All sensors have `availability` templates guarding against missing/short forecast data. Period templates use `as_datetime | as_local | .hour` (note: `timestamp_custom` does not work on datetime objects — it expects Unix epoch).

No JSON parsing on ESP32.

### Entity list (all HA entities used)

| ESPHome ID | HA Entity | Type | Status |
|------------|-----------|------|--------|
| `temp_inside` | `sensor.aqara_weather_02_temperature` | sensor | Done |
| `temp_outside_measured` | `sensor.tuya_weather_02_temperature` | sensor | Done |
| `temp_outside_provided` | `weather.yandex_weather` (attr: temperature) | text_sensor | Done |
| `co2` | `sensor.d1_co2_co2_scd30` | sensor | Done |
| `humidity` | `sensor.aqara_weather_02_humidity` | sensor | Done |
| `wind_speed_real` | `sensor.wind_speed` | sensor | Done (precipitation component only) |
| `wind_speed_weather` | `weather.yandex_weather` (attr: wind_speed) | text_sensor | Done (wind display widget) |
| `wind_bearing` | `weather.yandex_weather` (attr: wind_bearing) | text_sensor | Done |
| `current_icon` | `sensor.fact_icon` | text_sensor | Done |
| `sun_state` | `sun.sun` | text_sensor | Done |
| `sun_rising` | `sun.sun` (attr: next_rising) | text_sensor | Done |
| `sun_setting` | `sun.sun` (attr: next_setting) | text_sensor | Done |
| `moon_rising` | `sensor.home_moon_rise` | text_sensor | Done |
| `moon_setting` | `sensor.home_moon_set` | text_sensor | Done |
| `precip_type` | `sensor.precipitation_type` | sensor | Done |
| `precip_strength` | `sensor.precipitation_strength` | sensor | Done |
| `forecast_temp_1` | `sensor.forecast_temp_1` (HA template) | sensor | Done |
| `forecast_icon_1` | `sensor.forecast_icon_1` (HA template) | text_sensor | Done |
| `forecast_period_1` | `sensor.forecast_period_1` (HA template) | text_sensor | Done |
| `forecast_temp_2` | `sensor.forecast_temp_2` (HA template) | sensor | Done |
| `forecast_icon_2` | `sensor.forecast_icon_2` (HA template) | text_sensor | Done |
| `forecast_period_2` | `sensor.forecast_period_2` (HA template) | text_sensor | Done |

## ESPHome Template Entities (replacing MQTT controls)

### Implemented

| Entity | ESPHome Type | ID | Purpose |
|--------|-------------|-----|---------|
| Simulate precipitation | `select` (template) | `sim_precip` | Options: "", "snow", "rain", "wet_snow" → `set_simulate_precip()` |
| Simulated precip strength | `number` (template) | `sim_precip_strength` | 0.0-2.0, step 0.5 → `set_simulate_precip_strength()` |
| Simulated wind speed | `number` (template) | `sim_wind_speed` | 0.0-30.0, step 1.0 → `set_simulate_wind_speed()` |
| Brightness | `light` (monochromatic) | `brightness_light` | On/off + brightness slider. OFF = auto mode. Uses template float output + `update_brightness` script |
| Custom text | `text` (template) | `custom_text_input` | Text input, word-wrapped across two lines using `font_small` (b10.bdf, monospace 5px/char, 25 chars/line) |

### Not yet implemented

| Entity | ESPHome Type | Purpose |
|--------|-------------|---------|
| RGB light | `switch` (template) + `number` for R/G/B | Fill screen with solid color |
| Debug borders | `switch` (template) | Toggle debug rectangle drawing |

Each entity's `on_value` trigger calls the appropriate setter on the component:

```yaml
select:
  - platform: template
    id: sim_precip
    name: "Simulate precipitation"
    options:
      - ""
      - "snow"
      - "rain"
      - "wet_snow"
    on_value:
      - lambda: id(ws).set_simulate_precip(x);

number:
  - platform: template
    id: sim_precip_strength
    name: "Simulated precip strength"
    min_value: 0.0
    max_value: 2.0
    step: 0.5
    on_value:
      - lambda: id(ws).set_simulate_precip_strength(x);

  - platform: template
    id: sim_wind_speed
    name: "Simulated wind speed"
    min_value: 0.0
    max_value: 30.0
    step: 1.0
    on_value:
      - lambda: id(ws).set_simulate_wind_speed(x);
```

Real weather sensors also feed the component via `on_value`:
```yaml
sensor:
  - platform: homeassistant
    id: precip_type
    entity_id: sensor.precipitation_type
    on_value:
      - lambda: id(ws).set_precip_type((int) x);
  - platform: homeassistant
    id: precip_strength
    entity_id: sensor.precipitation_strength
    on_value:
      - lambda: id(ws).set_precip_strength(x);
  - platform: homeassistant
    id: wind_speed_real
    entity_id: sensor.wind_speed
    on_value:
      - lambda: id(ws).set_wind_speed_real((int) round(x));
```

## Rendering Loop

### Fixed refresh interval

LVGL handles screen refresh at `refresh_interval: 16ms` (~60 FPS). No dynamic frame rate changes needed.

### Canvas update interval

A separate `interval:` block updates the canvas (precipitation particles + sky arc) at 20ms (50 FPS, matching Python's precipitation frame rate). The component's `loop()` updates particle state continuously; the interval lambda reads `get_pixels()` and draws:

```yaml
interval:
  - interval: 20ms
    then:
      - lvgl.canvas.fill:
          id: particle_canvas
          color: black
          opa: TRANSP
      - lambda: |-
          const auto &pixels = id(ws).get_pixels();
          for (const auto &p : pixels) {
            if (p.x < 0 || p.x >= ${panel_width} || p.y < 0 || p.y >= ${panel_height})
              continue;
            lv_color_t c = lv_color_make(p.r, p.g, p.b);
            lv_canvas_set_px(id(particle_canvas), p.x, p.y, c, LV_OPA_COVER);
          }
```

For canvas with `transparent: true`, clearing with `LV_OPA_TRANSP` makes pixels transparent (showing labels below).

### Label update intervals

Labels are refreshed via `lvgl.widget.refresh` on two intervals:
- **1s**: clock, date, temp_outside (needs second-precision for measured/provided blinking)
- **5s**: weather_icon, temp_inside, co2, humidity, wind

```yaml
interval:
  - interval: 1s
    then:
      - lvgl.widget.refresh: clock_label
      - lvgl.widget.refresh: date_label
      - lvgl.widget.refresh: temp_outside_label
  - interval: 5s
    then:
      - lvgl.widget.refresh: weather_icon
      - lvgl.widget.refresh: temp_inside_label
      - lvgl.widget.refresh: co2_label
      - lvgl.widget.refresh: humidity_label
      - lvgl.widget.refresh: wind_label
```

Labels use inline lambdas in widget config, so `lvgl.widget.refresh` re-evaluates them.

## Porting Reference: Python → ESPHome LVGL

### Layout system (`get_coords_by_element`)

Python: collision-avoidance packing per row, left/right alignment, tracks placed elements in `self.map`.

ESPHome LVGL: Static widget positions with `x`/`y`/`align`. No runtime collision avoidance needed — the layout is fixed and known at config time. Right-aligned elements use `align: TOP_RIGHT` with negative x offset.

### Clock and date

Python: `draw_clock()` renders `now.strftime("%H:%M")` with large font (`win_crox5h`, 18px, proportional — colon is half digit width).

ESPHome:
```yaml
- label:
    id: clock_label
    x: 1
    y: 0
    text_font: font_clock        # win_crox5h.bdf, naturally proportional
    text_color: color_clock
    text:
      time_format: "%H:%M"
      time: esptime
```

### Temperature inside

Python: `draw_temp_inside()` reads HA sensor, formats as `f'{round(float(dev_temp_inside), 1)}°'`.

ESPHome:
```yaml
- label:
    id: temp_inside_label
    x: 1
    y: 29
    text_font: font_reg
    text: !lambda |-
      if (id(temp_inside).has_state())
        return str_sprintf("%.1f°", id(temp_inside).state);
      return std::string("N/A");
```

### Temperature outside (blinking)

Python: alternates between measured and provided temp every 5 seconds (`now.second % 10 >= 5`), with different colors.

ESPHome: Update label in 1s interval, check `id(esptime).now().second`:
```yaml
interval:
  - interval: 1s
    then:
      - lvgl.label.update:
          id: temp_outside_label
          text: !lambda |-
            int sec = id(esptime).now().second;
            if (sec % 10 >= 5) {
              // measured
              if (id(temp_outside_measured).has_state())
                return str_sprintf("%d°", (int)round(id(temp_outside_measured).state));
            } else {
              // provided
              if (id(temp_outside_provided).has_state())
                return str_sprintf("%d°", (int)round(std::stof(id(temp_outside_provided).state)));
            }
            return std::string("N/A");
          text_color: !lambda |-
            int sec = id(esptime).now().second;
            return (sec % 10 >= 5) ? lv_color_hex(0xFFFFFF) : lv_color_hex(0xAAAAAA);
```

### Precipitation particle system (`draw_precip`)

Python: `self.raindrops` list, spawn timing, wind drift, per-particle colors.

ESPHome C++ component (**done**):
- `std::vector<Particle>` in `WeatherStation` class
- `loop()` calls `update_particles_()` which updates particle state and populates `pixels_` vector
- YAML interval lambda reads `get_pixels()` and draws via `lv_canvas_set_px()`
- Spawn rate: `max_drops = int(panel_h * strength * 0.5)`, interval = `panel_h / (max_drops * spawn_speed)` — uses `panel_h_` for universality
- Spawn timing: `spawn_timer_` (float) tracks when next spawn is due. Each `loop()` call calculates `to_spawn = elapsed / interval_ms` (capped at `max_drops`), spawns that many particles at `y=-1`, then advances `spawn_timer_` by `to_spawn * interval_ms` regardless of how many actually spawned (prevents debt accumulation when `particles == max_drops`)
- `precip_active_` flag: resets `spawn_timer_` to `now` when precipitation starts (prevents stale timer from spawning all particles at once)
- Wind: `horizontal_step` and `horizontal_every` from wind speed, applied via accumulator
- Speeds: rain=100px/s, snow=15px/s, wet_snow=25px/s
- Colors: rain = blue range, snow = white range, wet_snow = gray range (random per-particle)
- Movement: each particle has independent `timer`. After moving, `timer += distance * drop_delay_ms` (not snapped to `now`) — prevents lockstep/waves caused by variable `loop()` frequency
- Component reads real precip data from HA sensors (via `set_precip_type`, `set_precip_strength`, `set_wind_speed_real`), or simulation settings if active

### Sun/moon arc (`draw_sky`) — DONE

Python: `angle_to_border()` converts angle to (x,y) on panel border. `draw_sky_body()` draws pixel + neighbors. `border_neighbors()` finds adjacent border pixels.

ESPHome C++ component (implemented):
- `update_sky_()` method called from `loop()` — adds sun/moon pixels to the same `pixels_` vector as particles
- `angle_to_border_(angle, &x, &y)` → (x, y) on border — direct port of Python trig
- `border_neighbors_(x, y, out, &count)` — finds up to 2 adjacent border pixels
- `parse_iso_datetime_(iso)` — manual ISO 8601 parse to UTC epoch seconds (Howard Hinnant's days-from-civil algorithm). Avoids `mktime`/`timegm` portability issues. Parses timezone offset (`+03:00` or `+0300`).
- Sun position: angle from last sunrise, `day_angle_span = day_length / 86400 * 360`
- Moon position: same logic with moon rise/set
- Sunrise/sunset marks at arc boundaries (2 pixels each, offset ±0.5°)
- Sun color: (255, 220, 0), moon color: (180, 200, 255)
- Mark colors: sun (200, 60, 0), moon (130, 130, 160)
- Component receives sun/moon rise/set times from HA text sensors via setters (`set_sun_rising`, `set_sun_setting`, `set_moon_rising`, `set_moon_setting`)
- `loop()` restructured: `pixels_.clear()` → `update_sky_()` → `update_particles_()` (both append to shared vector)
- Note: Datetime parsing is fragile. Future improvement: create HA-side helper sensors that provide pre-computed epoch seconds or angle values directly.

### Auto-brightness (`define_brightness`) — DONE

Python: time-based brightness with `userBrightness` override. `extra_dim` flag hides non-essential widgets when brightness=1.

ESPHome: `light` entity (monochromatic, `brightness_light`) with template float output. OFF = auto mode. Uses `update_brightness` script called from both `on_value` (immediate) and 30s interval (automatic transitions).

Brightness logic (matching Python exactly):
- User override: if light is ON, brightness = `light.brightness * 100`. If `<= 1`, `extra_dim = true`.
- Auto (light OFF): time-of-day + sun position:
  - 0-6h: below_horizon → 1 (extra_dim), else 20
  - 6-9h: below_horizon → 20, else 50
  - 18-22h: 25
  - 22-24h: 3
  - else: 60
- Conversion: HUB75 uses 0-255 scale. `brightness_255 = round(brightness_100 * 2.55)`. Special case: `brightness == 1` (extra_dim) maps to `1` not `3` (avoids excessive brightness at lowest setting).
- Applied via `id(matrix).set_brightness(brightness_255)` in lambda

Extra dim mode (matching Python `draw_entities`):
- **Hidden** (via `LV_OBJ_FLAG_HIDDEN`): date_label, temp_inside_label, temp_outside_label, weather_icon, co2_label, humidity_label, wind_label, forecast_label_1, forecast_icon_1, forecast_label_2, forecast_icon_2
- **Hidden** (via empty text): custom_text_line1, custom_text_line2
- **Visible**: clock_label, particle_canvas (sky arc + precipitation)

Extra dim state stored in global variable `extra_dim_global` (type `bool`), set by `update_brightness` script. The 1s custom text lambda checks `id(extra_dim_global)` to hide custom text without recalculating brightness logic.

Widget visibility controlled via `lv_obj_add_flag(id(widget), LV_OBJ_FLAG_HIDDEN)` / `lv_obj_remove_flag(...)`. Custom text labels use `lv_label_set_text(id(label), "")` instead of hiding, to avoid show/hide artifacts.

Two triggers:
1. `write_action` on template output (triggered by light state change) — immediate response to user input
2. 30s interval — automatic time-of-day transitions

### RGB light mode

Python: fills entire display with solid color, skips all other rendering.

ESPHome: Template switch toggles a flag. When ON, fill canvas with solid color and hide all labels:
```yaml
interval:
  - interval: 100ms
    then:
      - lambda: |-
          if (id(rgb_light_switch).state) {
            lv_canvas_fill_bg(id(overlay_canvas),
              lv_color_make(id(rgb_r).state, id(rgb_g).state, id(rgb_b).state),
              LV_OPA_COVER);
            // hide all labels
          } else {
            // normal rendering
          }
```

### Custom text word wrap (`draw_mqtt_text`) — DONE

Python: if text wider than display, cut at last space, render on two lines. Uses `fontSm` (b10.bdf, monospace 5px/char). Single-line baseline=60, two-line baselines=57/63.

ESPHome: Two LVGL labels (`custom_text_line1` at y=49, `custom_text_line2` at y=54) updated from a 1s interval lambda. Since b10 is monospace at 5px/char, max 25 chars/line (25×5=125 ≤ 128). If text exceeds 25 chars, scan backwards from position 25 for a space to split at; if none found, hard-cut at 25. Input via template text entity (`custom_text_input`, `mode: text`, `restore_value: true`). Both labels cleared to empty string when text is empty or in extra_dim mode (using `lv_label_set_text(id(label), "")` instead of `LV_OBJ_FLAG_HIDDEN` to avoid redraw artifacts).

**Note on line2 y position**: Python uses baseline=63 for line 2, which gives ESPHome `label_y = 63 - 8 = 55`. However, `font_small` has `line_height=10`, so a label at y=55 spans y=55..64 — 1px past the 64px display boundary (0-63). This caused a 4px-wide, 61px-tall white artifact on the right side of the display due to HUB75 framebuffer overflow. Fix: use `y=54` instead (spans y=54..63, fits within display). Visible text pixels are 1px higher than Python, which is imperceptible.

**General lesson**: LVGL label widgets are `line_height` pixels tall (which includes font ascent + descent + line gap), not just the visible glyph height. Always verify that `y + line_height <= display_height` to avoid framebuffer overflow on HUB75.

### Fonts

Python: Three fonts — `win_crox5h.bdf` (clock, 18px, proportional), `helvR08.bdf` (regular, 8px, proportional), `b10.bdf` (small, 10px, monospace "Biwidth").

ESPHome: All three fonts configured. IDs: `font_clock` (win_crox5h, size 18), `font_reg` (helvR08, size 8), `font_small` (b10, size 10). BDF metrics: `font_small` has ascent=8, height=10, base_line=2. All glyphs are 5px wide (monospace), visible pixels at bitmap rows 2-7 (6px visible height).

The production fonts (`win_crox5h`, `helvR08`) are naturally proportional — colon is half the digit width, decimal dot is narrow, digit `1` is narrower than other digits. This gives the clock and temperature a tight, professional look.

#### BDF charset fix for `win_crox5h.bdf`

The font had `CHARSET_REGISTRY "RAWIN"` / `CHARSET_ENCODING "R"` which FreeType doesn't recognize as a Unicode charset. This caused FreeType to return `char_index=0` for ALL codepoints, resulting in an empty glyph set and a crash in `Font::find_glyph()` (binary search on empty vector). Fixed by changing to `CHARSET_REGISTRY "ISO10646"` / `CHARSET_ENCODING "1"` (matching the other BDF fonts). The `FONT` XLFD line was also updated from `RAWIN-R` to `ISO10646-1`.

#### BDF editing notes

- `DWIDTH` = cursor advance after drawing glyph (determines character spacing)
- `BBX` = bounding box of actual pixels (width, height, x-offset, y-offset)
- `BBX x-offset` = horizontal offset of the bounding box from the cursor position; negative shifts left
- Bitmap data must be consistent with BBX width (bits are MSB-first, packed into bytes)
- For BBX width ≤ 8, one byte per row; the meaningful bits are the leftmost `BBX_W` bits

#### Font analysis

| Font | Type | Colon DWIDTH | Digit DWIDTH | Period DWIDTH | `1` DWIDTH |
|------|------|-------------|-------------|---------------|------------|
| `win_crox5h.bdf` (18px) | Proportional | 6 | 13 | 6 | 13 |
| `helvR08.bdf` (8px) | Proportional | 3 | 6 | 3 | 4 |
| `b10.bdf` (10px) | Monospace | 5 | 5 | 5 | 5 |

Python `dot_color` feature: The config had `"dot_color": [110, 0, 0]` for `temp_inside` (dark red). The Python code had a commented-out attempt to draw the decimal dot separately in a different color, abandoned due to alignment issues with proportional fonts (TODO: "mismatched position with narrow digits, eg: 21.1"). Not ported to ESPHome.

### Icons

Python: PNG icons in `icons8/` (8x8) and `icons/` (24x24), resized at runtime.

ESPHome: Icons copied from `weather-station/icons8/` to `esphome/icons/` (27 files, keeping `_8` suffix). Uses `image:` component with `platform: file` and `type: RGB`. ESPHome converts PNGs at compile time.

**Done**: Icons are loaded via `mapping:` component for dynamic selection by name (matching HA `sensor.fact_icon` text values). Image IDs sanitize `+`→`p` and `-`→`m` for valid C++ identifiers (e.g. `bkn_+ra_d` → `icon_bkn_pra_d`).

```yaml
image:
  - platform: file              # NOTE: "platform: file" required (bare "file:" is deprecated)
    file: icons/bkn_d_8.png
    id: icon_bkn_d
    type: RGB
  # ... 27 icons total

mapping:
  - id: icon_map
    from: string                # NOTE: "from:" field is required
    to: image
    default_value: icon_na
    entries:
      "bkn_d": icon_bkn_d
      "ovc": icon_ovc
      # ... keys match HA icon names (without _8 suffix)
```

LVGL image widget with dynamic src:
```yaml
- image:
    id: weather_icon
    x: -10
    y: 8
    align: TOP_RIGHT
    src:
      mapping: icon_map
      value: !lambda return id(current_icon).state;
```

#### Icon brightness difference

Python `draw_image()` applies a 0.7 coefficient to all icon pixel values (`self.c(r, 0.7)`, `self.c(g, 0.7)`, `self.c(b, 0.7)`), dimming icons to 70%. ESPHome renders icons as LVGL image widgets at full brightness. This is **intentional** — the dimming was an artifact of the Python rendering pipeline, not a deliberate design choice. Full-brightness icons on HUB75 look cleaner. Needs more user testing to confirm the brighter icons are acceptable.

### Debug borders

Python: `debug_borders` flag draws rectangles around element bounds.

ESPHome: Template switch toggles flag. When ON, draw rectangles on canvas:
```cpp
if (id(debug_borders_switch).state) {
  // draw rectangles around each widget's bounds using lv_canvas_draw_rectangle
  // or use lv_obj_get_coords to get widget positions
}
```

## File Structure

```
project root
├── weather-station.yaml           # main config (ESP32-S3, PSRAM)
├── fonts/
│   ├── win_crox5h.bdf             # clock font (18px) — MODIFIED: CHARSET_REGISTRY fixed to ISO10646
│   ├── helvR08.bdf                # regular font (8px) — proportional, ISO10646
│   └── b10.bdf                    # small font (10px) — monospace, used for custom text
├── icons/
│   └── (27 PNG icons, 8x8, copied from weather-station/icons8/)
└── components/
    └── weather_station/
        ├── __init__.py            # config schema + codegen
        ├── weather_station.h      # class declaration
        └── weather_station.cpp    # implementation
```

## HA-Side Prerequisites

Template sensors to create in Home Assistant (not implemented here):

1. **Forecast day 1 temp** — numeric sensor from `weather.yandex_weather` `forecast[1].native_temperature`
2. **Forecast day 1 icon** — text sensor from `weather.yandex_weather` `forecast_icons[0]`
3. **Forecast day 1 time period** — text sensor (morning/day/evening/night based on forecast datetime hour)
4. **Forecast day 2 temp** — numeric sensor from `forecast[2].native_temperature`
5. **Forecast day 2 icon** — text sensor from `forecast_icons[1]`
6. **Forecast day 2 time period** — text sensor

## Implementation Progress

### Done

- [x] ESPHome project setup (`weather-station.yaml`), HUB75 display config, LVGL integration
- [x] C++ `weather_station` component: particle system (spawn, movement, wind drift, colors)
- [x] `get_pixels()` pattern: component produces pixels, YAML lambda draws to canvas
- [x] Template entities: simulate precip select, precip strength, wind speed
- [x] Real weather data wired to component: precip_type, precip_strength, wind_speed via `on_value`
- [x] 27 weather icons copied, configured with `image: platform: file`, `mapping:` for dynamic selection
- [x] HA text sensor for current weather icon (`sensor.fact_icon`)
- [x] LVGL image widget with dynamic icon via mapping + lambda
- [x] HA sensors: temp_inside, temp_outside_measured, co2, humidity, precip_type, precip_strength, wind_speed_real
- [x] HA text sensors: current_icon, temp_outside_provided (attr), wind_bearing (attr), sun_state, sun_rising (attr), sun_setting (attr), moon_rising, moon_setting
- [x] LVGL labels: clock, date, temp_inside, temp_outside (blinking measured/provided), co2, humidity, wind (direction + speed)
- [x] Label refresh intervals: 1s for time-sensitive (clock, date, temp_outside blink), 5s for rest
- [x] Colors matching Python config values
- [x] BDF charset fix: `win_crox5h.bdf` CHARSET_REGISTRY changed from RAWIN to ISO10646
- [x] Sun/moon border arc in C++ component (`angle_to_border_`, `border_neighbors_`, `update_sky_`, `parse_iso_datetime_`)
- [x] Sun/moon HA text sensors wired to component via `on_value` triggers
- [x] `loop()` restructured: shared `pixels_` vector between sky arc and particles
- [x] Auto-brightness (time-of-day + sun position, `matrix.set_brightness`)
- [x] `extra_dim` mode (hide non-essential widgets at low brightness via `LV_OBJ_FLAG_HIDDEN`)
- [x] Brightness as `light` entity (monochromatic, on/off + brightness slider, `restore_mode: RESTORE_DEFAULT_OFF`). OFF = auto mode.
- [x] Production 128x64 layout (win_crox5h/helvR08 fonts, hardcoded positions matching Python row layout)
- [x] Custom text entity (template text input + word wrap using b10.bdf font_small, two-line split at 25 chars)
- [x] Dynamic icon positioning via LVGL flex containers (weather_icon, forecast_icon_1/2 wrapped in `obj` with `width: SIZE_CONTENT` + `flex_flow: row`, auto-packs icon next to label with 1px gap — no C++ lambda needed)
- [x] Temp outside color alternating between measured (bright cyan `#146E6E`) and provided (dim cyan `#0A3C3C`) every 5 seconds via `text_color` lambda
- [x] Wind display widget uses `weather.yandex_weather` attr `wind_speed` (not `sensor.wind_speed` which is for precipitation only)
- [x] Wind N/A when either bearing or speed is missing (matching Python)
- [x] Canvas interval at 20ms (50 FPS) matching Python's precipitation frame rate
- [x] Extra_dim brightness clamped to 1/255 (not 2/255 from truncation of `1 * 2.55`)
- [x] Colors use raw 0-255 values (`red_int`/`green_int`/`blue_int`) matching Python config exactly, no percentage rounding
- [x] Clock color dimmed in extra_dim mode via `color_clock_dim` (40,40,40) — compensates for HUB75 driver brightness curve difference vs Python's `rpi-rgb-led-matrix` BCM
- [x] Precipitation spawn timing: `spawn_timer_` (float) with `to_spawn = elapsed / interval_ms`, capped at `max_drops`, `spawn_timer_` advances regardless of actual spawns (no debt accumulation)
- [x] Precipitation `precip_active_` flag resets spawn timer on precipitation start (prevents burst spawn from stale timer)
- [x] Particle movement uses independent timers (`f.timer += distance * delay_ms`, not snapped to `now`) — prevents lockstep/waves from variable `loop()` frequency

### Not yet implemented

- [ ] RGB light mode (fill screen with solid color)
- [ ] Debug borders (toggle rectangles on canvas)
- [ ] HA-side helper sensors for sun/moon angles (would replace fragile datetime parsing in C++; not a correctness issue — `time(nullptr)` returns UTC epoch and `parse_iso_datetime_()` also converts to UTC, so current math is correct)

## Not In Scope

- Hardware testing/flashing
- The HA long-lived token in `config-clock.json` is dropped (ESPHome uses its own API auth)
- Dynamic frame rate (canvas uses fixed 20ms matching Python's precipitation FPS; LVGL uses fixed 16ms)
