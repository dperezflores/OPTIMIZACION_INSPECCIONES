# OPTIMIZACION_INSPECCIONES

Motor de optimización para planear inspecciones físicas de obra pública.

El objetivo del proyecto es coordinar auditores, supervisores municipales y contratistas y evolucionar hacia una solución que minimice días, tiempos de traslado, distancias y tiempos muertos.

## Estado actual: V0 + interfaz Streamlit

La V0 utiliza **Google OR-Tools / CP-SAT** para responder:

> ¿Cuál es el menor número de días en el que puede programarse el conjunto completo de inspecciones respetando las reglas operativas básicas?

Actualmente considera:

- auditor responsable obligatorio;
- mínimo dos auditores por inspección;
- parejas de auditores estables durante cada jornada;
- duración estimada de cada revisión;
- jornada laboral;
- supervisor municipal preferente o alternativo;
- imposibilidad de que un supervisor esté en dos obras simultáneamente;
- imposibilidad de que un contratista esté en dos obras simultáneamente;
- prioridad de 1 a 5.

**Todavía no se consideran traslados ni rutas en la V0.** Esa separación es intencional: primero validamos la programación y luego incorporaremos la matriz de viajes, Google Routes y ALNS.

## Dashboard Streamlit

`app.py` es únicamente el punto de entrada de la interfaz. La lógica está separada en capas:

- `src/`: modelo matemático, datos, reglas y optimización;
- `services/`: casos de uso y transformación de resultados;
- `views/`: pantallas de Resumen, Planeación, Cronograma y Mapa;
- `ui/`: estilos y componentes reutilizables.

El dashboard permite configurar el rango de días y el tiempo máximo del solver, ejecutar CP-SAT desde la interfaz y consultar:

- KPIs de inspecciones, auditores, horas y mínimo factible;
- escenarios evaluados;
- planeación detallada y descarga CSV;
- cronograma Gantt por pareja de auditores;
- mapa de las obras y día propuesto.

Para ejecutarlo localmente:

```bash
pip install -r requirements.txt
streamlit run app.py
```

Para Streamlit Community Cloud, el archivo principal es `app.py`.

## Datos

`data/input/obras.csv` contiene las 44 inspecciones normalizadas a partir del archivo de planeación.

Los proyectos ejecutivos que comparten coordenadas conservan esa ubicación porque corresponden a revisiones realizadas en la Dirección General de Obras Públicas del municipio.

En obras con más de un supervisor:

- el primero es el preferente;
- cualquiera de los siguientes puede asistir como alternativa;
- no se requiere presencia simultánea de todos.

## Ejecución por GitHub Actions

El workflow **Ejecutar modelo V0** permite ejecutar el motor sin VS Code. Desde `Actions` se define el rango de días y el tiempo máximo por escenario y se descarga el artefacto con el resumen y la planeación.

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

1. **V0 — Factibilidad:** CP-SAT, parejas, horarios, supervisor y contratista.
2. **V0 UI — Visualización:** Streamlit, Gantt, mapa, KPIs y planeación.
3. **V1 — Geografía:** matriz de distancias y tiempos aproximados entre obras.
4. **V2 — Red vial:** Google Routes para tiempos y kilómetros reales.
5. **V3 — Metaheurística:** ALNS para mejorar rutas, días y parejas.

La formulación de la V0 se documenta en [`docs/MODELO_V0.md`](docs/MODELO_V0.md).
