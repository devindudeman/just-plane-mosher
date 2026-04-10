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
- Altitude-colored aircraft arrows with black borders (red/orange/yellow/blue)
- Callsign + route labels with bordered white backgrounds
- 10nm range ring, altitude legend
- Two-layer rendering: dithered watercolor map with pixel-perfect text and icons on top
- Change detection (skips display refresh if nothing moved)
- Graceful error handling with exponential backoff

## Quick Start

```bash
# Clone
git clone https://github.com/devindudeman/just-plane-mosher.git
cd just-plane-mosher

# On Raspberry Pi:
cp .env.example .env
nano .env  # Set STADIA_API_KEY and MOCK_DISPLAY=false
chmod +x setup.sh && ./setup.sh
sudo reboot

# After reboot:
sudo systemctl start just-plane-mosher
journalctl -u just-plane-mosher -f
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
| `REFRESH_INTERVAL` | 300 | Seconds between updates |
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
  renderer.py    Two-layer PIL compositing + 7-color quantization
  display.py     InkyDisplay + MockDisplay abstraction
```

## How It Works

The renderer uses a two-layer approach to solve a fundamental e-ink challenge: Floyd-Steinberg dithering (needed to reduce the watercolor map to 7 colors) destroys small text and thin lines.

1. **Layer 1 (dithered)**: The Stamen Watercolor map and range ring are rendered in full RGB, then quantized to the 7-color e-ink palette with Floyd-Steinberg dithering.
2. **Layer 2 (crisp)**: Aircraft arrows, callsign labels, the info bar, and altitude legend are drawn directly onto the palette image using exact color indices — no dithering, pixel-perfect.

The Inky library skips its own dithering when it receives a pre-quantized palette image, so everything reaches the display exactly as rendered.

## Attribution

- Map tiles: [Stamen Watercolor](http://maps.stamen.com/watercolor) via [Stadia Maps](https://stadiamaps.com)
- Flight data: [ADSB.lol](https://adsb.lol)
- Flight enrichment: [ADSBdb](https://adsbdb.com)
- Display library: [Pimoroni Inky](https://github.com/pimoroni/inky)
