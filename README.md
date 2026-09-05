# OPTIMIZACION_INSPECCIONES

Motor de optimización para planear revisiones documentales de proyectos e inspecciones físicas de obra pública.

El objetivo del proyecto es coordinar auditores, supervisores municipales y contratistas y evolucionar hacia una solución que minimice días, tiempos de traslado, distancias y tiempos muertos.

## Estado actual: V0.1 + interfaz Streamlit

La V0.1 utiliza **Google OR-Tools / CP-SAT** para responder:

> ¿Cuál es el menor número de días en el que puede programarse el conjunto completo de actividades respetando las reglas operativas básicas?

Actualmente considera:

- auditor responsable obligatorio en toda actividad;
- **proyecto documental: 1 auditor**;
- **inspección física: responsable + 1 acompañante**;
- acompañante dinámico por inspección física, no una pareja obligatoria durante toda la jornada;
- posibilidad de revisar proyectos y posteriormente realizar inspecciones físicas el mismo día;
- duración estimada de cada revisión;
- jornada laboral;
- supervisor municipal preferente o alternativo;
- imposibilidad de que un supervisor esté en dos actividades simultáneamente;
- imposibilidad de que un contratista esté en dos actividades simultáneamente;
- prioridad de 1 a 5.

**Todavía no se consideran traslados ni rutas.** Esa separación es intencional: primero validamos la programación y luego incorporaremos matriz de viajes, Google Routes y ALNS.

## Clasificación de actividades

El modelo maneja explícitamente dos valores internos:

- `PROYECTO_DOCUMENTAL`
- `INSPECCION_FISICA`

El cargador admite una columna opcional `tipo_revision` en el CSV. Mientras el archivo actual no tenga esa columna, las 17 actividades ubicadas en la coordenada conocida de la Dirección General de Obras Públicas se clasifican temporalmente como proyectos documentales; las demás se consideran inspecciones físicas.

## Dashboard Streamlit

`app.py` es únicamente el punto de entrada de la interfaz. La lógica está separada en capas:

- `src/`: modelo matemático, datos, reglas y optimización;
- `services/`: casos de uso y transformación de resultados;
- `views/`: pantallas de Resumen, Planeación, Cronograma y Mapa;
- `ui/`: estilos y componentes reutilizables.

El dashboard permite configurar el rango de días y el tiempo máximo del solver, ejecutar CP-SAT y consultar:

- KPIs de actividades, proyectos, inspecciones físicas, auditores y mínimo factible;
- escenarios evaluados;
- planeación detallada y descarga CSV;
- cronograma Gantt con actividades individuales y en pareja;
- mapa de las actividades y día propuesto.

Para ejecutarlo localmente:

```bash
pip install -r requirements.txt
streamlit run app.py
```

Para Streamlit Community Cloud, el archivo principal es `app.py`.

## Datos

`data/input/obras.csv` contiene las 44 actividades normalizadas a partir del archivo de planeación.

Los proyectos ejecutivos que comparten coordenadas conservan esa ubicación porque corresponden a revisiones realizadas en la Dirección General de Obras Públicas del municipio.

En actividades con más de un supervisor:

- el primero es el preferente;
- cualquiera de los siguientes puede asistir como alternativa;
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
    presentation_service.py

views/
    dashboard.py
    planificacion.py
    gantt.py
    mapa.py

ui/
    components.py
    styles.py

data/input/
    obras.csv
    auditores.csv
    parametros.json

tests/
docs/
```

## Hoja de ruta

1. **V0.1 — Factibilidad:** proyectos individuales, inspecciones físicas en pareja y programación multi-recurso.
2. **V0.1 UI — Visualización:** Streamlit, Gantt, mapa, KPIs y planeación.
3. **V1 — Geografía:** matriz de distancias y tiempos aproximados entre actividades.
4. **V2 — Red vial:** Google Routes para tiempos y kilómetros reales.
5. **V3 — Metaheurística:** ALNS para mejorar rutas, días y asignaciones.
