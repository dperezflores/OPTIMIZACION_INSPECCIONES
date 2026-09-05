# OPTIMIZACION_INSPECCIONES

Motor de optimización para planear revisiones documentales de proyectos e inspecciones físicas de obra pública.

El objetivo es coordinar auditores, supervisores municipales y contratistas, considerando duración, sincronización y desplazamientos por red vial.

## Estado actual: V2 + Streamlit

La V2 utiliza **Google Routes API + Google OR-Tools / CP-SAT**.

Actualmente considera:

- auditor responsable obligatorio en toda actividad;
- **proyecto documental: 1 auditor**;
- **inspección física: responsable + 1 acompañante**;
- acompañante dinámico por inspección física;
- posibilidad de revisar proyectos y posteriormente realizar inspecciones físicas el mismo día;
- duración estimada de cada revisión;
- jornada laboral;
- supervisor municipal preferente o alternativo;
- contratista como recurso sincronizado;
- tiempos de traslado para auditores, supervisores y contratistas;
- matriz real de distancia y duración por red vial mediante **Google Routes Compute Route Matrix**;
- respaldo V1 mediante Haversine ajustado cuando se desea probar sin consumir API.

## Google Routes V2

La integración se encuentra aislada en `services/google_routes_service.py`.

Principios de diseño:

- la API Key se lee exclusivamente desde `GOOGLE_MAPS_API_KEY` en Streamlit Secrets o variable de entorno;
- la clave nunca se escribe en archivos ni en el repositorio;
- las actividades con la misma coordenada se consolidan en una sola ubicación antes de consultar Google;
- las solicitudes se dividen en bloques de máximo 625 elementos origen-destino;
- se solicitan únicamente `originIndex`, `destinationIndex`, `status`, `condition`, `distanceMeters` y `duration`;
- se utiliza `DRIVE` con `TRAFFIC_UNAWARE` en esta primera V2;
- la matriz se guarda en `data/cache/google_routes_matrix.json` y se reutiliza mientras las coordenadas no cambien;
- el archivo de caché está excluido de Git.

> Nota: en Streamlit Community Cloud el almacenamiento local es de ejecución. Un reinicio o redeploy puede eliminar la caché; el sistema la reconstruirá cuando sea necesario. Si se requiere persistencia permanente, la siguiente evolución puede guardar la matriz en una base de datos.

## Clasificación de actividades

El modelo maneja:

- `PROYECTO_DOCUMENTAL`
- `INSPECCION_FISICA`

El cargador admite una columna opcional `tipo_revision`. Mientras el archivo actual no la tenga, las actividades ubicadas en la coordenada conocida de la Dirección General de Obras Públicas se clasifican temporalmente como proyectos documentales.

## Dashboard Streamlit

`app.py` sólo orquesta la interfaz. La aplicación mantiene separación por capas:

- `src/`: modelo matemático, restricciones y optimización;
- `services/`: integración Google Routes, casos de uso y preparación de resultados;
- `views/`: Resumen, Planeación, Cronograma y Mapa;
- `ui/`: estilos y componentes reutilizables.

El dashboard permite:

- elegir **Google Routes V2** o **Haversine V1 (respaldo)**;
- detectar si existe una matriz Google válida en caché;
- forzar una actualización manual de la matriz sólo cuando se desea;
- configurar rango de días y tiempo máximo por escenario;
- ejecutar CP-SAT;
- ver días mínimos, km-auditor y horas de traslado;
- consultar planeación, Gantt, mapa y escenarios evaluados.

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
    config.py
    data_loader.py
    models.py
    validator.py
    feasibility.py
    optimizer.py
    reporting.py
    distance_matrix.py

services/
    optimization_service.py
    google_routes_service.py
    presentation_service.py

views/
    dashboard.py
    planificacion.py
    gantt.py
    mapa.py

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

## Hoja de ruta

1. **V0.1 — Factibilidad:** proyectos individuales, inspecciones físicas en pareja y programación multi-recurso.
2. **V1 — Geografía aproximada:** Haversine, factor vial y velocidad media.
3. **V2 — Red vial:** Google Routes, caché y tiempos/distancias reales.
4. **V2.1 — Función objetivo geográfica:** minimizar explícitamente km, tiempo de viaje, espera y cambios de acompañante.
5. **V3 — Metaheurística:** ALNS para mejorar rutas, días, asignaciones y equilibrio operativo.
