from __future__ import annotations

import streamlit as st

from services.optimization_service import (
    OptimizationRequest,
    load_context,
    run_optimization,
)
from ui.components import render_header, render_kpis, render_v0_notice
from ui.styles import apply_styles
from views.dashboard import render_dashboard
from views.gantt import render_gantt
from views.mapa import render_mapa
from views.planificacion import render_planificacion


st.set_page_config(
    page_title="Optimización de inspecciones",
    page_icon="📍",
    layout="wide",
    initial_sidebar_state="expanded",
)
apply_styles()


@st.cache_resource
def get_context():
    return load_context()


context = get_context()

if "optimization_run" not in st.session_state:
    st.session_state.optimization_run = None

render_header()
render_v0_notice()

with st.sidebar:
    st.header("Parámetros de optimización")
    min_days = st.number_input(
        "Mínimo de días",
        min_value=1,
        max_value=15,
        value=int(context.config.dias_min),
        step=1,
    )
    max_days = st.number_input(
        "Máximo de días",
        min_value=int(min_days),
        max_value=20,
        value=max(int(min_days), int(context.config.dias_max)),
        step=1,
    )
    time_limit = st.number_input(
        "Tiempo máximo por escenario (s)",
        min_value=1.0,
        max_value=300.0,
        value=float(context.config.time_limit_seconds),
        step=5.0,
    )

    optimize = st.button(
        "Optimizar planeación",
        type="primary",
        use_container_width=True,
    )

    st.divider()
    st.caption(
        f"Jornada: {context.config.hora_inicio}–{context.config.hora_fin}\n\n"
        f"Intervalo: {context.config.slot_minutos} min\n\n"
        "Motor: OR-Tools / CP-SAT"
    )

if optimize:
    request = OptimizationRequest(
        min_days=int(min_days),
        max_days=int(max_days),
        time_limit_seconds=float(time_limit),
    )
    try:
        with st.spinner("Calculando la planeación factible..."):
            st.session_state.optimization_run = run_optimization(context, request)
    except Exception as exc:
        st.error(f"No fue posible ejecutar el modelo: {exc}")

run = st.session_state.optimization_run
render_kpis(context, run)

tab_resumen, tab_plan, tab_gantt, tab_mapa = st.tabs(
    ["Resumen", "Planeación", "Cronograma", "Mapa"]
)

with tab_resumen:
    render_dashboard(context, run)

with tab_plan:
    render_planificacion(run, context.config)

with tab_gantt:
    render_gantt(run, context.config)

with tab_mapa:
    render_mapa(context, run)
