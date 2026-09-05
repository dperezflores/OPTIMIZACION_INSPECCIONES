from src.config import OptimizationConfig
from src.distance_matrix import TravelValue
from src.models import PlanItem, TIPO_FISICA
from src.quality import calculate_quality_metrics


def item(obra_id: str, start: int, end: int, companion: str | None = None) -> PlanItem:
    return PlanItem(
        obra_id=obra_id,
        contrato=obra_id,
        descripcion=obra_id,
        dia=1,
        inicio_slot=start,
        fin_slot=end,
        auditor_responsable="A",
        auditor_acompanante=companion,
        supervisor_seleccionado=None,
        contratista_id=None,
        prioridad=3,
        tipo_revision=TIPO_FISICA,
    )


def test_quality_detects_waiting_and_companion_change():
    config = OptimizationConfig(slot_minutos=30)
    plan = [
        item("1", 0, 2, "B"),
        item("2", 4, 6, "C"),
    ]
    matrix = {
        ("1", "1"): TravelValue(0, 0, 0),
        ("2", "2"): TravelValue(0, 0, 0),
        ("1", "2"): TravelValue(2, 2, 30),
        ("2", "1"): TravelValue(2, 2, 30),
    }
    metrics = calculate_quality_metrics(plan, matrix, config)
    assert metrics.espera_auditor_min == 30
    assert metrics.cambios_acompanante == 1
    assert metrics.costo_operativo > 0
