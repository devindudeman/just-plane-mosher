import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Display constants
DISPLAY_WIDTH = 800
DISPLAY_HEIGHT = 480
MAP_ZOOM = 10


@dataclass(frozen=True)
class Config:
    latitude: float
    longitude: float
    radius_nm: int
    stadia_api_key: str
    refresh_interval: int
    log_level: str
    mock_display: bool
    display_width: int = DISPLAY_WIDTH
    display_height: int = DISPLAY_HEIGHT
    map_zoom: int = MAP_ZOOM
    cache_dir: str = "cache"


def load_config() -> Config:
    """Load configuration from .env file with sensible defaults."""
    load_dotenv()

    config = Config(
        latitude=float(os.getenv("LATITUDE", "37.7692")),
        longitude=float(os.getenv("LONGITUDE", "-122.4488")),
        radius_nm=int(os.getenv("RADIUS_NM", "25")),
        stadia_api_key=os.getenv("STADIA_API_KEY", ""),
        refresh_interval=int(os.getenv("REFRESH_INTERVAL", "120")),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        mock_display=os.getenv("MOCK_DISPLAY", "false").lower() == "true",
    )

    # Validate
    if not (-90 <= config.latitude <= 90):
        raise ValueError(f"Invalid latitude: {config.latitude}")
    if not (-180 <= config.longitude <= 180):
        raise ValueError(f"Invalid longitude: {config.longitude}")
    if config.radius_nm <= 0:
        raise ValueError(f"Radius must be positive: {config.radius_nm}")
    if config.refresh_interval < 10:
        raise ValueError(f"Refresh interval too low: {config.refresh_interval}")

    # Ensure cache directory exists
    Path(config.cache_dir).mkdir(parents=True, exist_ok=True)

    return config
