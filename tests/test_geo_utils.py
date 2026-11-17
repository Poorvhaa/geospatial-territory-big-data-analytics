"""Unit tests for geospatial utilities (Haversine, destination point, and H3 v4)."""

import pytest

from src.geo_utils import (
    haversine_distance_m,
    destination_point,
    calculate_bearing,
    point_to_h3,
    is_valid_h3,
    h3_smoke_test,
)


def test_haversine_zero_distance():
    """Distance between identical coordinates must be 0.0."""
    dist = haversine_distance_m(41.8781, -87.6298, 41.8781, -87.6298)
    assert dist == 0.0


def test_haversine_symmetry():
    """Haversine distance must be symmetric."""
    p1 = (41.8781, -87.6298)
    p2 = (41.8900, -87.6100)
    d1 = haversine_distance_m(p1[0], p1[1], p2[0], p2[1])
    d2 = haversine_distance_m(p2[0], p2[1], p1[0], p1[1])
    assert abs(d1 - d2) < 1e-6
    assert d1 > 1000.0  # Around ~2 km


def test_haversine_known_meridian_distance():
    """1 degree of latitude is approximately 111.195 km."""
    d = haversine_distance_m(0.0, 0.0, 1.0, 0.0)
    assert 110_000 < d < 112_000


def test_destination_point_zero_distance():
    """Zero distance destination should equal starting point."""
    lat, lon = destination_point(41.8781, -87.6298, 0.0, 90.0)
    assert pytest.approx(lat, abs=1e-6) == 41.8781
    assert pytest.approx(lon, abs=1e-6) == -87.6298


def test_destination_point_due_north():
    """Moving due North (bearing 0) should increase latitude."""
    lat1, lon1 = 41.8781, -87.6298
    lat2, lon2 = destination_point(lat1, lon1, 1000.0, 0.0)
    assert lat2 > lat1
    assert pytest.approx(lon2, abs=1e-4) == lon1
    # Check that Haversine confirms ~1000m
    d = haversine_distance_m(lat1, lon1, lat2, lon2)
    assert pytest.approx(d, rel=1e-3) == 1000.0


def test_calculate_bearing():
    """Bearing due North should be near 0 degrees."""
    b = calculate_bearing(41.8781, -87.6298, 41.8981, -87.6298)
    assert pytest.approx(b, abs=0.5) == 0.0 or pytest.approx(b, abs=0.5) == 360.0


def test_h3_cell_generation_and_validation():
    """Modern H3 4.x API should produce valid resolution 9 cells."""
    lat, lon = 41.8781, -87.6298
    cell = point_to_h3(lat, lon, resolution=9)
    assert isinstance(cell, str)
    assert len(cell) == 15
    assert is_valid_h3(cell) is True
    assert is_valid_h3("invalid_cell_string") is False


def test_h3_smoke_test():
    """H3 smoke test function should return (True, cell_str)."""
    valid, cell = h3_smoke_test()
    assert valid is True
    assert isinstance(cell, str)
    assert len(cell) > 10
