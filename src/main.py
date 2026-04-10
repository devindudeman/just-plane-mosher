import hashlib
import logging
import signal
import sys
import time

from src.config import load_config
from src.display import create_display
from src.flights import ADSBClient
from src.map_tiles import TileCache
from src.renderer import FlightRenderer

logger = logging.getLogger("mosher")


def setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def compute_image_hash(image) -> str:
    return hashlib.sha256(image.tobytes()).hexdigest()


def main():
    config = load_config()
    setup_logging(config.log_level)

    logger.info("Just Plane Mosher starting up")
    logger.info(
        "Tracking flights within %dnm of (%.4f, %.4f)",
        config.radius_nm,
        config.latitude,
        config.longitude,
    )

    # Graceful shutdown
    running = True

    def handle_signal(sig, frame):
        nonlocal running
        logger.info("Shutting down...")
        running = False

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    # Initialize components
    display = create_display(config)
    client = ADSBClient(config)
    tile_cache = TileCache(config)
    renderer = FlightRenderer(config, tile_cache)

    last_hash = None
    consecutive_errors = 0

    while running:
        try:
            flights = client.get_tracked_flights()
            logger.info("Found %d flights", len(flights))

            image = renderer.render(flights)

            current_hash = compute_image_hash(image)
            if current_hash == last_hash:
                logger.info("No visual change, skipping display refresh")
            else:
                logger.info("Updating display...")
                display.show(image)
                last_hash = current_hash
                logger.info("Display updated")

            consecutive_errors = 0

        except Exception:
            consecutive_errors += 1
            logger.exception(
                "Error in main loop (consecutive: %d)", consecutive_errors
            )
            if consecutive_errors > 3:
                backoff = min(
                    600, config.refresh_interval * (2 ** (consecutive_errors - 3))
                )
                logger.warning("Backing off for %ds", backoff)
                time.sleep(backoff)
                continue

        # Sleep with 1s granularity for responsive shutdown
        for _ in range(config.refresh_interval):
            if not running:
                break
            time.sleep(1)

    logger.info("Goodbye!")


if __name__ == "__main__":
    main()
