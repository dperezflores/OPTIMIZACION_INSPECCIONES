from __future__ import annotations

import pandas as pd
import streamlit as st

from services.optimization_service import OptimizationContext
from services.presentation_service import build_scenarios_dataframe
from src.depot import DEPOT_NAME
from src.optimizer import OptimizationRun


def _source_text(run: OptimizationRun) -> str:
    if run.travel_source == "google_routes":
        return "Google Routes (matriz recién consultada)"
    if run.travel_source == "google_cache":
        return "Google Routes (matriz reutilizada desde caché)"
    return "Haversine V1 (respaldo aproximado)"


def render_dashboard(context: OptimizationContext, run: OptimizationRun | None) -> None:
    st.subheader("Resumen del modelo")

    if context.warnings:
        with st.expander("Advertencias de datos", expanded=False):
            for warning in context.warnings:
                st.warning(warning)

    if run is None:
        st.info("Ejecuta la optimización desde el panel lateral para generar y comparar escenarios.")
        return
    if run.best is None:
        st.error("No se encontró una solución factible en el rango evaluado.")
        return

    certification = "mínimo certificado" if run.minimum_certified else "primera solución factible encontrada"
    st.success(f"Mínimo factible: {run.best.dias} día(s) · {certification}.")
    if run.quality_best is not None:
        st.info(
            f"Mejor calidad CP-SAT evaluada: {run.quality_best.dias} día(s). "
            f"El mínimo sigue siendo {run.best.dias} día(s); son criterios distintos."
        )

    st.markdown("#### Comparación de escenarios CP-SAT")
    st.dataframe(build_scenarios_dataframe(run), use_container_width=True, hide_index=True)
    st.caption(
        "Km-auditor mide movilidad de personas; km-vehículo cuenta cada recorrido compartido una sola vez. "
        "El costo operativo es un índice interno: menor es mejor."
    )

    if run.alns_result is not None and run.quality_best is not None and run.refined_best is not None:
        initial = run.alns_result.initial
        refined = run.refined_best
        improvement = 0.0
        if initial.operational_cost > 0:
            improvement = 100.0 * (initial.operational_cost - refined.operational_cost) / initial.operational_cost

        st.markdown("#### Refinamiento ALNS: antes vs después")
        compare = pd.DataFrame([
            {
                "Solución": "CP-SAT inicial",
                "Días": initial.dias,
                "Km-auditor": round(initial.auditor_travel_km, 1),
                "Km-vehículo": round(initial.vehicle_km, 1),
                "Viajes solo": initial.solo_vehicle_legs,
                "Viajes compartidos": initial.shared_vehicle_legs,
                "Vehículos simultáneos máx.": initial.vehicles_required_peak,
                "Traslado auditor (h)": round(initial.auditor_travel_min / 60, 1),
                "Espera (h-auditor)": round(initial.waiting_auditor_min / 60, 1),
                "Desbalance día (h)": round(initial.day_imbalance_min / 60, 1),
                "Cambios acompañante": initial.companion_changes,
                "Costo operativo": round(initial.operational_cost, 1),
            },
            {
                "Solución": "ALNS refinada",
                "Días": refined.dias,
                "Km-auditor": round(refined.auditor_travel_km, 1),
                "Km-vehículo": round(refined.vehicle_km, 1),
                "Viajes solo": refined.solo_vehicle_legs,
                "Viajes compartidos": refined.shared_vehicle_legs,
                "Vehículos simultáneos máx.": refined.vehicles_required_peak,
                "Traslado auditor (h)": round(refined.auditor_travel_min / 60, 1),
                "Espera (h-auditor)": round(refined.waiting_auditor_min / 60, 1),
                "Desbalance día (h)": round(refined.day_imbalance_min / 60, 1),
                "Cambios acompañante": refined.companion_changes,
                "Costo operativo": round(refined.operational_cost, 1),
            },
        ])
        st.dataframe(compare, use_container_width=True, hide_index=True)

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Mejora del índice", f"{improvement:.1f}%")
        c2.metric("Iteraciones ALNS", run.alns_result.iterations)
        c3.metric("Movimientos aceptados", run.alns_result.accepted_moves)
        c4.metric("Movimientos con mejora", run.alns_result.improving_moves)

        operator_rows = []
        for op in run.alns_result.operator_stats:
            operator_rows.append({
                "Operador": op.name, "Peso final": round(op.weight, 2), "Usos": op.uses,
                "Aceptados": op.accepted, "Mejoras": op.improved, "Nuevos mejores": op.best_hits,
            })
        with st.expander("Comportamiento adaptativo de operadores", expanded=False):
            st.dataframe(pd.DataFrame(operator_rows), use_container_width=True, hide_index=True)
    else:
        st.warning("ALNS no se ejecutó en esta corrida; sólo se muestran resultados CP-SAT.")

    st.markdown("#### Base y movilidad")
    st.write(
        f"Todos los auditores parten de **{DEPOT_NAME}** y la agenda debe permitir su regreso antes del cierre de jornada. "
        "La capacidad utilizada es de **4 pasajeros por vehículo**. Los viajes individuales están permitidos, pero reciben una penalización suave."
    )

    st.markdown("#### Fuente de traslados")
    st.write(f"**{_source_text(run)}** · Nodos de ruta: **{run.unique_locations or context.unique_location_count}**.")
    if run.billed_elements:
        st.info(
            f"Esta ejecución generó una matriz nueva con {run.billed_elements:,} elementos origen-destino. "
            "Las siguientes optimizaciones reutilizarán la caché mientras no cambien las coordenadas."
        )

    st.markdown("#### Qué hace V5")
    st.write(
        "CP-SAT construye agendas que ya consideran el viaje de salida desde ASEG y el regreso. "
        "Después se agrupan tramos compatibles en vehículos de hasta cuatro personas; ALNS usa también estas métricas "
        "para favorecer menos km-vehículo, menos viajes individuales y una mejor organización general."
    )
