from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from statistics import pstdev

from .config import OptimizationConfig
from .distance_matrix import TravelValue, calculate_plan_travel_metrics
from .models import PlanItem, TIPO_FISICA


@dataclass(frozen=True)
class QualityMetrics:
    espera_auditor_min: float = 0.0
    desbalance_dia_min: float = 0.0
    desbalance_auditor_min: float = 0.0
    cambios_acompanante: int = 0
    costo_operativo: float = 0.0


def _travel_minutes(
    matrix: dict[tuple[str, str], TravelValue],
    origin: str,
    destination: str,
) -> float:
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


def calculate_quality_metrics(
    plan: list[PlanItem],
    matrix: dict[tuple[str, str], TravelValue],
    config: OptimizationConfig,
) -> QualityMetrics:
    """Calcula calidad operativa comparable entre soluciones del mismo conjunto."""
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

    # Índice interno, sin unidades físicas. Menor = mejor para el mismo conjunto.
    operating_cost = (
        config.peso_calidad_traslado_auditor * travel.auditor_min
        + config.peso_calidad_traslado_supervisor * travel.supervisor_min
        + config.peso_calidad_traslado_contratista * travel.contratista_min
        + config.peso_calidad_espera * waiting
        + config.peso_calidad_balance_dia * day_imbalance
        + config.peso_calidad_balance_auditor * auditor_imbalance
        + config.peso_calidad_cambio_acompanante * companion_changes
    )

    return QualityMetrics(
        espera_auditor_min=waiting,
        desbalance_dia_min=day_imbalance,
        desbalance_auditor_min=auditor_imbalance,
        cambios_acompanante=companion_changes,
        costo_operativo=operating_cost,
    )
