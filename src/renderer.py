import math
import logging
from datetime import datetime

from PIL import Image, ImageDraw, ImageEnhance, ImageFont

from src.config import Config
from src.geo import latlon_to_pixel
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

# Palette indices for drawing on quantized "P" mode images
PAL_BLACK = 0
PAL_WHITE = 1
PAL_GREEN = 2
PAL_BLUE = 3
PAL_RED = 4
PAL_YELLOW = 5
PAL_ORANGE = 6

# RGB colors for drawing on the pre-quantization map layer (aircraft arrows)
RGB_BLACK = (0, 0, 0)
RGB_RED = (220, 40, 40)
RGB_ORANGE = (230, 130, 30)
RGB_YELLOW = (230, 210, 40)
RGB_BLUE = (40, 40, 180)
RGB_GREEN = (30, 120, 50)

# Font paths to try
FONT_PATHS = [
    "assets/fonts/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
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
    try:
        return ImageFont.truetype("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf", size)
    except (OSError, IOError):
        return ImageFont.load_default()


def _altitude_color_rgb(alt_ft: int | None) -> tuple[int, int, int]:
    """Map altitude to an RGB color for the map layer (pre-quantization)."""
    if alt_ft is None:
        return RGB_GREEN
    if alt_ft < 5000:
        return RGB_RED
    if alt_ft < 15000:
        return RGB_ORANGE
    if alt_ft < 30000:
        return RGB_YELLOW
    return RGB_BLUE


def _altitude_color_pal(alt_ft: int | None) -> int:
    """Map altitude to a palette index for the quantized layer."""
    if alt_ft is None:
        return PAL_GREEN
    if alt_ft < 5000:
        return PAL_RED
    if alt_ft < 15000:
        return PAL_ORANGE
    if alt_ft < 30000:
        return PAL_YELLOW
    return PAL_BLUE


def _arrow_points(
    cx: float, cy: float, heading_deg: float, size: float = 12
) -> list[tuple[float, float]]:
    """Compute vertices of a triangle arrow pointing in the heading direction."""
    angle = math.radians(heading_deg - 90)
    tip = (cx + size * math.cos(angle), cy + size * math.sin(angle))
    left_angle = angle + math.radians(140)
    right_angle = angle - math.radians(140)
    base = size * 0.5
    left = (cx + base * math.cos(left_angle), cy + base * math.sin(left_angle))
    right = (cx + base * math.cos(right_angle), cy + base * math.sin(right_angle))
    return [tip, left, right]


# Label data collected during RGB pass, drawn on palette image after quantization
class _LabelInfo:
    __slots__ = ("x", "y", "line1", "line2", "text_w", "total_h", "text_h", "box")

    def __init__(self, x, y, line1, line2, text_w, total_h, text_h, box):
        self.x = x
        self.y = y
        self.line1 = line1
        self.line2 = line2
        self.text_w = text_w
        self.total_h = total_h
        self.text_h = text_h
        self.box = box


class FlightRenderer:
    def __init__(self, config: Config, tile_cache: TileCache):
        self._config = config
        self._base_map, self._map_bounds = tile_cache.build_base_map(config)
        self._size = (config.display_width, config.display_height)

        # Fonts — sized for legibility on e-ink
        self._font_label = _load_font(16, bold=True)
        self._font_route = _load_font(14)
        self._font_info = _load_font(15)
        self._font_title = _load_font(16, bold=True)
        self._font_tiny = _load_font(12, bold=True)

    def render(self, flights: list[TrackedFlight]) -> Image.Image:
        """Render the complete flight tracker frame.

        Two-layer approach:
        1. Draw map + aircraft arrows on RGB canvas, then dither to 7 colors
        2. Draw all text/UI on the palette image with exact palette indices (no dithering)
        """
        # === Layer 1: RGB map + aircraft arrows (will be dithered) ===
        frame = self._base_map.copy()
        draw = ImageDraw.Draw(frame)

        self._draw_range_ring(draw)

        # Draw aircraft arrows and collect label positions
        labels: list[_LabelInfo] = []
        label_boxes: list[tuple[int, int, int, int]] = []
        visible_count = 0

        for flight in flights:
            ac = flight.aircraft
            pixel = latlon_to_pixel(ac.lat, ac.lon, self._map_bounds, self._size)
            if pixel is None:
                continue

            visible_count += 1
            px, py = pixel
            color = _altitude_color_rgb(ac.altitude_ft)

            # Draw arrow on RGB canvas (survives dithering as a colored blob)
            if ac.track_deg is not None:
                points = _arrow_points(px, py, ac.track_deg, size=14)
                shadow = [(x + 1, y + 1) for x, y in points]
                draw.polygon(shadow, fill=RGB_BLACK)
                draw.polygon(points, fill=color, outline=RGB_BLACK, width=2)
            else:
                draw.ellipse((px - 6, py - 6, px + 6, py + 6), fill=color, outline=RGB_BLACK, width=2)

            # Collect label info (text drawn AFTER quantization)
            label = self._compute_label(draw, flight, px, py, label_boxes)
            if label:
                labels.append(label)

        # === Quantize the map layer ===
        quantized = self._quantize(frame)

        # === Layer 2: Draw crisp text on the palette image ===
        draw_p = ImageDraw.Draw(quantized)

        # Flight labels
        for label in labels:
            pad = 3
            draw_p.rectangle(
                (label.x - pad, label.y - pad,
                 label.x + label.text_w + pad, label.y + label.total_h + pad),
                fill=PAL_WHITE,
            )
            draw_p.text((label.x, label.y), label.line1, fill=PAL_BLACK, font=self._font_label)
            if label.line2:
                draw_p.text(
                    (label.x, label.y + label.text_h + 1),
                    label.line2, fill=PAL_BLACK, font=self._font_route,
                )

        # UI elements
        self._draw_info_bar_p(draw_p, visible_count)
        self._draw_compass_rose_p(draw_p)
        self._draw_legend_p(draw_p)

        return quantized

    def _compute_label(
        self,
        draw: ImageDraw.ImageDraw,
        flight: TrackedFlight,
        px: int,
        py: int,
        label_boxes: list[tuple[int, int, int, int]],
    ) -> _LabelInfo | None:
        """Compute label position and text without drawing. Returns label info."""
        ac = flight.aircraft
        line1 = ac.callsign or ac.registration or ac.hex[:6]
        line2 = None
        if flight.info and flight.info.origin_iata and flight.info.destination_iata:
            line2 = f"{flight.info.origin_iata}>{flight.info.destination_iata}"

        label_x = px + 14
        label_y = py - 8

        bbox1 = draw.textbbox((0, 0), line1, font=self._font_label)
        text_w = bbox1[2] - bbox1[0]
        text_h = bbox1[3] - bbox1[1]
        total_h = text_h
        if line2:
            bbox2 = draw.textbbox((0, 0), line2, font=self._font_route)
            text_w = max(text_w, bbox2[2] - bbox2[0])
            total_h += (bbox2[3] - bbox2[1]) + 1

        # Flip to left if off-screen
        if label_x + text_w + 6 > self._size[0]:
            label_x = px - text_w - 20

        # Collision avoidance
        pad = 3
        box = (label_x - pad, label_y - pad, label_x + text_w + pad, label_y + total_h + pad)
        for existing in label_boxes:
            if _boxes_overlap(box, existing):
                label_y = existing[3] + 2
                box = (label_x - pad, label_y - pad, label_x + text_w + pad, label_y + total_h + pad)

        label_boxes.append(box)

        return _LabelInfo(
            x=label_x, y=label_y, line1=line1, line2=line2,
            text_w=text_w, total_h=total_h, text_h=text_h, box=box,
        )

    def _draw_range_ring(self, draw: ImageDraw.ImageDraw) -> None:
        """Draw a subtle 10nm range ring centered on the configured location."""
        center = latlon_to_pixel(
            self._config.latitude, self._config.longitude, self._map_bounds, self._size
        )
        if center is None:
            return

        cx, cy = center
        north_lat = self._config.latitude + (10.0 / 60.0)
        north_pixel = latlon_to_pixel(
            north_lat, self._config.longitude, self._map_bounds, self._size
        )
        if north_pixel is None:
            return

        radius_px = abs(cy - north_pixel[1])

        for angle_deg in range(0, 360, 3):
            angle = math.radians(angle_deg)
            x = cx + radius_px * math.cos(angle)
            y = cy + radius_px * math.sin(angle)
            draw.ellipse((x - 1, y - 1, x + 1, y + 1), fill=(100, 100, 100))

        draw.ellipse((cx - 2, cy - 2, cx + 2, cy + 2), fill=RGB_BLACK)

    # === Palette-mode drawing methods (pixel-perfect text, no dithering) ===

    def _draw_info_bar_p(self, draw: ImageDraw.ImageDraw, flight_count: int) -> None:
        bar_height = 24
        y = self._size[1] - bar_height
        w = self._size[0]

        draw.rectangle((0, y, w, self._size[1]), fill=PAL_WHITE)
        draw.line([(0, y), (w, y)], fill=PAL_BLACK, width=1)

        draw.text((8, y + 4), "Just Plane Mosher", fill=PAL_BLACK, font=self._font_title)

        count_text = f"{flight_count} flight{'s' if flight_count != 1 else ''} overhead"
        bbox = draw.textbbox((0, 0), count_text, font=self._font_info)
        text_w = bbox[2] - bbox[0]
        draw.text(((w - text_w) // 2, y + 4), count_text, fill=PAL_BLACK, font=self._font_info)

        now = datetime.now().strftime("%H:%M")
        bbox = draw.textbbox((0, 0), now, font=self._font_info)
        time_w = bbox[2] - bbox[0]
        draw.text((w - time_w - 8, y + 4), now, fill=PAL_BLACK, font=self._font_info)

    def _draw_compass_rose_p(self, draw: ImageDraw.ImageDraw) -> None:
        cx, cy = self._size[0] - 35, 35
        length = 18

        draw.line([(cx, cy - length), (cx, cy + length)], fill=PAL_BLACK, width=2)
        draw.line([(cx - length, cy), (cx + length, cy)], fill=PAL_BLACK, width=2)

        draw.polygon(
            [(cx, cy - length - 5), (cx - 4, cy - length + 3), (cx + 4, cy - length + 3)],
            fill=PAL_BLACK,
        )

        draw.text((cx - 5, cy - length - 18), "N", fill=PAL_BLACK, font=self._font_tiny)

    def _draw_legend_p(self, draw: ImageDraw.ImageDraw) -> None:
        x_start = 8
        y_start = self._size[1] - 100
        box_size = 10
        spacing = 16

        items = [
            (PAL_RED, "<5k ft"),
            (PAL_ORANGE, "5-15k"),
            (PAL_YELLOW, "15-30k"),
            (PAL_BLUE, ">30k ft"),
        ]

        draw.rectangle(
            (x_start - 4, y_start - 4, x_start + 80, y_start + len(items) * spacing + 4),
            fill=PAL_WHITE,
        )

        for i, (color, label) in enumerate(items):
            y = y_start + i * spacing
            draw.rectangle(
                (x_start, y, x_start + box_size, y + box_size),
                fill=color, outline=PAL_BLACK,
            )
            draw.text((x_start + box_size + 5, y - 2), label, fill=PAL_BLACK, font=self._font_tiny)

    def _quantize(self, image: Image.Image) -> Image.Image:
        """Quantize an RGB image to the 7-color e-ink palette with dithering."""
        image = ImageEnhance.Color(image).enhance(1.5)
        image = ImageEnhance.Contrast(image).enhance(1.1)

        palette_data = []
        for r, g, b in PALETTE_RGB:
            palette_data.extend([r, g, b])
        palette_data.extend([0, 0, 0] * (256 - len(PALETTE_RGB)))

        palette_img = Image.new("P", (1, 1))
        palette_img.putpalette(palette_data)

        return image.convert("RGB").quantize(palette=palette_img, dither=Image.Dither.FLOYDSTEINBERG)


def _boxes_overlap(a: tuple, b: tuple) -> bool:
    return not (a[2] < b[0] or a[0] > b[2] or a[3] < b[1] or a[1] > b[3])
