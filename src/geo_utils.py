"""Geospatial utilities: Haversine distance, dead-reckoning movement, and H3 v4 indexing."""

from __future__ import annotations

import math
from typing import Tuple

try:
    import h3
except ImportError:
    h3 = None  # type: ignore

# Mean Earth radius in meters (WGS-84 / IUGG recommended)
EARTH_RADIUS_M = 6371000.0


def haversine_distance_m(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> float:
    """Calculate the great-circle distance between two points in meters using the Haversine formula.

    Args:
        lat1: Latitude of first point in decimal degrees.
        lon1: Longitude of first point in decimal degrees.
        lat2: Latitude of second point in decimal degrees.
        lon2: Longitude of second point in decimal degrees.

    Returns:
        Great-circle distance in meters.
    """
    if lat1 == lat2 and lon1 == lon2:
        return 0.0

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    )
    # Clip to [0, 1] to avoid float precision issues with math.sqrt
    a = min(1.0, max(0.0, a))
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))

    return EARTH_RADIUS_M * c


def destination_point(
    lat: float,
    lon: float,
    distance_m: float,
    bearing_deg: float,
) -> Tuple[float, float]:
    """Calculate destination coordinates given a starting point, distance in meters, and bearing in degrees.

    Args:
        lat: Starting latitude in decimal degrees.
        lon: Starting longitude in decimal degrees.
        distance_m: Travel distance in meters.
        bearing_deg: Travel bearing in degrees (0 = North, 90 = East, etc.).

    Returns:
        Tuple of (destination_latitude, destination_longitude) in decimal degrees.
    """
    if distance_m == 0.0:
        return lat, lon

    angular_dist = distance_m / EARTH_RADIUS_M
    theta = math.radians(bearing_deg)
    phi1 = math.radians(lat)
    lambda1 = math.radians(lon)

    phi2 = math.asin(
        math.sin(phi1) * math.cos(angular_dist)
        + math.cos(phi1) * math.sin(angular_dist) * math.cos(theta)
    )

    lambda2 = lambda1 + math.atan2(
        math.sin(theta) * math.sin(angular_dist) * math.cos(phi1),
        math.cos(angular_dist) - math.sin(phi1) * math.sin(phi2),
    )

    # Normalize longitude to [-180, 180]
    lon_deg = (math.degrees(lambda2) + 540.0) % 360.0 - 180.0
    lat_deg = math.degrees(phi2)

    return lat_deg, lon_deg


def calculate_bearing(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> float:
    """Calculate the initial bearing in degrees (0-360) from point 1 to point 2."""
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_lambda = math.radians(lon2 - lon1)

    y = math.sin(delta_lambda) * math.cos(phi2)
    x = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(delta_lambda)

    bearing = (math.degrees(math.atan2(y, x)) + 360.0) % 360.0
    return bearing


def point_to_h3(lat: float, lon: float, resolution: int = 9) -> str:
    """Convert (latitude, longitude) to H3 index string using the H3 4.x API."""
    if h3 is None:
        raise ImportError("The 'h3' package is not installed. Install h3>=4.0.0.")
    return h3.latlng_to_cell(lat, lon, resolution)


def is_valid_h3(cell: str) -> bool:
    """Validate whether an H3 cell index string is valid using the H3 4.x API."""
    if h3 is None:
        raise ImportError("The 'h3' package is not installed. Install h3>=4.0.0.")
    return bool(h3.is_valid_cell(cell))


def h3_smoke_test(
    lat: float = 41.8781,
    lon: float = -87.6298,
    resolution: int = 9,
) -> Tuple[bool, str]:
    """Perform a lightweight H3 4.x smoke test.

    Returns:
        Tuple of (is_valid, cell_index_string).
    """
    cell = point_to_h3(lat, lon, resolution)
    valid = is_valid_h3(cell)
    return valid, cell
