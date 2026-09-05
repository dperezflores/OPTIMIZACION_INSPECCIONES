from __future__ import annotations

import csv
import json
from pathlib import Path

from .config import OptimizationConfig
from .optimizer import OptimizationRun


def print_run_summary(
    run: OptimizationRun,
    config: OptimizationConfig,
    obras_count: int,
    auditores_count: int,
    total_inspection_hours: float,
) -> None:
    print("=" * 72)
    print("OPTIMIZACIÓN DE INSPECCIONES - MODELO V0.1")
    print("=" * 72)
    print(f"Obras/actividades:      {obras_count}")
    print(f"Auditores disponibles: {auditores_count}")
    print(f"Horas de revisión:     {total_inspection_hours:.1f} h")
    print(f"Jornada modelada:      {config.hora_inicio} - {config.hora_fin}")
    print(f"Cota inferior teórica: {run.theoretical_lower_bound} día(s)")
    print()
    print("Escenarios:")

    for result in run.scenarios:
        if result.factible:
            label = "FACTIBLE"
        elif result.status == "INFEASIBLE":
            label = "NO FACTIBLE (PROBADO)"
        else:
            label = f"NO DETERMINADO ({result.status})"
        print(f"  {result.dias} día(s): {label} [{result.wall_time_seconds:.2f} s]")

    print()
    if run.best is None:
        print("No se encontró una solución factible en el rango evaluado.")
    else:
        cert = "mínimo certificado" if run.minimum_certified else "mínimo no certificado: hubo escenarios previos sin concluir"
        print(f"Primera solución factible: {run.best.dias} día(s) ({cert}).")
    print("=" * 72)


def save_run(run: OptimizationRun, config: OptimizationConfig, output_dir: str | Path) -> None:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    summary = {
        "theoretical_lower_bound": run.theoretical_lower_bound,
        "minimum_certified": run.minimum_certified,
        "best_days": run.best.dias if run.best else None,
        "scenarios": [
            {
                "days": r.dias,
                "status": r.status,
                "feasible": r.factible,
                "wall_time_seconds": round(r.wall_time_seconds, 4),
                "objective_value": r.objective_value,
            }
            for r in run.scenarios
        ],
        "assumptions": {
            "start_time": config.hora_inicio,
            "end_time": config.hora_fin,
            "slot_minutes": config.slot_minutos,
            "dynamic_companions_per_physical_inspection": True,
            "documentary_projects_require_one_auditor": True,
            "travel_times_included": False,
        },
    }
    (output_dir / "resumen.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    if run.best is None:
        return

    plan_path = output_dir / f"plan_{run.best.dias}_dias.csv"
    with plan_path.open("w", encoding="utf-8-sig", newline="") as fh:
        fieldnames = [
            "dia", "inicio", "fin", "tipo_revision", "obra_id", "contrato",
            "auditor_responsable", "auditor_acompanante", "equipo",
            "supervisor_seleccionado", "contratista_id", "prioridad", "obra",
        ]
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for item in run.best.plan:
            equipo = item.auditor_responsable
            if item.auditor_acompanante:
                equipo = " + ".join(sorted((item.auditor_responsable, item.auditor_acompanante)))
            writer.writerow({
                "dia": item.dia,
                "inicio": config.slot_a_hora(item.inicio_slot),
                "fin": config.slot_a_hora(item.fin_slot),
                "tipo_revision": item.tipo_revision,
                "obra_id": item.obra_id,
                "contrato": item.contrato,
                "auditor_responsable": item.auditor_responsable,
                "auditor_acompanante": item.auditor_acompanante or "",
                "equipo": equipo,
                "supervisor_seleccionado": item.supervisor_seleccionado or "",
                "contratista_id": item.contratista_id or "",
                "prioridad": item.prioridad,
                "obra": item.descripcion,
            })
