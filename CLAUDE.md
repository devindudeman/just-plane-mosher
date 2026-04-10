# CLAUDE.md

## Project Overview

Just Plane Mosher — a Raspberry Pi Zero 2 W + Pimoroni Inky Impression 7.3" (800x480, 7-color e-ink) flight tracker. Displays real-time overhead flights on a Stamen Watercolor map of the SF Bay Area. Built as a gift for Mosher who lives near the Haight in San Francisco.

## Quick Commands

```bash
# Run locally (mock display, outputs PNGs to output/)
source venv/bin/activate
python -m src.main

# On the Pi
sudo systemctl restart just-plane-mosher
journalctl -u just-plane-mosher -f

# Update the Pi
ssh devinbernosky@just-plane-mosher.local
cd ~/just-plane-mosher && git pull && sudo systemctl restart just-plane-mosher
```

## Key Architecture: Two-Layer Rendering

The renderer (`src/renderer.py`) uses a two-layer approach because Floyd-Steinberg dithering destroys small text on 7-color e-ink:

1. **Layer 1 (dithered)**: Watercolor map + range ring rendered in RGB, then quantized to 7-color palette with Floyd-Steinberg dithering
2. **Layer 2 (crisp)**: Aircraft arrows, labels, info bar, legend drawn directly on the palette image using integer palette indices (PAL_BLACK=0, PAL_WHITE=1, etc.)

The Inky library skips its own dithering when it receives a mode "P" (palette) image — this is the key bypass.

## APIs (all free, no auth required)

- **ADSB.lol**: `GET https://api.adsb.lol/v2/point/{lat}/{lon}/{radius_nm}` — live aircraft positions
- **ADSBdb**: `GET https://api.adsbdb.com/v0/callsign/{callsign}` — airline/route enrichment (cached 1hr, cache None for 404s)
- **Stadia Maps**: Stamen Watercolor tiles (requires free API key, tiles cached ~forever on disk)

## Config

All config via `.env` (see `.env.example`). Key settings:
- `MOCK_DISPLAY=true` for local dev (saves PNGs to `output/`)
- `MOCK_DISPLAY=false` on the Pi (drives Inky display)
- `STADIA_API_KEY` required for tile fetching
- `REFRESH_INTERVAL=300` (seconds between updates)

## File Structure

- `src/main.py` — Main loop, signal handling, SHA-256 change detection, exponential backoff
- `src/config.py` — .env loading, Config dataclass, validation
- `src/models.py` — Aircraft, FlightInfo, TrackedFlight dataclasses
- `src/flights.py` — ADSBClient: ADSB.lol fetch + ADSBdb enrichment with callsign cache
- `src/geo.py` — Haversine, Mercator projection, tile math, MapBounds
- `src/map_tiles.py` — TileCache: Stamen Watercolor tile fetch/stitch into 800x480 base map
- `src/renderer.py` — FlightRenderer: two-layer compositing + 7-color quantization
- `src/display.py` — InkyDisplay (real hardware) + MockDisplay (PNG output)

## Display Hardware Notes

- 7-color ACeP e-ink: black, white, red, green, blue, yellow, orange
- ~40 second full refresh (physics of ACeP, not configurable)
- No partial refresh support on 7-color displays
- Palette perceptual RGB values in `PALETTE_RGB` in renderer.py (not pure RGB)
- The 2025 Spectra 6 edition refreshes in ~12-20s but loses orange

## Deployment

- systemd service: `just-plane-mosher.service`
- User: `devinbernosky` (not pi)
- Working dir on Pi: `/home/devinbernosky/just-plane-mosher`
- Tailscale installed for remote access
- Two WiFi networks saved (home + Mosher's)

## Gotchas

- ADSBdb route data can be stale/wrong for charter flights (callsigns get reused)
- Stadia Maps requires API key even for Stamen Watercolor tiles (free tier)
- `libfreetype6` and `libopenblas0` needed on Raspberry Pi OS Trixie (in setup.sh)
- Pi Imager Flatpak v1.9.6 silently fails to write cloud-init config on Trixie images — use AppImage v2.0.8+
