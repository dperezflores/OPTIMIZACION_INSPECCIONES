from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from statistics import pstdev

from .config import OptimizationConfig
from .depot import DEPOT_ID
from .distance_matrix import TravelValue, calculate_plan_travel_metrics, travel_slots
from .models import PlanItem, TIPO_FISICA
from .vehicle_planner import calculate_vehicle_plan


@dataclass(frozen=True)
class QualityMetrics:
    espera_auditor_min: float = 0.0
    desbalance_dia_min: float = 0.0
    desbalance_auditor_min: float = 0.0
    cambios_acompanante: int = 0
    tiempo_adicional_traslado_min: float = 0.0
    costo_operativo: float = 0.0
    vehicle_rendezvous_issues: int = 0


def _travel_minutes(matrix: dict[tuple[str, str], TravelValue], origin: str, destination: str) -> float:
    value = matrix.get((origin, destination))
    return value.tiempo_estimado_min if value else 0.0


def _auditor_sequences(plan: list[PlanItem]) -> dict[tuple[str, int], list[PlanItem]]:
    groups: dict[tuple[str, int], list[PlanItem]] = defaultdict(list)
    for item in plan:
        groups[(item.auditor_responsable, item.dia)].append(item)
        if item.auditor_acompanante:
            groups[(item.auditor_acompanante, item.dia)].append(item)
    for items in groups.values():
        items.sort(key=lambda x: (x.inicio_slot, x.fin_slot, x.obra_id))
    return groups


def _additional_depot_time(
    sequences: dict[tuple[str, int], list[PlanItem]],
    matrix: dict[tuple[str, str], TravelValue],
    config: OptimizationConfig,
) -> float:
    """Minutos de traslado que quedan fuera de la ventana de actividades 08:00-17:00."""
    total = 0.0
    horizon = config.slots_por_dia
    for items in sequences.values():
        if not items:
            continue
        first = items[0]
        last = items[-1]
        outbound = travel_slots(matrix, DEPOT_ID, first.obra_id, config)
        inbound = travel_slots(matrix, last.obra_id, DEPOT_ID, config)
        departure_slot = first.inicio_slot - outbound
        return_slot = last.fin_slot + inbound
        total += max(0, -departure_slot) * config.slot_minutos
        total += max(0, return_slot - horizon) * config.slot_minutos
    return total


def calculate_quality_metrics(
    plan: list[PlanItem],
    matrix: dict[tuple[str, str], TravelValue],
    config: OptimizationConfig,
) -> QualityMetrics:
    sequences = _auditor_sequences(plan)
    waiting = 0.0
    auditor_load: dict[str, float] = defaultdict(float)
    day_load: dict[int, float] = defaultdict(float)

    for (auditor, day), items in sequences.items():
        previous: PlanItem | None = None
        for item in items:
            duration = (item.fin_slot - item.inicio_slot) * config.slot_minutos
            auditor_load[auditor] += duration
            day_load[day] += duration
            if previous is not None:
                gap = (item.inicio_slot - previous.fin_slot) * config.slot_minutos
                travel = _travel_minutes(matrix, previous.obra_id, item.obra_id)
                waiting += max(0.0, gap - travel)
            previous = item

    day_values = list(day_load.values())
    day_imbalance = (max(day_values) - min(day_values)) if len(day_values) > 1 else 0.0
    auditor_values = list(auditor_load.values())
    auditor_imbalance = pstdev(auditor_values) if len(auditor_values) > 1 else 0.0

    by_responsible_day: dict[tuple[str, int], list[PlanItem]] = defaultdict(list)
    for item in plan:
        if item.tipo_revision == TIPO_FISICA and item.auditor_acompanante:
            by_responsible_day[(item.auditor_responsable, item.dia)].append(item)

    companion_changes = 0
    for items in by_responsible_day.values():
        items.sort(key=lambda x: (x.inicio_slot, x.obra_id))
        previous_companion: str | None = None
        for item in items:
            if previous_companion is not None and item.auditor_acompanante != previous_companion:
                companion_changes += 1
            previous_companion = item.auditor_acompanante

    travel = calculate_plan_travel_metrics(plan, matrix)
    vehicle = calculate_vehicle_plan(plan, matrix, config)
    additional_time = _additional_depot_time(sequences, matrix, config)

    operating_cost = (
        config.peso_calidad_traslado_auditor * travel.auditor_min
        + config.peso_calidad_traslado_supervisor * travel.supervisor_min
        + config.peso_calidad_traslado_contratista * travel.contratista_min
        + config.peso_calidad_espera * waiting
        + config.peso_calidad_balance_dia * day_imbalance
        + config.peso_calidad_balance_auditor * auditor_imbalance
        + config.peso_calidad_cambio_acompanante * companion_changes
        + config.peso_calidad_km_vehiculo * vehicle.vehicle_km
        + config.peso_calidad_viaje_solo * vehicle.solo_legs
        + config.peso_calidad_viaje_vehicular * vehicle.vehicle_trips
        + config.peso_calidad_tiempo_adicional * additional_time
        + 5000.0 * vehicle.rendezvous_issues
    )

    return QualityMetrics(
        espera_auditor_min=waiting,
        desbalance_dia_min=day_imbalance,
        desbalance_auditor_min=auditor_imbalance,
        cambios_acompanante=companion_changes,
        tiempo_adicional_traslado_min=additional_time,
        costo_operativo=operating_cost,
        vehicle_rendezvous_issues=vehicle.rendezvous_issues,
    )
