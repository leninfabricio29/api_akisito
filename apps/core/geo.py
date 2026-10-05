"""Utilidades geográficas sin dependencia de PostGIS."""

import math
from decimal import Decimal

EARTH_RADIUS_M = 6_371_000


def haversine_m(lat1, lon1, lat2, lon2) -> float:
    """Distancia en metros entre dos coordenadas (grados decimales)."""
    lat1, lon1, lat2, lon2 = (float(v) for v in (lat1, lon1, lat2, lon2))
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def bounding_box(lat, lon, radius_m):
    """Caja (min_lat, max_lat, min_lon, max_lon) que contiene el círculo; sirve para prefiltrar en SQL."""
    lat, lon = float(lat), float(lon)
    d_lat = math.degrees(radius_m / EARTH_RADIUS_M)
    cos_lat = max(math.cos(math.radians(lat)), 1e-6)
    d_lon = math.degrees(radius_m / (EARTH_RADIUS_M * cos_lat))
    return (
        Decimal(str(lat - d_lat)),
        Decimal(str(lat + d_lat)),
        Decimal(str(lon - d_lon)),
        Decimal(str(lon + d_lon)),
    )
