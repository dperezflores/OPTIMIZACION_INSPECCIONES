from __future__ import annotations

import streamlit as st

from services.optimization_service import OptimizationContext
from src.optimizer import OptimizationRun


def render_header() -> None:
    st.title("Optimización de inspecciones")
    st.caption("Modelo V0 · Programación multi-recurso con OR-Tools / CP-SAT")


def render_kpis(context: OptimizationContext, run: OptimizationRun | None) -> None:
    best_days = "—"
    lower_bound = "—"
    if run is not None:
        lower_bound = str(run.theoretical_lower_bound)
        if run.best is not None:
            best_days = str(run.best.dias)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Inspecciones", context.obras_count)
    c2.metric("Auditores disponibles", context.auditores_disponibles)
    c3.metric("Horas de inspección", f"{context.total_inspection_hours:.1f} h")
    c4.metric("Mínimo factible V0", best_days, help=f"Cota inferior teórica: {lower_bound} día(s)")


def render_v0_notice() -> None:
    st.markdown(
        """
        <div class="model-note">
        <strong>Alcance V0:</strong> la programación considera duración de inspección,
        parejas de auditores, supervisores y contratistas. Aún no incorpora tiempos
        ni distancias de traslado; esos elementos se agregarán en la siguiente etapa.
        </div>
        """,
        unsafe_allow_html=True,
    )
