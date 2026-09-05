from __future__ import annotations

import pandas as pd
import streamlit as st

from services.optimization_service import OptimizationContext
from services.presentation_service import build_map_dataframe
from src.depot import DEPOT_LATITUDE, DEPOT_LONGITUDE, DEPOT_NAME
from src.optimizer import OptimizationRun


def render_mapa(context: OptimizationContext, run: OptimizationRun | None) -> None:
    st.subheader("Mapa de inspecciones")

    if run is None:
        st.info("Ejecuta la optimización para asociar las obras con un día propuesto.")

    map_df = build_map_dataframe(context, run)
    if map_df.empty:
        st.warning("No hay coordenadas disponibles para mostrar.")
        return

    day_options = ["Todos"]
    if run is not None and run.best is not None:
        day_options += [int(d) for d in sorted(map_df["dia"].dropna().unique())]

    selected_day = st.selectbox("Día del mapa", day_options, key="map_day_filter")
    visible = map_df if selected_day == "Todos" else map_df[map_df["dia"] == selected_day]

    depot_row = pd.DataFrame([{"lat": DEPOT_LATITUDE, "lon": DEPOT_LONGITUDE}])
    points = pd.concat([visible[["lat", "lon"]], depot_row], ignore_index=True)
    st.map(points)
    st.write(f"**Base común:** {DEPOT_NAME} · {DEPOT_LATITUDE:.6f}, {DEPOT_LONGITUDE:.6f}")
    st.dataframe(
        visible[["obra_id", "contrato", "auditor", "dia", "descripcion"]],
        use_container_width=True,
        hide_index=True,
        column_config={"descripcion": st.column_config.TextColumn("Obra", width="large")},
    )

    st.caption(
        "V5 incluye ASEG como punto de salida y regreso de los auditores. La tabla de Planeación muestra, además, "
        "los tramos vehiculares compartidos e individuales calculados para la solución seleccionada."
    )
