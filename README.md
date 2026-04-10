# Just Plane Mosher

A beautiful e-ink flight tracker for the Raspberry Pi. Shows real-time overhead flights on a Stamen Watercolor map, designed for the Pimoroni Inky Impression 7.3" (800x480, 7-color e-ink display).

Built as a gift for Mosher in San Francisco.

## Hardware

- Raspberry Pi Zero 2 W
- Pimoroni Inky Impression 7.3" (7-color)

## Features

- Real-time flight tracking via [ADSB.lol](https://adsb.lol) (free, no auth)
- Flight enrichment (airline, route) via [ADSBdb](https://adsbdb.com) (free, no auth)
- Stamen Watercolor base map via [Stadia Maps](https://stadiamaps.com) (free tier)
- Altitude-colored aircraft arrows (red/orange/yellow/blue)
- Callsign + route labels
- 10nm range ring, compass rose, altitude legend
- 7-color Floyd-Steinberg dithering optimized for e-ink
- Change detection (skips display refresh if nothing moved)
- Graceful error handling with exponential backoff

## Quick Start

```bash
# Clone
git clone https://github.com/yourusername/just-plane-mosher
cd just-plane-mosher

# On Raspberry Pi:
chmod +x setup.sh && ./setup.sh

# Edit config
nano .env

# Run manually:
source venv/bin/activate
python -m src.main

# Or via systemd:
sudo systemctl start just-plane-mosher
```

## Development (any machine)

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Set MOCK_DISPLAY=true in .env to output PNGs instead of driving hardware
cp .env.example .env
python -m src.main
# Check output/ for rendered frames
```

## Configuration (.env)

| Variable | Default | Description |
|----------|---------|-------------|
| `LATITUDE` | 37.7692 | Center latitude |
| `LONGITUDE` | -122.4488 | Center longitude |
| `RADIUS_NM` | 25 | Flight search radius (nautical miles) |
| `STADIA_API_KEY` | | Stadia Maps API key (free at stadiamaps.com) |
| `REFRESH_INTERVAL` | 120 | Seconds between updates |
| `MOCK_DISPLAY` | false | Output PNGs instead of driving Inky display |
| `LOG_LEVEL` | INFO | Logging verbosity |

## Architecture

```
src/
  main.py        Main loop with signal handling + change detection
  config.py      .env loading + validation
  models.py      Aircraft, FlightInfo, TrackedFlight dataclasses
  flights.py     ADSB.lol + ADSBdb API client with callsign caching
  geo.py         Haversine, Mercator projection, tile math
  map_tiles.py   Stamen Watercolor tile fetch/stitch/cache
  renderer.py    PIL compositing + 7-color quantization
  display.py     InkyDisplay + MockDisplay abstraction
```

## Attribution

- Map tiles: [Stamen Watercolor](http://maps.stamen.com/watercolor) via [Stadia Maps](https://stadiamaps.com)
- Flight data: [ADSB.lol](https://adsb.lol)
- Flight enrichment: [ADSBdb](https://adsbdb.com)
- Display library: [Pimoroni Inky](https://github.com/pimoroni/inky)
