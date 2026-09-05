from collections import Counter

from src.config import OptimizationConfig
from src.depot import DEPOT_ID
from src.distance_matrix import TravelValue
from src.feasibility import FeasibilitySolver
from src.models import Auditor, Obra, TIPO_PROYECTO


def _work(index: int) -> Obra:
    return Obra(
        obra_id=f"P{index:02d}",
        contrato=f"P{index:02d}",
        descripcion=f"Proyecto {index}",
        auditor_responsable="AUD1",
        duracion_minutos=60,
        latitud=21.0,
        longitud=-101.0,
        supervisor_preferente_id=None,
        prioridad=3,
        tipo_revision=TIPO_PROYECTO,
    )


def _zero_matrix(obras: list[Obra]) -> dict[tuple[str, str], TravelValue]:
    ids = [DEPOT_ID] + [o.obra_id for o in obras]
    return {
        (origin, destination): TravelValue(0.0, 0.0, 0.0)
        for origin in ids
        for destination in ids
    }


def test_homogeneous_priorities_do_not_pile_activities_into_first_day():
    obras = [_work(i) for i in range(12)]
    cfg = OptimizationConfig(
        slot_minutos=30,
        time_limit_seconds=5,
        num_search_workers=1,
        peso_obj_dispersion_geografica=0,
        peso_obj_inicio_temprano=0,
    )
    result = FeasibilitySolver(
        obras,
        [Auditor("AUD1")],
        cfg,
        _zero_matrix(obras),
    ).solve(3, random_seed=17)

    assert result.factible
    counts = Counter(item.dia for item in result.plan)
    per_day = [counts.get(day, 0) for day in (1, 2, 3)]
    most = max(per_day)
    least = min(per_day)
    assert least > 0

    # Diferencia relativa respecto al día menos cargado. El umbral del 60 %
    # impediría una distribución tipo 19 vs 8 (+137 %) y tolera pequeñas
    # asimetrías cuando otras restricciones reales obliguen a ellas.
    relative_difference = (most - least) / least
    assert relative_difference <= 0.60
