import logging
import os
from datetime import datetime
from pathlib import Path

from PIL import Image

from src.config import Config

logger = logging.getLogger("mosher.display")


class MockDisplay:
    """Saves frames as PNGs for development without physical hardware."""

    def __init__(self):
        self._output_dir = Path("output")
        self._output_dir.mkdir(exist_ok=True)

    def show(self, image: Image.Image) -> None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = self._output_dir / f"frame_{ts}.png"
        image.save(path)
        logger.info("Mock display: saved %s (%s)", path, image.mode)


class InkyDisplay:
    """Drives the physical Pimoroni Inky Impression display."""

    def __init__(self):
        from inky.auto import auto

        self._inky = auto()
        logger.info("Inky display detected: %s", self._inky.resolution)

    def show(self, image: Image.Image) -> None:
        self._inky.set_image(image, saturation=0.5)
        self._inky.show()


def create_display(config: Config):
    """Create the appropriate display driver."""
    if config.mock_display:
        logger.info("Using mock display (output to PNG)")
        return MockDisplay()

    try:
        return InkyDisplay()
    except Exception as e:
        logger.warning("Could not initialize Inky display (%s), falling back to mock", e)
        return MockDisplay()
