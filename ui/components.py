from __future__ import annotations

import streamlit as st

from services.optimization_service import OptimizationContext
from src.models import TIPO_PROYECTO
from src.optimizer import OptimizationRun


def render_header() -> None:
    st.title("Optimización de inspecciones")
    st.caption("Modelo V0.1 · Programación multi-recurso con OR-Tools / CP-SAT")


def render_kpis(context: OptimizationContext, run: OptimizationRun | None) -> None:
    best_days = "—"
    lower_bound = "—"
    if run is not None:
        lower_bound = str(run.theoretical_lower_bound)
        if run.best is not None:
            best_days = str(run.best.dias)

    proyectos = sum(o.tipo_revision == TIPO_PROYECTO for o in context.obras)
    fisicas = context.obras_count - proyectos

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Actividades", context.obras_count)
    c2.metric("Proyectos documentales", proyectos)
    c3.metric("Inspecciones físicas", fisicas)
    c4.metric("Auditores disponibles", context.auditores_disponibles)
    c5.metric("Mínimo factible V0.1", best_days, help=f"Cota inferior teórica: {lower_bound} día(s)")


def render_v0_notice() -> None:
    st.markdown(
        """
        <div class="model-note">
        <strong>Alcance V0.1:</strong> los proyectos documentales requieren sólo al auditor responsable;
        las inspecciones físicas requieren responsable + acompañante. El acompañante se decide por
        inspección. Aún no se incorporan tiempos ni distancias de traslado.
        </div>
        """,
        unsafe_allow_html=True,
    )
