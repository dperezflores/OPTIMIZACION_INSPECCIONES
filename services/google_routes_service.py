from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Iterable

import requests

from src.depot import DEPOT_ID, DEPOT_LATITUDE, DEPOT_LONGITUDE
from src.distance_matrix import TravelValue
from src.models import Obra


ROUTES_MATRIX_URL = "https://routes.googleapis.com/distanceMatrix/v2:computeRouteMatrix"
FIELD_MASK = "originIndex,destinationIndex,status,condition,distanceMeters,duration"
MAX_ELEMENTS_PER_REQUEST = 625
DEFAULT_CACHE_PATH = Path("data/cache/google_routes_matrix.json")
TRAVEL_MODE = "DRIVE"
ROUTING_PREFERENCE = "TRAFFIC_UNAWARE"
CACHE_SCHEMA_VERSION = 3


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


def _depot_node() -> LocationNode:
    return LocationNode(_coord_key(DEPOT_LATITUDE, DEPOT_LONGITUDE), DEPOT_LATITUDE, DEPOT_LONGITUDE)


def unique_locations(obras: Iterable[Obra]) -> list[LocationNode]:
    nodes: dict[str, LocationNode] = {}
    depot = _depot_node()
    nodes[depot.key] = depot
    for obra in obras:
        if obra.latitud is None or obra.longitud is None:
            continue
        key = _coord_key(obra.latitud, obra.longitud)
        nodes.setdefault(key, LocationNode(key, obra.latitud, obra.longitud))
    return sorted(nodes.values(), key=lambda n: n.key)


def matrix_signature(obras: Iterable[Obra]) -> str:
    settings = f"v{CACHE_SCHEMA_VERSION}|{TRAVEL_MODE}|{ROUTING_PREFERENCE}|depot:{DEPOT_LATITUDE:.7f},{DEPOT_LONGITUDE:.7f}"
    coordinates = "|".join(n.key for n in unique_locations(obras))
    payload = f"{settings}|{coordinates}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:20]


def _duration_seconds(value: object) -> float:
    if value is None:
        return 0.0
    text = str(value).strip()
    if text.endswith("s"):
        text = text[:-1]
    return float(text or 0.0)


def _waypoint(node: LocationNode) -> dict:
    return {"waypoint": {"location": {"latLng": {"latitude": node.latitude, "longitude": node.longitude}}}}


def _batch_pairs(nodes: list[LocationNode]) -> list[tuple[list[LocationNode], list[LocationNode]]]:
    chunk = 25
    batches = []
    for i in range(0, len(nodes), chunk):
        origins = nodes[i : i + chunk]
        for j in range(0, len(nodes), chunk):
            destinations = nodes[j : j + chunk]
            if len(origins) * len(destinations) > MAX_ELEMENTS_PER_REQUEST:
                raise AssertionError("Lote de Google Routes excede 625 elementos.")
            batches.append((origins, destinations))
    return batches


def _request_batch(api_key: str, origins: list[LocationNode], destinations: list[LocationNode], timeout_seconds: float) -> dict[tuple[str, str], TravelValue]:
    payload = {
        "origins": [_waypoint(n) for n in origins],
        "destinations": [_waypoint(n) for n in destinations],
        "travelMode": TRAVEL_MODE,
        "routingPreference": ROUTING_PREFERENCE,
    }
    response = requests.post(
        ROUTES_MATRIX_URL,
        headers={"Content-Type": "application/json", "X-Goog-Api-Key": api_key, "X-Goog-FieldMask": FIELD_MASK},
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
        if oi >= len(origins) or di >= len(destinations):
            raise RuntimeError("Google Routes devolvió índices fuera del lote solicitado.")
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
                f"Google Routes no devolvió ruta válida entre {origin.key} y {destination.key}. status={status!r}, condition={condition!r}"
            )
        distance_km = float(element.get("distanceMeters", 0.0)) / 1000.0
        duration_min = _duration_seconds(element.get("duration")) / 60.0
        result[(origin.key, destination.key)] = TravelValue(distance_km, distance_km, duration_min)
    return result


def _expand_to_obras(obras: list[Obra], location_matrix: dict[tuple[str, str], TravelValue]) -> dict[tuple[str, str], TravelValue]:
    result: dict[tuple[str, str], TravelValue] = {}
    depot_key = _coord_key(DEPOT_LATITUDE, DEPOT_LONGITUDE)
    for origin in obras:
        if origin.latitud is None or origin.longitud is None:
            continue
        origin_key = _coord_key(origin.latitud, origin.longitud)
        for destination in obras:
            if destination.latitud is None or destination.longitud is None:
                continue
            destination_key = _coord_key(destination.latitud, destination.longitud)
            value = location_matrix.get((origin_key, destination_key))
            if value is not None:
                result[(origin.obra_id, destination.obra_id)] = value
        to_obra = location_matrix.get((depot_key, origin_key))
        to_depot = location_matrix.get((origin_key, depot_key))
        if to_obra is not None:
            result[(DEPOT_ID, origin.obra_id)] = to_obra
        if to_depot is not None:
            result[(origin.obra_id, DEPOT_ID)] = to_depot
    result[(DEPOT_ID, DEPOT_ID)] = TravelValue(0.0, 0.0, 0.0)
    return result


def save_cache(obras: list[Obra], location_matrix: dict[tuple[str, str], TravelValue], cache_path: str | Path = DEFAULT_CACHE_PATH) -> Path:
    path = Path(cache_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": CACHE_SCHEMA_VERSION,
        "provider": "google_routes",
        "travel_mode": TRAVEL_MODE,
        "routing_preference": ROUTING_PREFERENCE,
        "signature": matrix_signature(obras),
        "entries": [
            {"origin": origin, "destination": destination, "distance_km": value.distancia_estimada_km, "duration_min": value.tiempo_estimado_min}
            for (origin, destination), value in sorted(location_matrix.items())
        ],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_cache(obras: list[Obra], cache_path: str | Path = DEFAULT_CACHE_PATH) -> GoogleRoutesMatrix | None:
    path = Path(cache_path)
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if raw.get("version") != CACHE_SCHEMA_VERSION or raw.get("provider") != "google_routes" or raw.get("signature") != matrix_signature(obras):
        return None

    location_matrix: dict[tuple[str, str], TravelValue] = {}
    for row in raw.get("entries", []):
        distance_km = float(row["distance_km"])
        duration_min = float(row["duration_min"])
        location_matrix[(row["origin"], row["destination"])] = TravelValue(distance_km, distance_km, duration_min)

    nodes = unique_locations(obras)
    expected = len(nodes) * len(nodes)
    if len(location_matrix) != expected:
        return None
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
    if not nodes:
        raise ValueError("No hay coordenadas válidas para construir la matriz Google Routes.")
    location_matrix: dict[tuple[str, str], TravelValue] = {}
    billed_elements = 0
    for origins, destinations in _batch_pairs(nodes):
        billed_elements += len(origins) * len(destinations)
        location_matrix.update(_request_batch(api_key.strip(), origins, destinations, timeout_seconds))

    expected = len(nodes) * len(nodes)
    if len(location_matrix) != expected:
        raise RuntimeError(f"Matriz Google incompleta: {len(location_matrix)} de {expected} elementos. No se guardó caché.")
    save_cache(obras, location_matrix, cache_path)
    return GoogleRoutesMatrix(
        matrix=_expand_to_obras(obras, location_matrix),
        unique_locations=len(nodes),
        billed_elements=billed_elements,
        source="google_routes",
        cache_path=str(cache_path),
    )
