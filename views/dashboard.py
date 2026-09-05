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
        "Tiempo adicional ASEG es el traslado que ocurre antes de las 08:00 o después de las 17:00. "
        "Se permite, pero recibe una penalización para evitarlo cuando existe otra organización razonable."
    )

    # Tomamos una instantánea local de los tres campos. El if compuesto ya era
    # seguro por cortocircuito, pero esta forma evita accesos repetidos y deja una
    # salida explícita si una ejecución parcial deja ALNS incompleto.
    alns_result = run.alns_result
    quality_best = run.quality_best
    refined = run.refined_best

    if alns_result is not None and quality_best is not None and refined is not None:
        initial = alns_result.initial
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
                "Tiempo adicional ASEG (h-auditor)": round(initial.additional_travel_time_min / 60, 1),
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
                "Tiempo adicional ASEG (h-auditor)": round(refined.additional_travel_time_min / 60, 1),
                "Espera (h-auditor)": round(refined.waiting_auditor_min / 60, 1),
                "Desbalance día (h)": round(refined.day_imbalance_min / 60, 1),
                "Cambios acompañante": refined.companion_changes,
                "Costo operativo": round(refined.operational_cost, 1),
            },
        ])
        st.dataframe(compare, use_container_width=True, hide_index=True)

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Mejora del índice", f"{improvement:.1f}%")
        c2.metric("Iteraciones ALNS", alns_result.iterations)
        c3.metric("Movimientos aceptados", alns_result.accepted_moves)
        c4.metric("Movimientos con mejora", alns_result.improving_moves)

        operator_rows = []
        for op in alns_result.operator_stats:
            operator_rows.append({
                "Operador": op.name, "Peso final": round(op.weight, 2), "Usos": op.uses,
                "Aceptados": op.accepted, "Mejoras": op.improved, "Nuevos mejores": op.best_hits,
            })
        with st.expander("Comportamiento adaptativo de operadores", expanded=False):
            st.dataframe(pd.DataFrame(operator_rows), use_container_width=True, hide_index=True)
    elif alns_result is not None or refined is not None:
        st.warning(
            "La ejecución de ALNS quedó parcial y no tiene todos los objetos necesarios para comparar antes/después. "
            "La solución CP-SAT sigue disponible."
        )
    else:
        st.warning("ALNS no se ejecutó en esta corrida; sólo se muestran resultados CP-SAT.")

    st.markdown("#### Base y movilidad")
    st.write(
        f"Todos los auditores parten de **{DEPOT_NAME}** y regresan a esa misma base. "
        "Las actividades se programan entre 08:00 y 17:00. Si el traslado obliga a salir antes o regresar después, "
        "el sistema lo muestra como tiempo adicional y lo penaliza, en vez de declarar imposible una revisión larga. "
        "La capacidad utilizada es de **4 pasajeros por vehículo** y los viajes individuales siguen permitidos."
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
        "CP-SAT construye las agendas de actividades y ahora incorpora en su objetivo los minutos de traslado "
        "consecutivo de auditores, supervisores y contratistas. La capa logística añade el recorrido "
        "ASEG → actividades → ASEG, agrupa tramos compatibles en vehículos de hasta cuatro personas y calcula "
        "los viajes individuales necesarios. ALNS refina después los componentes que dependen de la solución "
        "completa, como km-vehículo, viajes individuales, espera y tiempo adicional."
    )
