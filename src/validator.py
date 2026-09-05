from __future__ import annotations

import math

from .config import OptimizationConfig
from .models import Auditor, Obra


class ValidationError(ValueError):
    pass


def validate_dataset(
    obras: list[Obra],
    auditores: list[Auditor],
    config: OptimizationConfig,
) -> list[str]:
    """Valida errores duros y devuelve advertencias no bloqueantes."""
    warnings: list[str] = []

    if not obras:
        raise ValidationError("No existen obras para optimizar.")
    if len(auditores) < 2:
        raise ValidationError(
            "Se requieren al menos dos auditores disponibles."
        )

    auditor_ids = [a.auditor_id for a in auditores if a.disponible]
    auditor_set = set(auditor_ids)
    if len(auditor_set) != len(auditor_ids):
        raise ValidationError("Hay auditores duplicados.")

    obra_ids = [o.obra_id for o in obras]
    if len(set(obra_ids)) != len(obra_ids):
        raise ValidationError("Hay obra_id duplicados.")

    for obra in obras:
        if obra.auditor_responsable not in auditor_set:
            raise ValidationError(
                f"Obra {obra.obra_id}: el auditor responsable "
                f"{obra.auditor_responsable!r} no está disponible."
            )
        if obra.duracion_minutos <= 0:
            raise ValidationError(
                f"Obra {obra.obra_id}: duración inválida."
            )
        if not 1 <= obra.prioridad <= 5:
            raise ValidationError(
                f"Obra {obra.obra_id}: prioridad debe estar entre 1 y 5."
            )
        if (obra.latitud is None) != (obra.longitud is None):
            warnings.append(
                f"Obra {obra.obra_id}: sólo una coordenada está informada."
            )
        if obra.latitud is not None and not (-90 <= obra.latitud <= 90):
            raise ValidationError(
                f"Obra {obra.obra_id}: latitud fuera de rango."
            )
        if obra.longitud is not None and not (-180 <= obra.longitud <= 180):
            raise ValidationError(
                f"Obra {obra.obra_id}: longitud fuera de rango."
            )

    if config.modo_parejas != "estables_por_dia":
        raise ValidationError(
            "La V0 sólo implementa modo_parejas='estables_por_dia'."
        )

    return warnings


def theoretical_lower_bound_days(
    obras: list[Obra],
    auditores: list[Auditor],
    config: OptimizationConfig,
) -> int:
    """Cota inferior sin traslados: demanda total y carga del responsable."""
    disponibles = [a for a in auditores if a.disponible]
    capacidad_diaria = len(disponibles) * config.minutos_jornada

    # Cada inspección consume simultáneamente dos auditores.
    demanda_auditor_min = 2 * sum(o.duracion_minutos for o in obras)
    lb_capacidad = math.ceil(demanda_auditor_min / capacidad_diaria)

    por_responsable: dict[str, int] = {}
    for obra in obras:
        por_responsable[obra.auditor_responsable] = (
            por_responsable.get(obra.auditor_responsable, 0)
            + obra.duracion_minutos
        )
    lb_responsable = max(
        math.ceil(total / config.minutos_jornada)
        for total in por_responsable.values()
    )

    return max(1, lb_capacidad, lb_responsable)
