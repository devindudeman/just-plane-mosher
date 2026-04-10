import math
from typing import NamedTuple

EARTH_RADIUS_NM = 3440.065


class MapBounds(NamedTuple):
    north: float
    south: float
    east: float
    west: float


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two points in nautical miles."""
    lat1, lon1, lat2, lon2 = map(math.radians, (lat1, lon1, lat2, lon2))
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_NM * math.asin(math.sqrt(a))


def tile_coords(lat: float, lon: float, zoom: int) -> tuple[int, int]:
    """Convert lat/lon to slippy map tile indices at given zoom level."""
    n = 2 ** zoom
    x = int((lon + 180.0) / 360.0 * n)
    lat_rad = math.radians(lat)
    y = int((1.0 - math.log(math.tan(lat_rad) + 1.0 / math.cos(lat_rad)) / math.pi) / 2.0 * n)
    return x, y


def tile_coords_fractional(lat: float, lon: float, zoom: int) -> tuple[float, float]:
    """Like tile_coords but returns fractional values for sub-tile positioning."""
    n = 2 ** zoom
    x = (lon + 180.0) / 360.0 * n
    lat_rad = math.radians(lat)
    y = (1.0 - math.log(math.tan(lat_rad) + 1.0 / math.cos(lat_rad)) / math.pi) / 2.0 * n
    return x, y


def _mercator_y(lat: float) -> float:
    """Mercator Y projection for a latitude in degrees."""
    lat_rad = math.radians(lat)
    return math.log(math.tan(math.pi / 4.0 + lat_rad / 2.0))


def latlon_to_pixel(
    lat: float,
    lon: float,
    bounds: MapBounds,
    image_size: tuple[int, int],
) -> tuple[int, int] | None:
    """Convert lat/lon to pixel coordinates on the rendered map image.

    Returns None if the point is outside the map bounds.
    """
    width, height = image_size

    if not (bounds.south <= lat <= bounds.north and bounds.west <= lon <= bounds.east):
        return None

    # X is linear in longitude
    px_x = (lon - bounds.west) / (bounds.east - bounds.west) * width

    # Y uses Mercator projection
    merc_north = _mercator_y(bounds.north)
    merc_south = _mercator_y(bounds.south)
    merc_lat = _mercator_y(lat)
    px_y = (merc_north - merc_lat) / (merc_north - merc_south) * height

    return int(px_x), int(px_y)


def compute_map_bounds(
    center_lat: float,
    center_lon: float,
    zoom: int,
    width_px: int,
    height_px: int,
    tile_size: int = 256,
) -> MapBounds:
    """Compute the lat/lon bounds of a map image centered on the given point."""
    n = 2 ** zoom

    # Center in fractional tile coordinates
    cx, cy = tile_coords_fractional(center_lat, center_lon, zoom)

    # Half-dimensions in tile units
    half_w = (width_px / 2.0) / tile_size
    half_h = (height_px / 2.0) / tile_size

    # Bounds in tile coordinates
    left = cx - half_w
    right = cx + half_w
    top = cy - half_h
    bottom = cy + half_h

    # Convert back to lat/lon
    west = left / n * 360.0 - 180.0
    east = right / n * 360.0 - 180.0

    north_rad = math.atan(math.sinh(math.pi * (1 - 2 * top / n)))
    south_rad = math.atan(math.sinh(math.pi * (1 - 2 * bottom / n)))
    north = math.degrees(north_rad)
    south = math.degrees(south_rad)

    return MapBounds(north=north, south=south, east=east, west=west)
