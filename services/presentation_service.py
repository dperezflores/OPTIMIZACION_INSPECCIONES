from __future__ import annotations

from datetime import datetime

import pandas as pd

from src.config import OptimizationConfig
from src.optimizer import OptimizationRun
from .optimization_service import OptimizationContext


def build_scenarios_dataframe(run: OptimizationRun) -> pd.DataFrame:
    rows = []
    for result in run.scenarios:
        rows.append(
            {
                "Días": result.dias,
                "Estado": (
                    "Factible"
                    if result.factible
                    else "No factible"
                    if result.probado_infactible
                    else result.status
                ),
                "Tiempo solver (s)": round(result.wall_time_seconds, 2),
                "Objetivo": result.objective_value,
            }
        )
    return pd.DataFrame(rows)


def build_plan_dataframe(
    run: OptimizationRun,
    config: OptimizationConfig,
) -> pd.DataFrame:
    if run.best is None:
        return pd.DataFrame()

    rows = []
    for item in run.best.plan:
        pair = " + ".join(
            sorted((item.auditor_responsable, item.auditor_acompanante))
        )
        rows.append(
            {
                "Día": item.dia,
                "Inicio": config.slot_a_hora(item.inicio_slot),
                "Fin": config.slot_a_hora(item.fin_slot),
                "Obra ID": item.obra_id,
                "Contrato": item.contrato,
                "Obra": item.descripcion,
                "Responsable": item.auditor_responsable,
                "Acompañante": item.auditor_acompanante,
                "Pareja": pair,
                "Supervisor": item.supervisor_seleccionado or "Sin dato",
                "Contratista": item.contratista_id or "Sin dato",
                "Prioridad": item.prioridad,
            }
        )
    return pd.DataFrame(rows).sort_values(["Día", "Inicio", "Pareja"])


def build_gantt_dataframe(
    run: OptimizationRun,
    config: OptimizationConfig,
) -> pd.DataFrame:
    if run.best is None:
        return pd.DataFrame()

    rows = []
    base_date = datetime(2026, 1, 1)
    for item in run.best.plan:
        start_h, start_m = map(int, config.slot_a_hora(item.inicio_slot).split(":"))
        end_h, end_m = map(int, config.slot_a_hora(item.fin_slot).split(":"))
        day_offset = item.dia - 1
        start = base_date.replace(hour=start_h, minute=start_m) + pd.Timedelta(days=day_offset)
        end = base_date.replace(hour=end_h, minute=end_m) + pd.Timedelta(days=day_offset)
        pair = " + ".join(
            sorted((item.auditor_responsable, item.auditor_acompanante))
        )
        rows.append(
            {
                "Pareja": pair,
                "Inicio": start,
                "Fin": end,
                "Obra": f"{item.obra_id} · {item.contrato}",
                "Día": f"Día {item.dia}",
                "Responsable": item.auditor_responsable,
            }
        )
    return pd.DataFrame(rows)


def build_map_dataframe(
    context: OptimizationContext,
    run: OptimizationRun | None,
) -> pd.DataFrame:
    assigned_day = {}
    if run is not None and run.best is not None:
        assigned_day = {item.obra_id: item.dia for item in run.best.plan}

    rows = []
    for obra in context.obras:
        if obra.latitud is None or obra.longitud is None:
            continue
        rows.append(
            {
                "lat": obra.latitud,
                "lon": obra.longitud,
                "obra_id": obra.obra_id,
                "contrato": obra.contrato,
                "auditor": obra.auditor_responsable,
                "dia": assigned_day.get(obra.obra_id),
                "descripcion": obra.descripcion,
            }
        )
    return pd.DataFrame(rows)
