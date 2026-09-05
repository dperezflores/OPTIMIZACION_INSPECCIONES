from __future__ import annotations

from dataclasses import dataclass
from math import asin, cos, radians, sin, sqrt

from .config import OptimizationConfig
from .depot import DEPOT_ID, DEPOT_LATITUDE, DEPOT_LONGITUDE
from .models import Obra, PlanItem


EARTH_RADIUS_KM = 6371.0088


@dataclass(frozen=True)
class TravelValue:
    distancia_geodesica_km: float
    distancia_estimada_km: float
    tiempo_estimado_min: float


@dataclass(frozen=True)
class TravelMetrics:
    auditor_km: float = 0.0
    auditor_min: float = 0.0
    supervisor_km: float = 0.0
    supervisor_min: float = 0.0
    contratista_km: float = 0.0
    contratista_min: float = 0.0

    @property
    def recursos_km(self) -> float:
        return self.auditor_km + self.supervisor_km + self.contratista_km

    @property
    def recursos_min(self) -> float:
        return self.auditor_min + self.supervisor_min + self.contratista_min


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1, phi2 = radians(lat1), radians(lat2)
    dphi = radians(lat2 - lat1)
    dlambda = radians(lon2 - lon1)
    a = sin(dphi / 2) ** 2 + cos(phi1) * cos(phi2) * sin(dlambda / 2) ** 2
    return 2 * EARTH_RADIUS_KM * asin(sqrt(a))


def _travel_value(lat1: float, lon1: float, lat2: float, lon2: float, config: OptimizationConfig) -> TravelValue:
    geodesica = haversine_km(lat1, lon1, lat2, lon2)
    if geodesica < 1e-6:
        estimada = 0.0
        minutos = 0.0
    else:
        estimada = geodesica * config.factor_distancia_vial
        minutos = estimada / config.velocidad_promedio_kmh * 60.0
    return TravelValue(geodesica, estimada, minutos)


def build_travel_matrix(
    obras: list[Obra],
    config: OptimizationConfig,
) -> dict[tuple[str, str], TravelValue]:
    """Matriz Haversine V1 ampliada con el depósito ASEG para V5."""
    matrix: dict[tuple[str, str], TravelValue] = {}
    valid = [o for o in obras if o.latitud is not None and o.longitud is not None]
    for origin in valid:
        for destination in valid:
            matrix[(origin.obra_id, destination.obra_id)] = _travel_value(
                origin.latitud, origin.longitud, destination.latitud, destination.longitud, config
            )
        matrix[(DEPOT_ID, origin.obra_id)] = _travel_value(
            DEPOT_LATITUDE, DEPOT_LONGITUDE, origin.latitud, origin.longitud, config
        )
        matrix[(origin.obra_id, DEPOT_ID)] = _travel_value(
            origin.latitud, origin.longitud, DEPOT_LATITUDE, DEPOT_LONGITUDE, config
        )
    matrix[(DEPOT_ID, DEPOT_ID)] = TravelValue(0.0, 0.0, 0.0)
    return matrix


def travel_slots(
    matrix: dict[tuple[str, str], TravelValue],
    origen_id: str,
    destino_id: str,
    config: OptimizationConfig,
) -> int:
    if not config.incluir_traslados or origen_id == destino_id:
        return 0
    value = matrix.get((origen_id, destino_id))
    if value is None:
        return 0
    return config.traslado_minutos_a_slots(value.tiempo_estimado_min)


def _sequence_metrics(
    items: list[PlanItem],
    matrix: dict[tuple[str, str], TravelValue],
    *,
    include_depot: bool = False,
) -> tuple[float, float]:
    km = 0.0
    minutes = 0.0
    by_day: dict[int, list[PlanItem]] = {}
    for item in items:
        by_day.setdefault(item.dia, []).append(item)

    for day_items in by_day.values():
        ordered = sorted(day_items, key=lambda x: (x.inicio_slot, x.obra_id))
        if not ordered:
            continue
        if include_depot:
            first = matrix.get((DEPOT_ID, ordered[0].obra_id))
            if first:
                km += first.distancia_estimada_km
                minutes += first.tiempo_estimado_min
        for previous, current in zip(ordered, ordered[1:]):
            value = matrix.get((previous.obra_id, current.obra_id))
            if value:
                km += value.distancia_estimada_km
                minutes += value.tiempo_estimado_min
        if include_depot:
            last = matrix.get((ordered[-1].obra_id, DEPOT_ID))
            if last:
                km += last.distancia_estimada_km
                minutes += last.tiempo_estimado_min
    return km, minutes


def calculate_plan_travel_metrics(
    plan: list[PlanItem],
    matrix: dict[tuple[str, str], TravelValue],
) -> TravelMetrics:
    """Calcula desplazamientos por recurso; auditores incluyen salida/regreso a ASEG."""
    by_auditor: dict[str, list[PlanItem]] = {}
    by_supervisor: dict[str, list[PlanItem]] = {}
    by_contractor: dict[str, list[PlanItem]] = {}

    for item in plan:
        by_auditor.setdefault(item.auditor_responsable, []).append(item)
        if item.auditor_acompanante:
            by_auditor.setdefault(item.auditor_acompanante, []).append(item)
        if item.supervisor_seleccionado:
            by_supervisor.setdefault(item.supervisor_seleccionado, []).append(item)
        if item.contratista_id:
            by_contractor.setdefault(item.contratista_id, []).append(item)

    def total(groups: dict[str, list[PlanItem]], include_depot: bool = False) -> tuple[float, float]:
        km = minutes = 0.0
        for items in groups.values():
            k, m = _sequence_metrics(items, matrix, include_depot=include_depot)
            km += k
            minutes += m
        return km, minutes

    akm, amin = total(by_auditor, include_depot=True)
    skm, smin = total(by_supervisor)
    ckm, cmin = total(by_contractor)
    return TravelMetrics(akm, amin, skm, smin, ckm, cmin)
