import logging
import time

import requests

from src.config import Config
from src.models import Aircraft, FlightInfo, TrackedFlight

logger = logging.getLogger("mosher.flights")

ADSB_LOL_URL = "https://api.adsb.lol/v2/point"
ADSBDB_URL = "https://api.adsbdb.com/v0/callsign"
CACHE_TTL = 3600  # 1 hour


class ADSBClient:
    def __init__(self, config: Config):
        self._config = config
        self._session = requests.Session()
        self._session.headers["User-Agent"] = "JustPlaneMosher/1.0"
        self._callsign_cache: dict[str, tuple[FlightInfo | None, float]] = {}

    def fetch_aircraft(self) -> list[Aircraft]:
        """Fetch current aircraft from ADSB.lol within configured radius."""
        url = f"{ADSB_LOL_URL}/{self._config.latitude}/{self._config.longitude}/{self._config.radius_nm}"
        try:
            resp = self._session.get(url, timeout=10)
            resp.raise_for_status()
            data = resp.json()
        except (requests.RequestException, ValueError) as e:
            logger.warning("Failed to fetch aircraft: %s", e)
            return []

        aircraft_list = []
        for ac in data.get("ac", []):
            # Skip entries missing position
            if ac.get("lat") is None or ac.get("lon") is None:
                continue

            # Skip ground vehicles
            alt = ac.get("alt_baro")
            if alt == "ground" or (isinstance(alt, (int, float)) and alt < 100):
                continue

            # Skip stale positions
            if ac.get("seen", 0) > 60:
                continue

            # Parse callsign
            callsign = ac.get("flight", "").strip() or None

            aircraft_list.append(
                Aircraft(
                    hex=ac.get("hex", ""),
                    callsign=callsign,
                    lat=float(ac["lat"]),
                    lon=float(ac["lon"]),
                    altitude_ft=int(alt) if isinstance(alt, (int, float)) else None,
                    ground_speed_kt=ac.get("gs"),
                    track_deg=ac.get("track"),
                    aircraft_type=ac.get("t"),
                    registration=ac.get("r"),
                    distance_nm=ac.get("dst"),
                )
            )

        # Sort by distance
        aircraft_list.sort(key=lambda a: a.distance_nm if a.distance_nm is not None else 9999)
        return aircraft_list

    def enrich_flight(self, callsign: str) -> FlightInfo | None:
        """Look up airline/route info for a callsign via ADSBdb. Cached."""
        now = time.time()

        # Check cache
        if callsign in self._callsign_cache:
            cached_info, cached_at = self._callsign_cache[callsign]
            if now - cached_at < CACHE_TTL:
                return cached_info

        try:
            resp = self._session.get(f"{ADSBDB_URL}/{callsign}", timeout=10)
            if resp.status_code == 404:
                # Cache the miss
                self._callsign_cache[callsign] = (None, now)
                return None
            resp.raise_for_status()
            data = resp.json()
        except (requests.RequestException, ValueError) as e:
            logger.debug("ADSBdb lookup failed for %s: %s", callsign, e)
            # Don't cache network errors — retry next cycle
            return None

        try:
            route = data["response"]["flightroute"]
            airline = route.get("airline", {})
            origin = route.get("origin", {})
            destination = route.get("destination", {})

            info = FlightInfo(
                callsign=callsign,
                airline_name=airline.get("name"),
                origin_iata=origin.get("iata_code"),
                origin_name=origin.get("name"),
                destination_iata=destination.get("iata_code"),
                destination_name=destination.get("name"),
                fetched_at=now,
            )
            self._callsign_cache[callsign] = (info, now)
            return info
        except (KeyError, TypeError):
            self._callsign_cache[callsign] = (None, now)
            return None

    def get_tracked_flights(self) -> list[TrackedFlight]:
        """Fetch aircraft and enrich with flight info."""
        aircraft_list = self.fetch_aircraft()
        tracked = []

        for ac in aircraft_list:
            info = None
            if ac.callsign:
                info = self.enrich_flight(ac.callsign)
                # Rate limit ADSBdb calls
                time.sleep(0.2)

            tracked.append(TrackedFlight(aircraft=ac, info=info))

        return tracked
