from src.alns import ALNSOptimizer
from src.config import OptimizationConfig
from src.distance_matrix import build_travel_matrix
from src.feasibility import FeasibilitySolver
from src.models import Auditor, Obra, TIPO_PROYECTO


def _work(obra_id: str, auditor: str, lat: float, lon: float) -> Obra:
    return Obra(
        obra_id=obra_id,
        contrato=obra_id,
        descripcion=obra_id,
        auditor_responsable=auditor,
        duracion_minutos=60,
        latitud=lat,
        longitud=lon,
        supervisor_preferente_id=None,
        prioridad=3,
        tipo_revision=TIPO_PROYECTO,
    )


def test_alns_preserves_feasibility_and_never_returns_worse_best():
    cfg = OptimizationConfig(
        hora_inicio="08:00",
        hora_fin="12:00",
        slot_minutos=30,
        time_limit_seconds=2,
        num_search_workers=1,
    )
    obras = [
        _work("A", "AUD1", 21.10, -101.65),
        _work("B", "AUD1", 21.11, -101.66),
        _work("C", "AUD2", 21.20, -101.70),
        _work("D", "AUD2", 21.21, -101.71),
    ]
    auditores = [Auditor("AUD1"), Auditor("AUD2")]
    matrix = build_travel_matrix(obras, cfg)
    initial = FeasibilitySolver(obras, auditores, cfg, matrix).solve(2)
    assert initial.factible

    result = ALNSOptimizer(obras, auditores, cfg, matrix, seed=7).optimize(
        initial,
        iterations=3,
        destroy_fraction=0.5,
        repair_time_limit_seconds=1.0,
    )

    assert result.best.factible
    assert len(result.best.plan) == len(obras)
    assert result.best.dias == initial.dias
    assert result.best.operational_cost <= initial.operational_cost + 1e-9
    assert sum(op.uses for op in result.operator_stats) == 3
