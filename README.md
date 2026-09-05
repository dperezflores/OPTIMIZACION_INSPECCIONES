# OPTIMIZACION_INSPECCIONES

Motor de optimización para planear revisiones documentales de proyectos e inspecciones físicas de obra pública.

El objetivo es coordinar auditores, supervisores municipales y contratistas, considerando duración, sincronización, desplazamientos por red vial, salida/regreso a ASEG y uso compartido de vehículos.

## Estado actual: V5 + Streamlit

La V5 utiliza **Google Routes API + Google OR-Tools / CP-SAT + ALNS**.

Actualmente considera:

- auditor responsable obligatorio en toda actividad;
- **proyecto documental: 1 auditor**;
- **inspección física: responsable + 1 acompañante**;
- acompañante dinámico por inspección física;
- posibilidad de revisar proyectos y posteriormente realizar inspecciones físicas el mismo día;
- duración estimada de cada revisión;
- ventana de actividades 08:00–17:00;
- salida y regreso a las instalaciones de ASEG como depósito común;
- supervisor municipal preferente o alternativo;
- contratista como recurso sincronizado;
- tiempos de traslado para auditores, supervisores y contratistas;
- matriz real de distancia y duración por red vial mediante **Google Routes Compute Route Matrix**;
- vehículos con capacidad de 4 pasajeros, compartidos cuando es compatible;
- viajes individuales permitidos cuando son necesarios, pero penalizados;
- cálculo separado de km-auditor y km-vehículo;
- refinamiento ALNS activo por defecto (`use_alns=True`);
- respaldo V1 mediante Haversine ajustado cuando se desea probar sin consumir API.

## Objetivo CP-SAT y calidad operativa

CP-SAT mantiene todas las restricciones duras de agenda y sincronización. Su objetivo interno incluye:

- prioridad por día;
- dispersión geográfica;
- balance entre días;
- balance entre auditores;
- inicio temprano;
- penalización por supervisor alternativo;
- **minutos de traslado consecutivo de auditores**;
- **minutos de traslado consecutivo de supervisores**;
- **minutos de traslado consecutivo de contratistas**.

Los traslados incluidos en el objetivo usan la misma matriz de rutas y la misma discretización temporal que las restricciones de precedencia. Para auditores se incluyen también ASEG → primera actividad y última actividad → ASEG.

Los componentes que dependen de la solución completa o de decisiones logísticas posteriores siguen evaluándose en `src/quality.py` y son refinados por ALNS, entre ellos:

- km-vehículo;
- viajes compartidos e individuales;
- espera acumulada;
- tiempo adicional fuera de la ventana 08:00–17:00;
- cambios de acompañante;
- balance operativo final.

## Google Routes V2

La integración se encuentra aislada en `services/google_routes_service.py`.

Principios de diseño:

- la API Key se lee exclusivamente desde `GOOGLE_MAPS_API_KEY` en Streamlit Secrets o variable de entorno;
- la clave nunca se escribe en archivos ni en el repositorio;
- las actividades con la misma coordenada se consolidan en una sola ubicación antes de consultar Google;
- ASEG se incorpora como nodo de depósito;
- las solicitudes se dividen en bloques de máximo 625 elementos origen-destino;
- se solicitan únicamente los campos necesarios de distancia/duración/estado;
- se utiliza `DRIVE` con `TRAFFIC_UNAWARE`;
- la matriz se guarda en `data/cache/google_routes_matrix.json` y se reutiliza mientras las coordenadas no cambien;
- el archivo de caché está excluido de Git.

> Nota: en Streamlit Community Cloud el almacenamiento local es de ejecución. Un reinicio o redeploy puede eliminar la caché; el sistema la reconstruirá cuando sea necesario.

## Clasificación de actividades

El modelo maneja:

- `PROYECTO_DOCUMENTAL`
- `INSPECCION_FISICA`

El cargador admite una columna opcional `tipo_revision`. Mientras el archivo actual no la tenga, las actividades ubicadas en la coordenada conocida de la Dirección General de Obras Públicas se clasifican temporalmente como proyectos documentales.

## Dashboard Streamlit

`app.py` sólo orquesta la interfaz. La aplicación mantiene separación por capas:

- `src/`: modelo matemático, restricciones, calidad, vehículos y ALNS;
- `services/`: integración Google Routes, casos de uso y preparación de resultados;
- `views/`: Resumen, Planeación, Cronograma y Mapa;
- `ui/`: estilos y componentes reutilizables.

El dashboard permite:

- elegir **Google Routes V2** o **Haversine V1 (respaldo)**;
- detectar si existe una matriz Google válida en caché;
- forzar una actualización manual de la matriz sólo cuando se desea;
- configurar rango de días y tiempo máximo por escenario;
- ejecutar CP-SAT y comparar escenarios;
- activar/refinar con ALNS;
- ver días mínimos, km-auditor, km-vehículo, tiempos de traslado y calidad operativa;
- consultar planeación, logística vehicular, Gantt, mapa y escenarios evaluados.

Para Streamlit Community Cloud se requiere el Secret:

```toml
GOOGLE_MAPS_API_KEY = "..."
```

La clave no debe colocarse en GitHub.

## Datos

`data/input/obras.csv` contiene las 44 actividades normalizadas.

Los proyectos ejecutivos que comparten coordenadas conservan esa ubicación porque corresponden a revisiones documentales realizadas en la Dirección General de Obras Públicas.

En actividades con más de un supervisor:

- el primero es preferente;
- los siguientes son alternativas válidas;
- no se requiere presencia simultánea de todos.

## Arquitectura

```text
app.py

src/
    alns.py
    config.py
    data_loader.py
    depot.py
    distance_matrix.py
    feasibility.py
    models.py
    optimizer.py
    quality.py
    reporting.py
    validator.py
    vehicle_planner.py

services/
    google_routes_service.py
    optimization_service.py
    presentation_service.py

views/
    dashboard.py
    gantt.py
    mapa.py
    planificacion.py

ui/
    components.py
    styles.py

data/
    input/
    cache/
    output/

tests/
docs/
```

## Hoja de ruta / estado

1. **V0.1 — Factibilidad:** completada.
2. **V1 — Geografía aproximada:** completada con Haversine.
3. **V2 — Red vial:** completada con Google Routes y caché.
4. **V3 — Calidad multiobjetivo:** completada; CP-SAT compara escenarios con criterios operativos.
5. **V4 — Metaheurística ALNS:** completada e integrada; ALNS refina la mejor solución CP-SAT y está activo por defecto.
6. **V5 — Depósito ASEG y logística vehicular:** completada; incorpora salida/regreso, vehículos compartidos, viajes individuales y métricas km-vehículo.
7. **Siguiente evolución:** representación operativa final, explicación de rutas/vehículos y, si se requiere, mayor persistencia de matrices y escenarios.
