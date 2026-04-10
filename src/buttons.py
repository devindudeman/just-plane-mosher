"""Button handler for Inky Impression's 4 rear buttons (A/B/C/D).

Buttons are active-low on GPIO 5, 6, 16, 24. This module runs a
background listener thread using gpiod edge detection (interrupt-driven,
zero CPU when idle).
"""

import logging
import threading
from typing import Callable

logger = logging.getLogger("mosher.buttons")

BUTTON_PINS = {
    "A": 5,
    "B": 6,
    "C": 16,
    "D": 24,
}


class ButtonListener:
    """Listens for button presses and calls registered callbacks."""

    def __init__(self):
        self._callbacks: dict[str, Callable] = {}
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    def on_press(self, button: str, callback: Callable) -> None:
        """Register a callback for a button press. Button is 'A', 'B', 'C', or 'D'."""
        self._callbacks[button] = callback

    def start(self) -> bool:
        """Start the background listener. Returns False if GPIO unavailable."""
        try:
            import gpiod
            import gpiodevice
            from gpiod.line import Bias, Direction, Edge
        except ImportError:
            logger.warning("gpiod/gpiodevice not available — buttons disabled")
            return False

        try:
            chip = gpiodevice.find_chip_by_platform()
        except Exception as e:
            logger.warning("Could not find GPIO chip — buttons disabled: %s", e)
            return False

        pins = list(BUTTON_PINS.values())
        labels = list(BUTTON_PINS.keys())

        try:
            offsets = [chip.line_offset_from_id(p) for p in pins]
            input_settings = gpiod.LineSettings(
                direction=Direction.INPUT,
                bias=Bias.PULL_UP,
                edge_detection=Edge.FALLING,
            )
            request = chip.request_lines(
                consumer="mosher-buttons",
                config=dict.fromkeys(offsets, input_settings),
            )
        except Exception as e:
            logger.warning("Could not request GPIO lines — buttons disabled: %s", e)
            return False

        def listener():
            from datetime import timedelta

            while not self._stop.is_set():
                try:
                    if request.wait_edge_events(timedelta(milliseconds=200)):
                        for event in request.read_edge_events():
                            try:
                                idx = offsets.index(event.line_offset)
                                label = labels[idx]
                                logger.info("Button %s pressed", label)
                                if label in self._callbacks:
                                    self._callbacks[label]()
                            except ValueError:
                                pass
                except Exception as e:
                    logger.debug("Button event error: %s", e)

            request.release()

        self._thread = threading.Thread(target=listener, daemon=True)
        self._thread.start()
        logger.info("Button listener started (A/B/C/D on GPIO %s)", list(pins))
        return True

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
