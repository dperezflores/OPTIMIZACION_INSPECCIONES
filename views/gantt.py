from __future__ import annotations

import plotly.express as px
import streamlit as st

from services.presentation_service import build_gantt_dataframe
from src.config import OptimizationConfig
from src.optimizer import OptimizationRun


def render_gantt(run: OptimizationRun | None, config: OptimizationConfig) -> None:
    st.subheader("Cronograma de inspecciones")

    if run is None or run.best is None:
        st.info("No hay una solución disponible para mostrar.")
        return

    gantt_df = build_gantt_dataframe(run, config)
    if gantt_df.empty:
        st.info("La solución no contiene actividades programadas.")
        return

    selected_day = st.selectbox(
        "Día del cronograma",
        options=[int(d) for d in range(1, run.best.dias + 1)],
        key="gantt_day_filter",
    )
    visible = gantt_df[gantt_df["Día"] == f"Día {selected_day}"].copy()

    fig = px.timeline(
        visible,
        x_start="Inicio",
        x_end="Fin",
        y="Pareja",
        color="Responsable",
        hover_name="Obra",
        hover_data={"Día": True, "Responsable": True},
    )
    fig.update_yaxes(autorange="reversed")
    fig.update_layout(
        height=max(420, 80 + 55 * max(1, visible["Pareja"].nunique())),
        legend_title_text="Responsable",
        margin=dict(l=20, r=20, t=30, b=20),
    )
    st.plotly_chart(fig, use_container_width=True)
