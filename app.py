from __future__ import annotations

import os

import streamlit as st

from services.optimization_service import (
    OptimizationRequest,
    TRAVEL_PROVIDER_GOOGLE,
    TRAVEL_PROVIDER_HAVERSINE,
    google_cache_status,
    load_context,
    run_optimization,
)
from ui.components import render_header, render_kpis, render_v0_notice
from ui.styles import apply_styles
from views.dashboard import render_dashboard
from views.gantt import render_gantt
from views.mapa import render_mapa
from views.planificacion import render_planificacion


APP_SCHEMA_VERSION = "4.0.0"


def _google_api_key() -> str:
    value = os.getenv("GOOGLE_MAPS_API_KEY", "").strip()
    if value:
        return value
    try:
        return str(st.secrets.get("GOOGLE_MAPS_API_KEY", "")).strip()
    except Exception:
        return ""


st.set_page_config(page_title="Optimización de inspecciones", page_icon="📍", layout="wide", initial_sidebar_state="expanded")
apply_styles()
context = load_context()
google_key = _google_api_key()
cache = google_cache_status(context)

if st.session_state.get("app_schema_version") != APP_SCHEMA_VERSION:
    st.session_state.app_schema_version = APP_SCHEMA_VERSION
    st.session_state.optimization_run = None
elif "optimization_run" not in st.session_state:
    st.session_state.optimization_run = None

render_header()
render_v0_notice()

with st.sidebar:
    st.header("Parámetros de optimización")
    min_days = st.number_input("Mínimo de días", min_value=1, max_value=15, value=int(context.config.dias_min), step=1)
    max_days = st.number_input("Máximo de días", min_value=int(min_days), max_value=20, value=max(int(min_days), int(context.config.dias_max)), step=1)
    time_limit = st.number_input("Tiempo máximo por escenario (s)", min_value=1.0, max_value=300.0, value=float(context.config.time_limit_seconds), step=5.0)
    compare_all = st.checkbox(
        "Comparar todos los escenarios del rango",
        value=True,
        help="Resuelve cada cantidad de días para comparar calidad operativa.",
    )

    st.markdown("#### Refinamiento ALNS")
    use_alns = st.checkbox(
        "Refinar la mejor solución con ALNS",
        value=True,
        help="ALNS libera parcialmente la agenda y CP-SAT repara cada vecindario manteniendo todas las restricciones duras.",
    )
    if use_alns:
        alns_iterations = st.number_input("Iteraciones ALNS", min_value=1, max_value=100, value=20, step=5)
        alns_repair_time = st.number_input("Tiempo CP-SAT por reparación (s)", min_value=0.5, max_value=20.0, value=3.0, step=0.5)
        alns_destroy = st.slider("Porción de agenda liberada", min_value=0.05, max_value=0.50, value=0.20, step=0.05)
    else:
        alns_iterations, alns_repair_time, alns_destroy = 1, 1.0, 0.20

    st.markdown("#### Fuente de traslados")
    provider_label = st.radio(
        "Matriz de tiempos y distancias",
        options=["Google Routes V2", "Haversine V1 (respaldo)"],
        index=0,
    )
    travel_provider = TRAVEL_PROVIDER_GOOGLE if provider_label.startswith("Google") else TRAVEL_PROVIDER_HAVERSINE

    if travel_provider == TRAVEL_PROVIDER_GOOGLE:
        if cache is not None:
            st.success(f"Matriz Google disponible en caché para {cache.unique_locations} ubicaciones únicas.")
        elif google_key:
            st.info(f"La primera optimización consultará Routes API para {context.unique_location_count} ubicaciones únicas y guardará caché.")
        else:
            st.error("No se encontró GOOGLE_MAPS_API_KEY en Streamlit Secrets ni en variables de entorno.")
        force_refresh = st.checkbox(
            "Forzar actualización de matriz Google",
            value=False,
            help="Actívalo sólo si realmente deseas volver a consultar Google.",
        )
    else:
        force_refresh = False
        st.warning("Modo aproximado V1: no usa Google ni genera consumo de Routes API.")

    optimize = st.button("Optimizar y refinar", type="primary", use_container_width=True)
    st.divider()
    st.caption(
        f"Jornada: {context.config.hora_inicio}–{context.config.hora_fin}\n\n"
        f"Intervalo CP-SAT: {context.config.slot_minutos} min\n\n"
        f"Ubicaciones únicas: {context.unique_location_count}\n\n"
        "Motor V4: Google Routes + CP-SAT + ALNS"
    )

if optimize:
    if travel_provider == TRAVEL_PROVIDER_GOOGLE and not google_key:
        st.error("No es posible usar Google Routes hasta configurar GOOGLE_MAPS_API_KEY.")
    else:
        request = OptimizationRequest(
            min_days=int(min_days),
            max_days=int(max_days),
            time_limit_seconds=float(time_limit),
            travel_provider=travel_provider,
            google_api_key=google_key if travel_provider == TRAVEL_PROVIDER_GOOGLE else None,
            force_refresh_routes=bool(force_refresh),
            compare_all_scenarios=bool(compare_all),
            use_alns=bool(use_alns),
            alns_iterations=int(alns_iterations),
            alns_repair_time_seconds=float(alns_repair_time),
            alns_destroy_fraction=float(alns_destroy),
        )
        try:
            with st.spinner("Resolviendo escenarios CP-SAT y refinando la mejor solución con ALNS..."):
                st.session_state.optimization_run = run_optimization(context, request)
            st.rerun()
        except Exception as exc:
            st.error(f"No fue posible ejecutar el modelo: {exc}")

run = st.session_state.optimization_run
render_kpis(context, run)

tab_resumen, tab_plan, tab_gantt, tab_mapa = st.tabs(["Resumen", "Planeación", "Cronograma", "Mapa"])
with tab_resumen:
    render_dashboard(context, run)
with tab_plan:
    render_planificacion(run, context.config)
with tab_gantt:
    render_gantt(run, context.config)
with tab_mapa:
    render_mapa(context, run)
