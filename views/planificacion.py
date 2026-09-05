from __future__ import annotations

import streamlit as st

from services.presentation_service import build_plan_dataframe, select_solution
from src.config import OptimizationConfig
from src.optimizer import OptimizationRun


def render_planificacion(run: OptimizationRun | None, config: OptimizationConfig) -> None:
    st.subheader("Planeación propuesta")

    if run is None or run.best is None:
        st.info("No hay una solución disponible para mostrar.")
        return

    options = {"Mínimo factible": "minimum"}
    if run.quality_best is not None:
        options["Mejor calidad CP-SAT"] = "quality"
    if run.refined_best is not None:
        options["Refinada con ALNS"] = "refined"

    selected_label = st.selectbox(
        "Solución a visualizar",
        options=list(options.keys()),
        index=len(options) - 1,
        help="La solución refinada ALNS conserva el mismo número de días de la mejor calidad CP-SAT y busca mejorar su costo operativo.",
    )
    mode = options[selected_label]
    selected_solution = select_solution(run, mode)
    plan_df = build_plan_dataframe(run, config, mode=mode)
    if plan_df.empty or selected_solution is None:
        st.info("La solución no contiene actividades programadas.")
        return

    selected_day = st.selectbox(
        "Día",
        options=["Todos"] + [int(d) for d in sorted(plan_df["Día"].unique())],
        key=f"plan_day_filter_{mode}",
    )
    visible = plan_df if selected_day == "Todos" else plan_df[plan_df["Día"] == selected_day]
    st.dataframe(
        visible,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Obra": st.column_config.TextColumn(width="large"),
            "Prioridad": st.column_config.NumberColumn(format="%d"),
        },
    )

    st.download_button(
        "Descargar planeación CSV",
        data=plan_df.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"planificacion_{mode}_{selected_solution.dias}_dias.csv",
        mime="text/csv",
        use_container_width=False,
    )
