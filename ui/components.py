from __future__ import annotations

import streamlit as st

from services.optimization_service import OptimizationContext
from src.models import TIPO_FISICA, TIPO_PROYECTO
from src.optimizer import OptimizationRun


def render_header() -> None:
    st.title("Optimización de inspecciones")
    st.caption("Modelo V3 · Calidad operativa con Google Routes + OR-Tools / CP-SAT")


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
    quality_days = "—"
    travel_km = "—"
    travel_h = "—"
    if run is not None:
        if run.best is not None:
            best_days = str(run.best.dias)
            travel_km = f"{run.best.auditor_travel_km:.1f}"
            travel_h = f"{run.best.auditor_travel_min/60:.1f} h"
        if run.quality_best is not None:
            quality_days = str(run.quality_best.dias)

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
    c5.metric("Mínimo factible", best_days, help=f"Cota inferior teórica: {run.theoretical_lower_bound if run else '—'} día(s)")
    c6.metric("Mejor calidad evaluada", quality_days, help="Escenario con menor costo operativo entre los días evaluados; no sustituye al mínimo factible.")
    c7.metric("Km-auditor del mínimo", travel_km)
    c8.metric("Traslado auditores del mínimo", travel_h)

    st.caption(f"Fuente de rutas: {_travel_source_label(run)}")


def render_v0_notice() -> None:
    st.markdown(
        """
        <div class="model-note">
        <strong>Alcance V3:</strong> Google Routes aporta tiempos y distancias por red vial y CP-SAT ya no busca
        únicamente una agenda factible. Dentro de cada escenario también favorece menor dispersión geográfica,
        mejor balance entre días y mejor reparto de carga. Después se calculan métricas reales de traslado,
        espera, desequilibrio y cambios de acompañante para comparar la calidad operativa de 3, 4, 5... días.
        </div>
        """,
        unsafe_allow_html=True,
    )
