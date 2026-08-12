**LED Panel clock**  

Clock/weather station with [Home Assistant](https://www.home-assistant.io/) as data source and brightness control via mqtt

https://github.com/alexbilevskiy/weather-station/assets/14160356/9c2a1ec7-3ff8-4a07-8c3b-b7440d52bc84


**Working principle**
* Station retrieves sensor states from home assistant via http api (`/api/states`) every n-th second (defined in `config-clock.json`)
* List of home assistant entities required for the station to work is defined in `devices` section of config. For example, `temp_outside` contains the name of the sensor with outside temperature, `prec_type` contains numeric type of precipitation (0 - clear, 1 - rain, 2 - snow, 3 - snowy rain).
* List of widgets is defined in `elements` section of config. This list describes display order, color and alignment of elements. Widget types are hardcoded by name and linked internally with sensors from `devices` section.
* Home assistant auto-discovery is used to create controls and input for text.
* Precipitation simulation: type (rain/snow/wet_snow), strength (0–2, step 0.5) and wind speed (0–30 m/s) can be controlled via MQTT to test the animated particle system without real weather data.
* Sun position indicator travels around the full panel border (analog clock style), with sunrise/sunset marks and proportional day/night arc lengths.
* Auto-brightness based on time of day and sun position, with MQTT override.

![image](https://github.com/alexbilevskiy/weather-station/assets/14160356/fc59bbf3-eabf-43b6-9616-6300dc598b64)

**MQTT entities (auto-discovered)**

| Entity | Type | Purpose |
|--------|------|---------|
| Brightness | light | On/off + brightness 0–100 |
| Text | text | Custom text on display |
| Simulate precipitation | select | "", "snow", "rain", "wet_snow" |
| Simulated precip strength | number (slider) | 0.0–2.0, step 0.5 |
| Simulated wind speed | number (slider) | 0.0–30.0, step 1.0 |

**todo**
* merge `devices` and `elements` sections of config, make widgets list fully configurable, create widget types

<details>
  <summary>(previous version with 32x64 display)</summary>

https://user-images.githubusercontent.com/14160356/206857211-8d43333a-2a5c-4fe0-a5b3-7af17c93118c.mp4
    
</details>

**Big thanks to**:
* https://github.com/hzeller/rpi-rgb-led-matrix
