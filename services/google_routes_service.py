from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Iterable

import requests

from src.distance_matrix import TravelValue
from src.models import Obra


ROUTES_MATRIX_URL = "https://routes.googleapis.com/distanceMatrix/v2:computeRouteMatrix"
FIELD_MASK = "originIndex,destinationIndex,status,condition,distanceMeters,duration"
MAX_ELEMENTS_PER_REQUEST = 625
DEFAULT_CACHE_PATH = Path("data/cache/google_routes_matrix.json")


@dataclass(frozen=True)
class LocationNode:
    key: str
    latitude: float
    longitude: float


@dataclass(frozen=True)
class GoogleRoutesMatrix:
    matrix: dict[tuple[str, str], TravelValue]
    unique_locations: int
    billed_elements: int
    source: str
    cache_path: str | None = None


def _coord_key(lat: float, lon: float) -> str:
    return f"{lat:.7f},{lon:.7f}"


def unique_locations(obras: Iterable[Obra]) -> list[LocationNode]:
    nodes: dict[str, LocationNode] = {}
    for obra in obras:
        if obra.latitud is None or obra.longitud is None:
            continue
        key = _coord_key(obra.latitud, obra.longitud)
        nodes.setdefault(key, LocationNode(key, obra.latitud, obra.longitud))
    return sorted(nodes.values(), key=lambda n: n.key)


def matrix_signature(obras: Iterable[Obra]) -> str:
    payload = "|".join(n.key for n in unique_locations(obras))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:20]


def _duration_seconds(value: object) -> float:
    if value is None:
        return 0.0
    text = str(value).strip()
    if text.endswith("s"):
        text = text[:-1]
    return float(text or 0.0)


def _waypoint(node: LocationNode) -> dict:
    return {
        "waypoint": {
            "location": {
                "latLng": {
                    "latitude": node.latitude,
                    "longitude": node.longitude,
                }
            }
        }
    }


def _batch_pairs(nodes: list[LocationNode]) -> list[tuple[list[LocationNode], list[LocationNode]]]:
    # Bloques 25×25 = 625 elementos, límite actual de Compute Route Matrix.
    chunk = 25
    batches = []
    for i in range(0, len(nodes), chunk):
        origins = nodes[i : i + chunk]
        for j in range(0, len(nodes), chunk):
            destinations = nodes[j : j + chunk]
            batches.append((origins, destinations))
    return batches


def _request_batch(
    api_key: str,
    origins: list[LocationNode],
    destinations: list[LocationNode],
    timeout_seconds: float,
) -> dict[tuple[str, str], TravelValue]:
    payload = {
        "origins": [_waypoint(n) for n in origins],
        "destinations": [_waypoint(n) for n in destinations],
        "travelMode": "DRIVE",
        # No usamos tráfico dependiente de hora/fecha en esta primera V2.
        "routingPreference": "TRAFFIC_UNAWARE",
    }
    response = requests.post(
        ROUTES_MATRIX_URL,
        headers={
            "Content-Type": "application/json",
            "X-Goog-Api-Key": api_key,
            "X-Goog-FieldMask": FIELD_MASK,
        },
        json=payload,
        timeout=timeout_seconds,
    )
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, list):
        raise RuntimeError("Respuesta inesperada de Google Routes: se esperaba una lista de elementos.")

    result: dict[tuple[str, str], TravelValue] = {}
    for element in data:
        oi = int(element.get("originIndex", 0))
        di = int(element.get("destinationIndex", 0))
        origin = origins[oi]
        destination = destinations[di]
        status = element.get("status") or {}
        code = int(status.get("code", 0) or 0)
        condition = str(element.get("condition", "ROUTE_EXISTS"))

        if origin.key == destination.key:
            result[(origin.key, destination.key)] = TravelValue(0.0, 0.0, 0.0)
            continue
        if code != 0 or condition == "ROUTE_NOT_FOUND":
            raise RuntimeError(
                f"Google Routes no devolvió ruta válida entre {origin.key} y {destination.key}. "
                f"status={status!r}, condition={condition!r}"
            )

        distance_km = float(element.get("distanceMeters", 0.0)) / 1000.0
        duration_min = _duration_seconds(element.get("duration")) / 60.0
        result[(origin.key, destination.key)] = TravelValue(
            distancia_geodesica_km=distance_km,
            distancia_estimada_km=distance_km,
            tiempo_estimado_min=duration_min,
        )
    return result


