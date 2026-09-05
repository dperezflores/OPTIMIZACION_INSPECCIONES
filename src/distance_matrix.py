from __future__ import annotations

from math import asin, cos, radians, sin, sqrt

from .models import Obra


EARTH_RADIUS_KM = 6371.0088


def haversine_km(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> float:
    """Distancia geodésica. Se usará sólo como aproximación en la V1."""
    phi1, phi2 = radians(lat1), radians(lat2)
    dphi = radians(lat2 - lat1)
    dlambda = radians(lon2 - lon1)

    a = (
        sin(dphi / 2) ** 2
        + cos(phi1) * cos(phi2) * sin(dlambda / 2) ** 2
    )
    return 2 * EARTH_RADIUS_KM * asin(sqrt(a))


def build_haversine_matrix(obras: list[Obra]) -> dict[tuple[str, str], float]:
    matrix: dict[tuple[str, str], float] = {}
    for origen in obras:
        if origen.latitud is None or origen.longitud is None:
            continue
        for destino in obras:
            if destino.latitud is None or destino.longitud is None:
                continue
            matrix[(origen.obra_id, destino.obra_id)] = haversine_km(
                origen.latitud,
                origen.longitud,
                destino.latitud,
                destino.longitud,
            )
    return matrix
