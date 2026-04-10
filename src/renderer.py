import math
import logging
from datetime import datetime

from PIL import Image, ImageDraw, ImageEnhance, ImageFont

from src.config import Config
from src.geo import MapBounds, latlon_to_pixel, haversine, latlon_to_pixel, compute_map_bounds
from src.map_tiles import TileCache
from src.models import TrackedFlight

logger = logging.getLogger("mosher.renderer")

# Inky Impression 7-color palette (perceptual values for accurate dithering)
PALETTE_RGB = [
    (57, 48, 57),       # 0: Black
    (255, 255, 255),    # 1: White
    (58, 91, 70),       # 2: Green
    (61, 59, 94),       # 3: Blue
    (156, 72, 75),      # 4: Red
    (208, 190, 71),     # 5: Yellow
    (177, 106, 73),     # 6: Orange
]

# Pure colors for drawing (pre-quantization, these map well to the palette)
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
RED = (220, 40, 40)
ORANGE = (230, 130, 30)
YELLOW = (230, 210, 40)
BLUE = (40, 40, 180)
GREEN = (30, 120, 50)

# Font paths to try
FONT_PATHS = [
    "assets/fonts/DejaVuSans.ttf",
    "assets/fonts/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/nix/store/*/share/fonts/truetype/DejaVuSans.ttf",
]