def _expand_to_obras(
    obras: list[Obra],
    location_matrix: dict[tuple[str, str], TravelValue],
) -> dict[tuple[str, str], TravelValue]:
    result: dict[tuple[str, str], TravelValue] = {}
    for origin in obras:
        if origin.latitud is None or origin.longitud is None:
            continue
        ok = _coord_key(origin.latitud, origin.longitud)
        for destination in obras:
            if destination.latitud is None or destination.longitud is None:
                continue
            dk = _coord_key(destination.latitud, destination.longitud)
            value = location_matrix.get((ok, dk))
            if value is not None:
                result[(origin.obra_id, destination.obra_id)] = value
    return result


def save_cache(
    obras: list[Obra],
    location_matrix: dict[tuple[str, str], TravelValue],
    cache_path: str | Path = DEFAULT_CACHE_PATH,
) -> Path:
    path = Path(cache_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "provider": "google_routes",
        "signature": matrix_signature(obras),
        "entries": [
            {
                "origin": origin,
                "destination": destination,
                "distance_km": value.distancia_estimada_km,
                "duration_min": value.tiempo_estimado_min,
            }
            for (origin, destination), value in sorted(location_matrix.items())
        ],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_cache(
    obras: list[Obra],
    cache_path: str | Path = DEFAULT_CACHE_PATH,
) -> GoogleRoutesMatrix | None:
    path = Path(cache_path)
    if not path.exists():
        return None
    raw = json.loads(path.read_text(encoding="utf-8"))
    if raw.get("provider") != "google_routes" or raw.get("signature") != matrix_signature(obras):
        return None

    location_matrix: dict[tuple[str, str], TravelValue] = {}
    for row in raw.get("entries", []):
        distance_km = float(row["distance_km"])
        duration_min = float(row["duration_min"])
        location_matrix[(row["origin"], row["destination"])] = TravelValue(
            distancia_geodesica_km=distance_km,
            distancia_estimada_km=distance_km,
            tiempo_estimado_min=duration_min,
        )

    nodes = unique_locations(obras)
    return GoogleRoutesMatrix(
        matrix=_expand_to_obras(obras, location_matrix),
        unique_locations=len(nodes),
        billed_elements=0,
        source="google_cache",
        cache_path=str(path),
    )


def build_google_routes_matrix(
    obras: list[Obra],
    api_key: str,
    *,
    cache_path: str | Path = DEFAULT_CACHE_PATH,
    force_refresh: bool = False,
    timeout_seconds: float = 60.0,
) -> GoogleRoutesMatrix:
    if not api_key or not api_key.strip():
        raise ValueError("Falta GOOGLE_MAPS_API_KEY.")

    if not force_refresh:
        cached = load_cache(obras, cache_path)
        if cached is not None:
            return cached

    nodes = unique_locations(obras)
    location_matrix: dict[tuple[str, str], TravelValue] = {}
    billed_elements = 0
    for origins, destinations in _batch_pairs(nodes):
        billed_elements += len(origins) * len(destinations)
        location_matrix.update(
            _request_batch(api_key.strip(), origins, destinations, timeout_seconds)
        )

    save_cache(obras, location_matrix, cache_path)
    return GoogleRoutesMatrix(
        matrix=_expand_to_obras(obras, location_matrix),
        unique_locations=len(nodes),
        billed_elements=billed_elements,
        source="google_routes",
        cache_path=str(cache_path),
    )
