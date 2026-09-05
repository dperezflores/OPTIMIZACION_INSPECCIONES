from __future__ import annotations

import streamlit as st

from services.optimization_service import OptimizationContext
from services.presentation_service import build_scenarios_dataframe
from src.optimizer import OptimizationRun


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
        certification = (
            "mínimo certificado"
            if run.minimum_certified
            else "primera solución factible encontrada"
        )
        st.success(
            f"La V0.1 encontró una solución de {run.best.dias} día(s): {certification}."
        )

    scenarios = build_scenarios_dataframe(run)
    st.markdown("#### Escenarios evaluados")
    st.dataframe(scenarios, use_container_width=True, hide_index=True)

    st.markdown("#### Supuestos vigentes")
    st.write(
        f"Jornada: **{context.config.hora_inicio}–{context.config.hora_fin}** · "
        f"Intervalo: **{context.config.slot_minutos} min** · "
        "Proyecto documental: **1 auditor** · Inspección física: **2 auditores** · "
        "Acompañante dinámico por inspección · Traslados todavía no incluidos."
    )
