**LED Panel clock**  

Clock/weather station with [Home Assistant](https://www.home-assistant.io/) as data source and brightness control via mqtt

https://github.com/alexbilevskiy/weather-station/assets/14160356/9c2a1ec7-3ff8-4a07-8c3b-b7440d52bc84


**Working principle**
* Station retrieves sensor states from home assistant via http api (`/api/states`) every n-th second (defined in `config-lock.json`)
* List of home assistant entities required for the station to work is defined in `devices` section of config. For example, `temp_outside` contains the name of the sensor with outside temperature, `prec_type` contains numeric type of precipitation (0 - clear, 1 - rain, 2 - snow, 3 - snowy rain).
* List of widgets is defined in `elements` section of config. This list describes display order, color and alignment of elements. Widget types are hardcoded by name and linked internally with sensosrs from `devices` section.
* Home assistant auto-discovery feature is used to create brightness control and input for bottom text line.
![image](https://github.com/alexbilevskiy/weather-station/assets/14160356/a1fb7238-00e6-4c8d-8462-8543d7ec13b6)

**todo**
* merge `devices` and `elements` sections of config, make widgets list fully configurable, create widget types
* docker image

<details>
  <summary>(previous version with 32x64 display)</summary>

https://user-images.githubusercontent.com/14160356/206857211-8d43333a-2a5c-4fe0-a5b3-7af17c93118c.mp4
    
</details>

**Big thanks to**:
* https://github.com/hzeller/rpi-rgb-led-matrix

