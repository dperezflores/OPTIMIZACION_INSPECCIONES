from __future__ import annotations

import streamlit as st

from services.optimization_service import OptimizationContext
from src.depot import DEPOT_LATITUDE, DEPOT_LONGITUDE
from src.models import TIPO_FISICA, TIPO_PROYECTO
from src.optimizer import OptimizationRun


def render_header() -> None:
    st.title("Optimización de inspecciones")
    st.caption("Modelo V5 · Depósito ASEG + Google Routes + OR-Tools / CP-SAT + ALNS + logística vehicular")


def _travel_source_label(run: OptimizationRun | None) -> str:
    if run is None:
        return "—"
    if run.travel_source == "google_routes":
        return "Google Routes (nueva)"
    if run.travel_source == "google_cache":
        return "Google Routes (caché)"
    return "Haversine V1"


def render_kpis(context: OptimizationContext, run: OptimizationRun | None) -> None:
    best_days = quality_days = travel_km = travel_h = "—"
    vehicle_km = vehicle_peak = "—"
    if run is not None:
        if run.best is not None:
            best_days = str(run.best.dias)
            travel_km = f"{run.best.auditor_travel_km:.1f}"
            travel_h = f"{run.best.auditor_travel_min/60:.1f} h"
        if run.quality_best is not None:
            quality_days = str(run.quality_best.dias)
        selected = run.refined_best or run.quality_best or run.best
        if selected is not None:
            vehicle_km = f"{selected.vehicle_km:.1f}"
            vehicle_peak = str(selected.vehicles_required_peak)

    proyectos = sum(getattr(o, "tipo_revision", TIPO_FISICA) == TIPO_PROYECTO for o in context.obras)
    fisicas = context.obras_count - proyectos

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Actividades", context.obras_count)
    c2.metric("Proyectos documentales", proyectos)
    c3.metric("Inspecciones físicas", fisicas)
    c4.metric("Nodos de ruta", context.unique_location_count, help="Incluye las ubicaciones de trabajo y el depósito ASEG.")

    c5, c6, c7, c8 = st.columns(4)
    c5.metric("Mínimo factible", best_days, help=f"Cota inferior teórica: {run.theoretical_lower_bound if run else '—'} día(s)")
    c6.metric("Mejor calidad CP-SAT", quality_days)
    c7.metric("Km-vehículo solución final", vehicle_km)
    c8.metric("Vehículos simultáneos máx.", vehicle_peak, help="Máximo estimado de viajes vehiculares concurrentes en la solución final.")

    st.caption(
        f"Fuente de rutas: {_travel_source_label(run)} · Depósito ASEG: {DEPOT_LATITUDE:.6f}, {DEPOT_LONGITUDE:.6f} · "
        f"Km-auditor mínimo: {travel_km} · Traslado auditores mínimo: {travel_h}"
    )


def render_v0_notice() -> None:
    st.markdown(
        """
        <div class="model-note">
        <strong>Alcance V5:</strong> todos los auditores parten de las instalaciones de ASEG y regresan a ASEG al terminar.
        La ventana 08:00–17:00 corresponde a las actividades de revisión; si el viaje exige salir antes o regresar después,
        ese tiempo se contabiliza y se penaliza para que sólo se utilice cuando sea necesario. Los vehículos tienen capacidad
        de 4 personas; el modelo favorece viajes compartidos y permite viajes individuales cuando aportan flexibilidad.
        En inspecciones físicas, responsable y acompañante se modelan como un viaje compartido hacia el sitio.
        </div>
        """,
        unsafe_allow_html=True,
    )
