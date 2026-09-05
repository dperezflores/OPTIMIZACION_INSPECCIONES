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
- vehículos con capacidad de 4 pasajeros;
- ruteo vehicular con **pickup-and-delivery y paradas intermedias**;
- mínimo número de vehículos como primer objetivo del subproblema vehicular y, con ese mínimo fijado, menor km/tiempo como segundo objetivo;
- viajes individuales permitidos sólo cuando no existe una ruta compartida compatible con capacidad y horarios;
- cálculo separado de km-auditor y km-vehículo;
- refinamiento ALNS activo por defecto (`use_alns=True`);
- respaldo V1 mediante Haversine ajustado cuando se desea probar sin consumir API.

## Objetivo CP-SAT y calidad operativa

CP-SAT mantiene todas las restricciones duras de agenda y sincronización. Su objetivo interno incluye:

- prioridad por día **centrada respecto al promedio de prioridad del lote**;
- dispersión geográfica;
- balance entre días;
- balance entre auditores;
- inicio temprano;
- penalización por supervisor alternativo;
- **minutos de traslado consecutivo de auditores**;
- **minutos de traslado consecutivo de supervisores**;
- **minutos de traslado consecutivo de contratistas**.

La prioridad centrada evita que un lote homogéneo (por ejemplo, todas las actividades con prioridad 3) reciba por sí mismo un empuje artificial hacia el día 1. Sólo las actividades cuya prioridad se separa del promedio tienen incentivo temporal: las de mayor prioridad se favorecen antes y las de menor prioridad pueden desplazarse después. Los pesos de prioridad y balance se mantienen deliberadamente en el mismo orden de magnitud; `src/config.py` documenta rangos relativos recomendados.

Los traslados incluidos en el objetivo usan la misma matriz de rutas y la misma discretización temporal que las restricciones de precedencia. Para auditores se incluyen también ASEG → primera actividad y última actividad → ASEG.

Los componentes que dependen de la solución completa o de decisiones logísticas posteriores siguen evaluándose en `src/quality.py` y son refinados por ALNS, entre ellos:

- km-vehículo;
- viajes compartidos e individuales;
- espera acumulada;
- tiempo adicional fuera de la ventana 08:00–17:00;
- cambios de acompañante;
- balance operativo final.

## Ruteo vehicular V5

`src/vehicle_planner.py` construye las rutas **después** de que `FeasibilitySolver` fija el calendario. El ruteo no modifica quién hace qué actividad, ni el día, ni la hora.

Para cada día se generan solicitudes de transporte de cada auditor entre ASEG y sus actividades. OR-Tools resuelve un problema pickup-and-delivery con ventanas de tiempo y capacidad. Esto permite rutas como:

```text
ASEG (A+B+C+D)
  ↓
Obras Públicas (bajan C+D)
  ↓
Inspección física (continúan A+B)
  ↓
Obras Públicas (recoge C+D)
  ↓
ASEG (A+B+C+D)
```

Reglas principales:

- capacidad máxima: `capacidad_vehiculo = 4`;
- espera máxima de una persona lista para ser recogida en una parada intermedia: `espera_maxima_parada_intermedia_min = 90` por defecto;
- el vehículo puede permanecer estacionado durante una actividad completa; el límite anterior aplica a la persona que espera recogida, no al vehículo;
- responsable y acompañante de una inspección física deben llegar en el mismo vehículo;
- el solver prueba 1 vehículo, luego 2, luego 3, etc.; el primer número factible es el mínimo;
- con ese mínimo fijado se ejecuta una segunda optimización para reducir km/tiempo total;
- si el subsolver no concluye dentro del límite configurado, existe un fallback conservador para no romper `quality.py` ni el dashboard.

El agrupador V5 anterior por coincidencia exacta se conserva únicamente como referencia de regresión/benchmark; producción usa el ruteo optimizado.

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
6. **V5 — Depósito ASEG y logística vehicular:** completada; incorpora salida/regreso, ruteo pickup-and-delivery, mínimo de vehículos, viajes compartidos/individuales y métricas km-vehículo.
7. **Siguiente evolución:** representación operativa final, explicación de rutas/vehículos y, si se requiere, mayor persistencia de matrices y escenarios.
