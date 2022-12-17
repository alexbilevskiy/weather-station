## Project structure

**Main scripts**
- [`exporter/exporter.py`](exporter/exporter.py)  
Main daemon which collects all available data 
  - Subscribes to mqtt topic `zigbee2mqtt/#` to read all changes from zigbee network
  - Subscribes to mqtt topic `wifi2mqtt/#` to collect readings from my custom ESP8266 sensors `ESP_air` and `ESP_weather` (source code would be available soon...)
  - Periodically requests yandex.weather API and yandex.weather web for current weather conditions
  - Periodically requests my custom yandex traffic api (approximate route time from home to work and back) 
  - Stores all collected data as JSON object into memcached under key `metrics` ([example](metrics_example.json))


- [`led-clock/led-clock.py`](led-clock/led-clock.py)  
Daemon for LED clock (reads data from memcached `metrics`)


**Tools**
- [`exporter/metrics.py`](exporter/metrics.py)  
cgi script to export metrics in prometheus format ([example](metrics_example.txt))

- [`exporter/metrics_raw.py`](exporter/metrics_raw.py)  
cgi script to show raw metrics
  
- [`icons`](icons), [`icons8`](icons8)  
Yandex weather icons + 8px icons for led display
  

  
  
- [`led-clock/rect.py`](led-clock/rect.py)  
Just rectangle

- [`led-clock/snake.py`](led-clock/snake.py)  
Snake, controllable via raw tcp socket

**systemd units**
(`systemd` directory)
- units for led clock, exporter
- units for hass, zigbee2mqtt, mosquitto, grafana, etc (though they do not belong here)
- where is prometheus, you may ask? Windows box with spinning disk, of course!