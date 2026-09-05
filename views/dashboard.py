from __future__ import annotations

import streamlit as st

from services.optimization_service import OptimizationContext
from services.presentation_service import build_scenarios_dataframe
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
    else:
        certification = "mínimo certificado" if run.minimum_certified else "primera solución factible encontrada"
        st.success(f"Mínimo factible: {run.best.dias} día(s) · {certification}.")

    if run.quality_best is not None and run.best is not None:
        if run.quality_best.dias == run.best.dias:
            st.info("El escenario mínimo también obtuvo la mejor calidad operativa entre los escenarios evaluados.")
        else:
            st.info(
                f"Mejor calidad operativa evaluada: {run.quality_best.dias} día(s). "
                f"El mínimo sigue siendo {run.best.dias} día(s); son criterios distintos."
            )

    scenarios = build_scenarios_dataframe(run)
    st.markdown("#### Comparación de escenarios")
    st.dataframe(scenarios, use_container_width=True, hide_index=True)
    st.caption(
        "El costo operativo es un índice interno: menor es mejor. Combina tiempo real de traslado, "
        "espera, balance entre días/auditores y cambios de acompañante. No representa pesos ni dinero."
    )

    if run.best is not None:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Espera del mínimo", f"{run.best.waiting_auditor_min/60:.1f} h-auditor")
        c2.metric("Desbalance entre días", f"{run.best.day_imbalance_min/60:.1f} h-auditor")
        c3.metric("Desbalance entre auditores", f"{run.best.auditor_imbalance_min/60:.1f} h")
        c4.metric("Cambios de acompañante", run.best.companion_changes)

    st.markdown("#### Fuente de traslados")
    st.write(
        f"**{_source_text(run)}** · Ubicaciones únicas: **{run.unique_locations or context.unique_location_count}**."
    )
    if run.billed_elements:
        st.info(
            f"Esta ejecución generó una matriz nueva con {run.billed_elements:,} elementos origen-destino. "
            "Las siguientes optimizaciones reutilizarán la caché mientras no cambien las coordenadas."
        )

    st.markdown("#### Qué optimiza V3")
    st.write(
        "CP-SAT mantiene como restricciones duras la jornada, responsables, acompañantes, supervisores, "
        "contratistas y traslados. La función objetivo favorece prioridades, agrupación geográfica, "
        "balance entre jornadas y reparto de carga. Las métricas finales se calculan sobre la secuencia realmente obtenida."
    )
    st.warning(
        "V3 todavía no es ALNS. Esta versión fija y valida la función de calidad que ALNS usará en la siguiente iteración "
        "para destruir y reparar partes de la programación sin cambiar el criterio de evaluación."
    )
