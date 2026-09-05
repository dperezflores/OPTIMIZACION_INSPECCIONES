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
    assert metrics.solo_legs == 0
