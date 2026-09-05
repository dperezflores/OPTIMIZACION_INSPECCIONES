from src.config import OptimizationConfig
from src.depot import DEPOT_ID
from src.distance_matrix import TravelValue
from src.feasibility import FeasibilitySolver
from src.models import Auditor, Obra, TIPO_PROYECTO


def _work(obra_id: str) -> Obra:
    return Obra(
        obra_id=obra_id,
        contrato=obra_id,
        descripcion=obra_id,
        auditor_responsable="AUD1",
        duracion_minutos=60,
        latitud=21.0,
        longitud=-101.0,
        supervisor_preferente_id=None,
        contratista_id=None,
        prioridad=3,
        tipo_revision=TIPO_PROYECTO,
    )


def _value(minutes: float) -> TravelValue:
    # Para esta prueba la distancia no interviene en el costo; usamos un valor
    # proporcional únicamente para mantener una matriz realista.
    return TravelValue(minutes / 60.0, minutes / 60.0, minutes)


def _matrix() -> dict[tuple[str, str], TravelValue]:
    nodes = [DEPOT_ID, "A", "B", "C"]
    matrix: dict[tuple[str, str], TravelValue] = {}
    for origin in nodes:
        for destination in nodes:
            if origin == destination:
                matrix[(origin, destination)] = _value(0)
            else:
                matrix[(origin, destination)] = _value(60)

    # Ruta claramente preferible: ASEG -> A -> B -> C -> ASEG.
    matrix[(DEPOT_ID, "A")] = _value(30)
    matrix[("A", "B")] = _value(30)
    matrix[("B", "C")] = _value(30)
    matrix[("C", DEPOT_ID)] = _value(30)
    return matrix


def test_cpsat_travel_objective_improves_or_matches_operational_cost_before_alns():
    cfg = OptimizationConfig(
        hora_inicio="08:00",
        hora_fin="17:00",
        slot_minutos=30,
        time_limit_seconds=5,
        num_search_workers=1,
        # Neutralizamos el objetivo histórico para aislar el efecto del traslado.
        peso_obj_prioridad_dia=0,
        peso_obj_dispersion_geografica=0,
        peso_obj_balance_dia=0,
        peso_obj_balance_auditor=0,
        peso_obj_inicio_temprano=0,
        peso_obj_supervisor_alternativo=0,
        # operational_cost de esta prueba representa sólo minutos de auditor.
        peso_calidad_traslado_auditor=1.0,
        peso_calidad_traslado_supervisor=0.0,
        peso_calidad_traslado_contratista=0.0,
        peso_calidad_espera=0.0,
        peso_calidad_balance_dia=0.0,
        peso_calidad_balance_auditor=0.0,
        peso_calidad_cambio_acompanante=0.0,
        peso_calidad_km_vehiculo=0.0,
        peso_calidad_viaje_solo=0.0,
        peso_calidad_viaje_vehicular=0.0,
        peso_calidad_tiempo_adicional=0.0,
    )
    obras = [_work("A"), _work("B"), _work("C")]
    auditores = [Auditor("AUD1")]
    matrix = _matrix()

    baseline = FeasibilitySolver(
        obras,
        auditores,
        cfg,
        matrix,
        enable_travel_objective=False,
    ).solve(1, random_seed=11)
    aligned = FeasibilitySolver(
        obras,
        auditores,
        cfg,
        matrix,
        enable_travel_objective=True,
    ).solve(1, random_seed=11)

    assert baseline.factible
    assert aligned.factible
    assert len(aligned.plan) == len(obras)
    assert aligned.operational_cost <= baseline.operational_cost + 1e-9
    assert aligned.auditor_travel_min <= baseline.auditor_travel_min + 1e-9
