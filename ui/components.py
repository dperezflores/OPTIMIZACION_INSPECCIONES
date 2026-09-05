from __future__ import annotations

import streamlit as st

from services.optimization_service import OptimizationContext
from src.models import TIPO_FISICA, TIPO_PROYECTO
from src.optimizer import OptimizationRun


def render_header() -> None:
    st.title("Optimización de inspecciones")
    st.caption("Modelo V2 · Programación multi-recurso con Google Routes + OR-Tools / CP-SAT")


def _travel_source_label(run: OptimizationRun | None) -> str:
    if run is None:
        return "—"
    if run.travel_source == "google_routes":
        return "Google Routes (nueva)"
    if run.travel_source == "google_cache":
        return "Google Routes (caché)"
    return "Haversine V1"


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
    c4.metric("Ubicaciones únicas", context.unique_location_count)

    c5, c6, c7, c8 = st.columns(4)
    c5.metric("Mínimo factible V2", best_days, help=f"Cota inferior teórica: {lower_bound} día(s)")
    c6.metric("Km-auditor", travel_km, help="Suma de desplazamientos personales de auditores; no equivale aún a km-vehículo.")
    c7.metric("Horas traslado auditores", travel_h)
    c8.metric("Fuente de rutas", _travel_source_label(run))


def render_v0_notice() -> None:
    st.markdown(
        """
        <div class="model-note">
        <strong>Alcance V2:</strong> Google Routes puede proporcionar distancia y duración reales por red vial.
        La matriz se calcula sólo para ubicaciones únicas, se guarda en caché y luego CP-SAT la usa como
        restricción de traslado para auditores, supervisores y contratistas. El modo Haversine V1 permanece
        disponible únicamente como respaldo técnico.
        </div>
        """,
        unsafe_allow_html=True,
    )
