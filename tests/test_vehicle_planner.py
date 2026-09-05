from src.config import OptimizationConfig
from src.depot import DEPOT_ID
from src.distance_matrix import TravelValue
from src.models import PlanItem, TIPO_FISICA, TIPO_PROYECTO
from src.vehicle_planner import calculate_vehicle_plan


def item(obra_id: str, auditor: str, start: int, end: int, tipo: str = TIPO_PROYECTO, companion: str | None = None):
    return PlanItem(
        obra_id=obra_id,
        contrato=obra_id,
        descripcion=obra_id,
        dia=1,
        inicio_slot=start,
        fin_slot=end,
        auditor_responsable=auditor,
        auditor_acompanante=companion,
        supervisor_seleccionado=None,
        contratista_id=None,
        prioridad=3,
        tipo_revision=tipo,
    )


def test_four_auditors_to_same_project_site_share_one_vehicle_each_way():
    cfg = OptimizationConfig(slot_minutos=30, capacidad_vehiculo=4)
    plan = [item("DGOP", auditor, 2, 6) for auditor in ("A", "B", "C", "D")]
    matrix = {
        (DEPOT_ID, "DGOP"): TravelValue(10, 10, 30),
        ("DGOP", DEPOT_ID): TravelValue(10, 10, 30),
        ("DGOP", "DGOP"): TravelValue(0, 0, 0),
        (DEPOT_ID, DEPOT_ID): TravelValue(0, 0, 0),
    }
    metrics = calculate_vehicle_plan(plan, matrix, cfg)
    assert metrics.vehicles_required_peak == 1
    assert metrics.vehicle_trips == 2
    assert metrics.shared_legs == 2
    assert metrics.solo_legs == 0
    assert metrics.vehicle_km == 20
    assert all(leg.ocupacion == 4 for leg in metrics.legs if leg.distancia_km > 0)


def test_physical_pair_uses_same_vehicle_when_they_share_origin():
    cfg = OptimizationConfig(slot_minutos=30, capacidad_vehiculo=4)
    plan = [item("F1", "A", 2, 6, TIPO_FISICA, "B")]
    matrix = {
        (DEPOT_ID, "F1"): TravelValue(12, 12, 30),
        ("F1", DEPOT_ID): TravelValue(12, 12, 30),
        ("F1", "F1"): TravelValue(0, 0, 0),
        (DEPOT_ID, DEPOT_ID): TravelValue(0, 0, 0),
    }
    metrics = calculate_vehicle_plan(plan, matrix, cfg)
    outbound = [leg for leg in metrics.legs if leg.destino_id == "F1" and leg.distancia_km > 0]
    assert len(outbound) == 1
    assert set(outbound[0].pasajeros) == {"A", "B"}
    assert metrics.vehicles_required_peak == 1
    assert metrics.solo_legs == 0


def test_one_vehicle_can_drop_project_auditors_continue_to_physical_and_pick_them_up():
    """Caso operativo objetivo: ASEG -> DGOP -> física -> DGOP -> ASEG.

    C y D revisan proyectos en DGOP de 09:00 a 12:00. A+B tienen inspección
    física de 10:00 a 11:00. Un vehículo puede llevar a los cuatro, dejar C+D,
    continuar con A+B, volver por C+D y regresar a ASEG.
    """
    cfg = OptimizationConfig(
        slot_minutos=30,
        capacidad_vehiculo=4,
        espera_maxima_parada_intermedia_min=90,
        vehicle_routing_time_limit_seconds=2.0,
    )
    plan = [
        item("DGOP", "C", 2, 8, TIPO_PROYECTO),
        item("DGOP", "D", 2, 8, TIPO_PROYECTO),
        item("FISICA", "A", 4, 6, TIPO_FISICA, "B"),
    ]
    nodes = (DEPOT_ID, "DGOP", "FISICA")
    matrix = {(node, node): TravelValue(0, 0, 0) for node in nodes}
    matrix.update(
        {
            (DEPOT_ID, "DGOP"): TravelValue(10, 10, 30),
            ("DGOP", DEPOT_ID): TravelValue(10, 10, 30),
            ("DGOP", "FISICA"): TravelValue(20, 20, 30),
            ("FISICA", "DGOP"): TravelValue(20, 20, 30),
            (DEPOT_ID, "FISICA"): TravelValue(25, 25, 60),
            ("FISICA", DEPOT_ID): TravelValue(25, 25, 60),
        }
    )

    metrics = calculate_vehicle_plan(plan, matrix, cfg)

    assert metrics.rendezvous_issues == 0
    assert metrics.vehicles_required_peak == 1
    assert metrics.solo_legs == 0
    assert any(
        leg.origen_id == DEPOT_ID
        and leg.destino_id == "DGOP"
        and set(leg.pasajeros) == {"A", "B", "C", "D"}
        for leg in metrics.legs
    )
    assert any(
        leg.origen_id == "DGOP"
        and leg.destino_id == "FISICA"
        and set(leg.pasajeros) == {"A", "B"}
        for leg in metrics.legs
    )
    assert any(
        leg.origen_id == "FISICA"
        and leg.destino_id == "DGOP"
        and set(leg.pasajeros) == {"A", "B"}
        for leg in metrics.legs
    )
    assert any(
        leg.origen_id == "DGOP"
        and leg.destino_id == DEPOT_ID
        and set(leg.pasajeros) == {"A", "B", "C", "D"}
        for leg in metrics.legs
    )


def test_legacy_config_without_vehicle_capacity_uses_default_four():
    class LegacyConfig:
        incluir_traslados = True
        slot_minutos = 30
        minutos_jornada = 540
        espera_maxima_parada_intermedia_min = 90
        vehicle_routing_time_limit_seconds = 1.0

        @staticmethod
        def traslado_minutos_a_slots(minutes: float) -> int:
            return 0 if minutes <= 0 else int((minutes + 29) // 30)

    cfg = LegacyConfig()
    plan = [item("DGOP", auditor, 2, 6) for auditor in ("A", "B", "C", "D")]
    matrix = {
        (DEPOT_ID, "DGOP"): TravelValue(10, 10, 30),
        ("DGOP", DEPOT_ID): TravelValue(10, 10, 30),
        ("DGOP", "DGOP"): TravelValue(0, 0, 0),
        (DEPOT_ID, DEPOT_ID): TravelValue(0, 0, 0),
    }
    metrics = calculate_vehicle_plan(plan, matrix, cfg)
    assert metrics.vehicles_required_peak == 1
    assert metrics.vehicle_trips == 2
    assert all(leg.ocupacion == 4 for leg in metrics.legs if leg.distancia_km > 0)
