import logging
import math
import time
from pathlib import Path

import requests
from PIL import Image

from src.config import Config
from src.geo import MapBounds, compute_map_bounds, tile_coords_fractional

logger = logging.getLogger("mosher.tiles")

TILE_SIZE = 256
TILE_MAX_AGE_DAYS = 3650  # ~10 years — tiles never change

MAP_STYLES = {
    "watercolor": {
        "url": "https://tiles.stadiamaps.com/tiles/stamen_watercolor/{z}/{x}/{y}.jpg",
        "ext": "jpg",
        "fallback": (245, 235, 220),  # Warm beige
    },
    "toner": {
        "url": "https://tiles.stadiamaps.com/tiles/stamen_toner/{z}/{x}/{y}.png",
        "ext": "png",
        "fallback": (255, 255, 255),  # White
    },
    "terrain": {
        "url": "https://tiles.stadiamaps.com/tiles/stamen_terrain/{z}/{x}/{y}.png",
        "ext": "png",
        "fallback": (240, 238, 230),  # Light grey-green
    },
}

STYLE_ORDER = ["watercolor", "toner", "terrain"]


class TileCache:
    def __init__(self, config: Config):
        self._config = config
        self._cache_dir = Path(config.cache_dir)
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._session = requests.Session()
        self._session.headers["User-Agent"] = "JustPlaneMosher/1.0"

    def get_tile(self, z: int, x: int, y: int, style: str = "watercolor") -> Image.Image:
        """Fetch a single map tile, using disk cache."""
        style_info = MAP_STYLES[style]
        tile_dir = self._cache_dir / "tiles" / style
        tile_dir.mkdir(parents=True, exist_ok=True)
        cache_path = tile_dir / f"{z}_{x}_{y}.{style_info['ext']}"

        # Check disk cache
        if cache_path.exists():
            age_days = (time.time() - cache_path.stat().st_mtime) / 86400
            if age_days < TILE_MAX_AGE_DAYS:
                try:
                    return Image.open(cache_path).convert("RGB")
                except Exception:
                    pass

        # Fetch from Stadia Maps
        url = style_info["url"].format(z=z, x=x, y=y)
        if self._config.stadia_api_key:
            url += f"?api_key={self._config.stadia_api_key}"

        try:
            resp = self._session.get(url, timeout=15)
            resp.raise_for_status()
            cache_path.write_bytes(resp.content)
            logger.info("Fetched %s tile z=%d x=%d y=%d", style, z, x, y)
            return Image.open(cache_path).convert("RGB")
        except Exception as e:
            logger.warning("Failed to fetch %s tile z=%d x=%d y=%d: %s", style, z, x, y, e)
            return Image.new("RGB", (TILE_SIZE, TILE_SIZE), style_info["fallback"])

    def build_base_map(self, config: Config, style: str = "watercolor") -> tuple[Image.Image, MapBounds]:
        """Stitch tiles into an 800x480 base map centered on configured location."""
        zoom = config.map_zoom
        width = config.display_width
        height = config.display_height

        cx, cy = tile_coords_fractional(config.latitude, config.longitude, zoom)

        center_px_x = cx * TILE_SIZE
        center_px_y = cy * TILE_SIZE

        origin_px_x = center_px_x - width / 2.0
        origin_px_y = center_px_y - height / 2.0

        tile_x_start = int(math.floor(origin_px_x / TILE_SIZE))
        tile_x_end = int(math.floor((origin_px_x + width) / TILE_SIZE))
        tile_y_start = int(math.floor(origin_px_y / TILE_SIZE))
        tile_y_end = int(math.floor((origin_px_y + height) / TILE_SIZE))

        fallback = MAP_STYLES[style]["fallback"]
        canvas_w = (tile_x_end - tile_x_start + 1) * TILE_SIZE
        canvas_h = (tile_y_end - tile_y_start + 1) * TILE_SIZE
        canvas = Image.new("RGB", (canvas_w, canvas_h), fallback)

        for tx in range(tile_x_start, tile_x_end + 1):
            for ty in range(tile_y_start, tile_y_end + 1):
                tile = self.get_tile(zoom, tx, ty, style)
                paste_x = (tx - tile_x_start) * TILE_SIZE
                paste_y = (ty - tile_y_start) * TILE_SIZE
                canvas.paste(tile, (paste_x, paste_y))

        crop_x = int(origin_px_x - tile_x_start * TILE_SIZE)
        crop_y = int(origin_px_y - tile_y_start * TILE_SIZE)
        base_map = canvas.crop((crop_x, crop_y, crop_x + width, crop_y + height))

        bounds = compute_map_bounds(config.latitude, config.longitude, zoom, width, height)
        logger.info(
            "Base map built (%s): %dx%d, bounds N=%.4f S=%.4f E=%.4f W=%.4f",
            style, width, height, bounds.north, bounds.south, bounds.east, bounds.west,
        )

        return base_map, bounds
