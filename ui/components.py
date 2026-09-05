from __future__ import annotations

import streamlit as st

from services.optimization_service import OptimizationContext
from src.models import TIPO_FISICA, TIPO_PROYECTO
from src.optimizer import OptimizationRun


def render_header() -> None:
    st.title("Optimización de inspecciones")
    st.caption("Modelo V1 · Programación multi-recurso con traslados aproximados")


def render_kpis(context: OptimizationContext, run: OptimizationRun | None) -> None:
    best_days = "—"
    lower_bound = "—"
    travel_km = "—"
    travel_h = "—"
    if run is not None:
        lower_bound = str(run.theoretical_lower_bound)
        if run.best is not None:
            best_days = str(run.best.dias)
            travel_km = f"{run.best.auditor_travel_km:.1f}"
            travel_h = f"{run.best.auditor_travel_min/60:.1f} h"

    proyectos = sum(
        getattr(o, "tipo_revision", TIPO_FISICA) == TIPO_PROYECTO
        for o in context.obras
    )
    fisicas = context.obras_count - proyectos

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Actividades", context.obras_count)
    c2.metric("Proyectos documentales", proyectos)
    c3.metric("Inspecciones físicas", fisicas)
    c4.metric("Auditores", context.auditores_disponibles)

    c5, c6, c7 = st.columns(3)
    c5.metric("Mínimo factible V1", best_days, help=f"Cota inferior teórica: {lower_bound} día(s)")
    c6.metric("Km-auditor aprox.", travel_km, help="Suma de desplazamientos personales de auditores; aún no equivale a km-vehículo.")
    c7.metric("Horas traslado auditores", travel_h)


def render_v0_notice() -> None:
    st.markdown(
        """
        <div class="model-note">
        <strong>Alcance V1:</strong> los proyectos documentales requieren sólo al auditor responsable;
        las inspecciones físicas requieren responsable + acompañante. Los traslados ya forman parte de
        las restricciones de auditores, supervisores y contratistas. Por ahora se estiman con distancia
        Haversine ajustada y velocidad media; todavía no son tiempos reales de Google Routes.
        </div>
        """,
        unsafe_allow_html=True,
    )
