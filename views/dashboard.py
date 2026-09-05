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
        st.info("Ejecuta la optimización desde el panel lateral para generar la planeación.")
        return

    if run.best is None:
        st.error("No se encontró una solución factible en el rango evaluado.")
    else:
        certification = "mínimo certificado" if run.minimum_certified else "primera solución factible encontrada"
        st.success(f"La V2 encontró una solución de {run.best.dias} día(s): {certification}.")

    scenarios = build_scenarios_dataframe(run)
    st.markdown("#### Escenarios evaluados")
    st.dataframe(scenarios, use_container_width=True, hide_index=True)

    st.markdown("#### Fuente de traslados")
    st.write(
        f"**{_source_text(run)}** · Ubicaciones únicas: **{run.unique_locations or context.unique_location_count}**."
    )
    if run.billed_elements:
        st.info(
            f"Esta ejecución generó una matriz nueva con {run.billed_elements:,} elementos origen-destino. "
            "Las siguientes optimizaciones reutilizarán la caché mientras no cambien las coordenadas ni se fuerce una actualización."
        )

    st.markdown("#### Supuestos vigentes")
    st.write(
        f"Jornada: **{context.config.hora_inicio}–{context.config.hora_fin}** · "
        f"Intervalo: **{context.config.slot_minutos} min** · "
        "Proyecto documental: **1 auditor** · Inspección física: **2 auditores** · "
        "Acompañante dinámico por inspección."
    )
    if run.travel_source.startswith("google"):
        st.write(
            "Google Routes V2 utiliza **DRIVE** y **TRAFFIC_UNAWARE**: distancia y duración por red vial, "
            "sin depender todavía de una fecha/hora concreta ni de condiciones de tráfico en tiempo real."
        )
    else:
        st.warning(
            "Esta corrida usó el respaldo V1: Haversine ajustado y velocidad media. "
            "No debe interpretarse como tiempo real de carretera."
        )
