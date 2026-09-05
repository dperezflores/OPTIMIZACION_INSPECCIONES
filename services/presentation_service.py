from __future__ import annotations

from datetime import datetime
import pandas as pd

from src.config import OptimizationConfig
from src.depot import DEPOT_ID, DEPOT_NAME
from src.models import ScenarioResult, TIPO_FISICA, TIPO_PROYECTO
from src.optimizer import OptimizationRun
from .optimization_service import OptimizationContext


def build_scenarios_dataframe(run: OptimizationRun) -> pd.DataFrame:
    rows = []
    for result in run.scenarios:
        rows.append({
            "Días": result.dias,
            "Estado": "Factible" if result.factible else "No factible" if result.probado_infactible else result.status,
            "Tiempo solver (s)": round(result.wall_time_seconds, 2),
            "Km-auditor": round(result.auditor_travel_km, 1) if result.factible else None,
            "Horas traslado auditor": round(result.auditor_travel_min / 60, 1) if result.factible else None,
            "Tiempo adicional ASEG (h-auditor)": round(result.additional_travel_time_min / 60, 1) if result.factible else None,
            "Km-vehículo": round(result.vehicle_km, 1) if result.factible else None,
            "Viajes vehículo": result.vehicle_trips if result.factible else None,
            "Viajes solo": result.solo_vehicle_legs if result.factible else None,
            "Viajes compartidos": result.shared_vehicle_legs if result.factible else None,
            "Vehículos simultáneos máx.": result.vehicles_required_peak if result.factible else None,
            "Espera auditor (h)": round(result.waiting_auditor_min / 60, 1) if result.factible else None,
            "Desbalance día (h-auditor)": round(result.day_imbalance_min / 60, 1) if result.factible else None,
            "Desbalance auditor (h)": round(result.auditor_imbalance_min / 60, 1) if result.factible else None,
            "Cambios acompañante": result.companion_changes if result.factible else None,
            "Costo operativo": round(result.operational_cost, 1) if result.factible else None,
            "Km supervisores": round(result.supervisor_travel_km, 1) if result.factible else None,
            "Km contratistas": round(result.contractor_travel_km, 1) if result.factible else None,
        })
    return pd.DataFrame(rows)


def select_solution(run: OptimizationRun, mode: str = "minimum") -> ScenarioResult | None:
    if mode == "refined" and run.refined_best is not None:
        return run.refined_best
    if mode == "quality" and run.quality_best is not None:
        return run.quality_best
    return run.best


def _tipo_revision(obj) -> str:
    return getattr(obj, "tipo_revision", TIPO_FISICA)


def _equipo(item) -> str:
    if item.auditor_acompanante:
        return " + ".join(sorted((item.auditor_responsable, item.auditor_acompanante)))
    return item.auditor_responsable


def build_plan_dataframe(run: OptimizationRun, config: OptimizationConfig, mode: str = "minimum") -> pd.DataFrame:
    selected = select_solution(run, mode)
    if selected is None:
        return pd.DataFrame()
    rows = []
    for item in selected.plan:
        rows.append({
            "Día": item.dia,
            "Inicio": config.slot_a_hora(item.inicio_slot),
            "Fin": config.slot_a_hora(item.fin_slot),
            "Tipo": "Proyecto documental" if _tipo_revision(item) == TIPO_PROYECTO else "Inspección física",
            "Obra ID": item.obra_id,
            "Contrato": item.contrato,
            "Obra": item.descripcion,
            "Responsable": item.auditor_responsable,
            "Acompañante": item.auditor_acompanante or "No requerido",
            "Equipo": _equipo(item),
            "Supervisor": item.supervisor_seleccionado or "Sin dato",
            "Contratista": item.contratista_id or "Sin dato",
            "Prioridad": item.prioridad,
        })
    return pd.DataFrame(rows).sort_values(["Día", "Inicio", "Equipo"])


def _place_label(value: str) -> str:
    return DEPOT_NAME if value == DEPOT_ID else value


def build_vehicle_dataframe(run: OptimizationRun, config: OptimizationConfig, mode: str = "minimum") -> pd.DataFrame:
    selected = select_solution(run, mode)
    if selected is None or not selected.vehicle_plan:
        return pd.DataFrame()
    rows = []
    for leg in selected.vehicle_plan:
        rows.append({
            "Día": leg.dia,
            "Salida": config.slot_a_hora(leg.salida_slot),
            "Llegada aprox.": config.slot_a_hora(leg.llegada_slot),
            "Viaje": leg.vehicle_id,
            "Origen": _place_label(leg.origen_id),
            "Destino": _place_label(leg.destino_id),
            "Pasajeros": ", ".join(leg.pasajeros),
            "Ocupación": leg.ocupacion,
            "Km-vehículo": round(leg.distancia_km, 1),
            "Tiempo (min)": round(leg.tiempo_min, 1),
            "Tipo": "Compartido" if leg.ocupacion > 1 else "Individual",
            "Motivo": leg.motivo,
        })
    return pd.DataFrame(rows).sort_values(["Día", "Salida", "Viaje"])


def build_gantt_dataframe(run: OptimizationRun, config: OptimizationConfig, mode: str = "minimum") -> pd.DataFrame:
    selected = select_solution(run, mode)
    if selected is None:
        return pd.DataFrame()
    rows = []
    base_date = datetime(2026, 1, 1)
    for item in selected.plan:
        start_h, start_m = map(int, config.slot_a_hora(item.inicio_slot).split(":"))
        end_h, end_m = map(int, config.slot_a_hora(item.fin_slot).split(":"))
        day_offset = item.dia - 1
        rows.append({
            "Equipo": _equipo(item),
            "Inicio": base_date.replace(hour=start_h, minute=start_m) + pd.Timedelta(days=day_offset),
            "Fin": base_date.replace(hour=end_h, minute=end_m) + pd.Timedelta(days=day_offset),
            "Obra": f"{item.obra_id} · {item.contrato}",
            "Día": f"Día {item.dia}",
            "Responsable": item.auditor_responsable,
            "Tipo": "Proyecto documental" if _tipo_revision(item) == TIPO_PROYECTO else "Inspección física",
        })
    return pd.DataFrame(rows)


def build_map_dataframe(context: OptimizationContext, run: OptimizationRun | None, mode: str = "minimum") -> pd.DataFrame:
    assigned_day = {}
    if run is not None:
        selected = select_solution(run, mode)
        if selected is not None:
            assigned_day = {item.obra_id: item.dia for item in selected.plan}
    rows = []
    for obra in context.obras:
        if obra.latitud is None or obra.longitud is None:
            continue
        rows.append({
            "lat": obra.latitud, "lon": obra.longitud, "obra_id": obra.obra_id,
            "contrato": obra.contrato, "auditor": obra.auditor_responsable,
            "dia": assigned_day.get(obra.obra_id),
            "tipo": "Proyecto documental" if _tipo_revision(obra) == TIPO_PROYECTO else "Inspección física",
            "descripcion": obra.descripcion,
        })
    return pd.DataFrame(rows)
