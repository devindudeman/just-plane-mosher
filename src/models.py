from dataclasses import dataclass


@dataclass
class Aircraft:
    hex: str
    callsign: str | None
    lat: float
    lon: float
    altitude_ft: int | None
    ground_speed_kt: float | None
    track_deg: float | None
    aircraft_type: str | None
    registration: str | None
    distance_nm: float | None


@dataclass
class FlightInfo:
    callsign: str
    airline_name: str | None
    origin_iata: str | None
    origin_name: str | None
    destination_iata: str | None
    destination_name: str | None
    fetched_at: float


@dataclass
class TrackedFlight:
    aircraft: Aircraft
    info: FlightInfo | None
