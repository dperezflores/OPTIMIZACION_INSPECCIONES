from __future__ import annotations

from dataclasses import dataclass
from math import asin, cos, radians, sin, sqrt

from .config import OptimizationConfig
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
    """Distancia geodésica entre dos coordenadas."""
    phi1, phi2 = radians(lat1), radians(lat2)
    dphi = radians(lat2 - lat1)
    dlambda = radians(lon2 - lon1)
    a = sin(dphi / 2) ** 2 + cos(phi1) * cos(phi2) * sin(dlambda / 2) ** 2
    return 2 * EARTH_RADIUS_KM * asin(sqrt(a))


def build_travel_matrix(
    obras: list[Obra],
    config: OptimizationConfig,
) -> dict[tuple[str, str], TravelValue]:
    """Matriz V1: Haversine × factor vial / velocidad media.

    No pretende reemplazar Google Routes. Es una aproximación reproducible para
    validar que el modelo espacio-temporal funciona antes de consumir una API.
    """
    matrix: dict[tuple[str, str], TravelValue] = {}
    for origen in obras:
        if origen.latitud is None or origen.longitud is None:
            continue
        for destino in obras:
            if destino.latitud is None or destino.longitud is None:
                continue
            geodesica = haversine_km(
                origen.latitud,
                origen.longitud,
                destino.latitud,
                destino.longitud,
            )
            if origen.obra_id == destino.obra_id or geodesica < 1e-6:
                estimada = 0.0
                minutos = 0.0
            else:
                estimada = geodesica * config.factor_distancia_vial
                minutos = estimada / config.velocidad_promedio_kmh * 60.0
            matrix[(origen.obra_id, destino.obra_id)] = TravelValue(
                distancia_geodesica_km=geodesica,
                distancia_estimada_km=estimada,
                tiempo_estimado_min=minutos,
            )
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
) -> tuple[float, float]:
    km = 0.0
    minutes = 0.0
    ordered = sorted(items, key=lambda x: (x.dia, x.inicio_slot, x.obra_id))
    previous: PlanItem | None = None
    for item in ordered:
        if previous is not None and previous.dia == item.dia:
            value = matrix.get((previous.obra_id, item.obra_id))
            if value:
                km += value.distancia_estimada_km
                minutes += value.tiempo_estimado_min
        previous = item
    return km, minutes


def calculate_plan_travel_metrics(
    plan: list[PlanItem],
    matrix: dict[tuple[str, str], TravelValue],
) -> TravelMetrics:
    """Calcula desplazamientos entre actividades consecutivas por recurso.

    `auditor_km` es km-auditor, no km-vehículo: si dos auditores viajan juntos se
    contabilizan dos desplazamientos personales hasta conocer la regla de vehículos.
    """
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

    def total(groups: dict[str, list[PlanItem]]) -> tuple[float, float]:
        km = minutes = 0.0
        for items in groups.values():
            k, m = _sequence_metrics(items, matrix)
            km += k
            minutes += m
        return km, minutes

    akm, amin = total(by_auditor)
    skm, smin = total(by_supervisor)
    ckm, cmin = total(by_contractor)
    return TravelMetrics(akm, amin, skm, smin, ckm, cmin)