BOLD_FONT_PATHS = [
    "assets/fonts/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]


def _load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    paths = BOLD_FONT_PATHS if bold else FONT_PATHS
    for path in paths:
        try:
            return ImageFont.truetype(path, size)
        except (OSError, IOError):
            continue
    # Try system font discovery
    try:
        return ImageFont.truetype("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf", size)
    except (OSError, IOError):
        return ImageFont.load_default()


def _altitude_color(alt_ft: int | None) -> tuple[int, int, int]:
    """Map altitude to a color that will quantize well to the 7-color palette."""
    if alt_ft is None:
        return GREEN
    if alt_ft < 5000:
        return RED
    if alt_ft < 15000:
        return ORANGE
    if alt_ft < 30000:
        return YELLOW
    return BLUE


def _arrow_points(
    cx: float, cy: float, heading_deg: float, size: float = 12
) -> list[tuple[float, float]]:
    """Compute vertices of a triangle arrow pointing in the heading direction."""
    angle = math.radians(heading_deg - 90)  # 0° = north = up on screen
    # Tip
    tip = (cx + size * math.cos(angle), cy + size * math.sin(angle))
    # Two base points, spread 140° from tip direction
    left_angle = angle + math.radians(140)
    right_angle = angle - math.radians(140)
    base = size * 0.5
    left = (cx + base * math.cos(left_angle), cy + base * math.sin(left_angle))
    right = (cx + base * math.cos(right_angle), cy + base * math.sin(right_angle))
    return [tip, left, right]


class FlightRenderer:
    def __init__(self, config: Config, tile_cache: TileCache):
        self._config = config
        self._base_map, self._map_bounds = tile_cache.build_base_map(config)
        self._size = (config.display_width, config.display_height)

        # Load fonts — sized for legibility after 7-color dithering
        self._font_label = _load_font(15, bold=True)
        self._font_route = _load_font(13)
        self._font_info = _load_font(14)
        self._font_title = _load_font(15, bold=True)
        self._font_tiny = _load_font(10)

    def render(self, flights: list[TrackedFlight]) -> Image.Image:
        """Render the complete flight tracker frame."""
        frame = self._base_map.copy()
        draw = ImageDraw.Draw(frame)

        # Draw range ring
        self._draw_range_ring(draw)

        # Draw aircraft (count visible ones for info bar)
        label_boxes: list[tuple[int, int, int, int]] = []
        visible_count = 0
        for flight in flights:
            pixel = latlon_to_pixel(
                flight.aircraft.lat, flight.aircraft.lon, self._map_bounds, self._size
            )
            if pixel is not None:
                visible_count += 1
            self._draw_flight(draw, flight, label_boxes)

        # Draw info bar
        self._draw_info_bar(draw, visible_count)

        # Draw compass rose
        self._draw_compass_rose(draw)

        # Draw altitude legend
        self._draw_legend(draw)

        # Quantize to 7-color palette
        return self._quantize(frame)

    def _draw_flight(
        self,
        draw: ImageDraw.ImageDraw,
        flight: TrackedFlight,
        label_boxes: list[tuple[int, int, int, int]],
    ) -> None:
        ac = flight.aircraft
        pixel = latlon_to_pixel(ac.lat, ac.lon, self._map_bounds, self._size)
        if pixel is None:
            return

        px, py = pixel
        color = _altitude_color(ac.altitude_ft)

        # Draw aircraft arrow — large and bold to survive dithering
        if ac.track_deg is not None:
            points = _arrow_points(px, py, ac.track_deg, size=14)
            # Draw a black shadow first for contrast
            shadow = [(x + 1, y + 1) for x, y in points]
            draw.polygon(shadow, fill=BLACK)
            draw.polygon(points, fill=color, outline=BLACK, width=2)
        else:
            draw.ellipse((px - 6, py - 6, px + 6, py + 6), fill=color, outline=BLACK, width=2)

        # Build label text
        label_line1 = ac.callsign or ac.registration or ac.hex[:6]
        label_line2 = None
        if flight.info and flight.info.origin_iata and flight.info.destination_iata:
            label_line2 = f"{flight.info.origin_iata}>{flight.info.destination_iata}"

        # Position label
        label_x = px + 12
        label_y = py - 8

        # Measure text
        bbox1 = draw.textbbox((0, 0), label_line1, font=self._font_label)
        text_w = bbox1[2] - bbox1[0]
        text_h = bbox1[3] - bbox1[1]
        total_h = text_h
        if label_line2:
            bbox2 = draw.textbbox((0, 0), label_line2, font=self._font_route)
            text_w = max(text_w, bbox2[2] - bbox2[0])
            total_h += (bbox2[3] - bbox2[1]) + 1

        # Flip label to left side if it would go off-screen
        if label_x + text_w + 6 > self._size[0]:
            label_x = px - text_w - 18

        # Collision avoidance: shift down if overlapping another label
        pad = 3
        box = (label_x - pad, label_y - pad, label_x + text_w + pad, label_y + total_h + pad)
        for existing in label_boxes:
            if _boxes_overlap(box, existing):
                label_y = existing[3] + 2
                box = (label_x - pad, label_y - pad, label_x + text_w + pad, label_y + total_h + pad)

        label_boxes.append(box)

        # Draw label background pill
        draw.rounded_rectangle(
            (label_x - pad, label_y - pad, label_x + text_w + pad, label_y + total_h + pad),
            radius=3,
            fill=(255, 255, 255, 220),
            outline=None,
        )

        # Draw text
        draw.text((label_x, label_y), label_line1, fill=BLACK, font=self._font_label)
        if label_line2:
            draw.text(
                (label_x, label_y + text_h + 1), label_line2, fill=BLACK, font=self._font_route
            )

    def _draw_range_ring(self, draw: ImageDraw.ImageDraw) -> None:
        """Draw a subtle 10nm range ring centered on the configured location."""
        center = latlon_to_pixel(
            self._config.latitude, self._config.longitude, self._map_bounds, self._size
        )
        if center is None:
            return

        cx, cy = center

        # Calculate 10nm radius in pixels by projecting a point 10nm north
        north_lat = self._config.latitude + (10.0 / 60.0)  # ~10nm north
        north_pixel = latlon_to_pixel(
            north_lat, self._config.longitude, self._map_bounds, self._size
        )
        if north_pixel is None:
            return

        radius_px = abs(cy - north_pixel[1])

        # Draw dashed circle (dots every 3 degrees)
        for angle_deg in range(0, 360, 3):
            angle = math.radians(angle_deg)
            x = cx + radius_px * math.cos(angle)
            y = cy + radius_px * math.sin(angle)
            draw.ellipse((x - 1, y - 1, x + 1, y + 1), fill=(100, 100, 100))

        # Small center dot
        draw.ellipse((cx - 2, cy - 2, cx + 2, cy + 2), fill=BLACK)

    def _draw_compass_rose(self, draw: ImageDraw.ImageDraw) -> None:
        """Draw a small compass rose in the top-right corner."""
        cx, cy = self._size[0] - 35, 35
        length = 18

        # N-S line
        draw.line([(cx, cy - length), (cx, cy + length)], fill=BLACK, width=1)
        # E-W line
        draw.line([(cx - length, cy), (cx + length, cy)], fill=BLACK, width=1)

        # N arrow tip
        draw.polygon(
            [(cx, cy - length - 4), (cx - 3, cy - length + 3), (cx + 3, cy - length + 3)],
            fill=BLACK,
        )

        # "N" label
        draw.text((cx - 4, cy - length - 16), "N", fill=BLACK, font=self._font_tiny)

    def _draw_legend(self, draw: ImageDraw.ImageDraw) -> None:
        """Draw altitude color legend in the bottom-left corner."""
        x_start = 8
        y_start = self._size[1] - 65
        box_size = 8
        spacing = 14

        items = [
            (RED, "<5k ft"),
            (ORANGE, "5-15k"),
            (YELLOW, "15-30k"),
            (BLUE, ">30k ft"),
        ]

        # Background
        draw.rounded_rectangle(
            (x_start - 4, y_start - 4, x_start + 70, y_start + len(items) * spacing + 2),
            radius=4,
            fill=(255, 255, 255, 200),
        )

        for i, (color, label) in enumerate(items):
            y = y_start + i * spacing
            draw.rectangle((x_start, y, x_start + box_size, y + box_size), fill=color, outline=BLACK)
            draw.text((x_start + box_size + 4, y - 2), label, fill=BLACK, font=self._font_tiny)

    def _draw_info_bar(self, draw: ImageDraw.ImageDraw, flight_count: int) -> None:
        """Draw the info bar at the bottom of the frame."""
        bar_height = 24
        y = self._size[1] - bar_height
        w = self._size[0]

        # Semi-transparent white bar
        draw.rectangle((0, y, w, self._size[1]), fill=(255, 255, 255))
        draw.line([(0, y), (w, y)], fill=(180, 180, 180), width=1)

        # Left: title
        draw.text((8, y + 5), "Just Plane Mosher", fill=BLACK, font=self._font_title)

        # Center: flight count
        count_text = f"{flight_count} flight{'s' if flight_count != 1 else ''} overhead"
        bbox = draw.textbbox((0, 0), count_text, font=self._font_info)
        text_w = bbox[2] - bbox[0]
        draw.text(((w - text_w) // 2, y + 5), count_text, fill=BLACK, font=self._font_info)

        # Right: timestamp
        now = datetime.now().strftime("%H:%M")
        bbox = draw.textbbox((0, 0), now, font=self._font_info)
        time_w = bbox[2] - bbox[0]
        draw.text((w - time_w - 8, y + 5), now, fill=BLACK, font=self._font_info)

    def _quantize(self, image: Image.Image) -> Image.Image:
        """Quantize an RGB image to the 7-color e-ink palette with dithering."""
        # Boost saturation and contrast for e-ink vibrancy
        image = ImageEnhance.Color(image).enhance(1.5)
        image = ImageEnhance.Contrast(image).enhance(1.1)

        # Build palette image
        palette_data = []
        for r, g, b in PALETTE_RGB:
            palette_data.extend([r, g, b])
        # Pad to 256 entries
        palette_data.extend([0, 0, 0] * (256 - len(PALETTE_RGB)))

        palette_img = Image.new("P", (1, 1))
        palette_img.putpalette(palette_data)

        # Quantize with Floyd-Steinberg dithering
        return image.convert("RGB").quantize(palette=palette_img, dither=Image.Dither.FLOYDSTEINBERG)


def _boxes_overlap(a: tuple, b: tuple) -> bool:
    """Check if two (x1, y1, x2, y2) bounding boxes overlap."""
    return not (a[2] < b[0] or a[0] > b[2] or a[3] < b[1] or a[1] > b[3])
