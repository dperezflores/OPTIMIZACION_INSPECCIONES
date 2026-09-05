from src.config import OptimizationConfig
from src.feasibility import FeasibilitySolver
from src.models import Auditor, Obra


def make_work(
    obra_id,
    responsable,
    hours,
    supervisor="S1",
    alternates=(),
    contractor=None,
):
    return Obra(
        obra_id=str(obra_id),
        contrato=f"C-{obra_id}",
        descripcion=f"Obra {obra_id}",
        auditor_responsable=responsable,
        duracion_minutos=int(hours * 60),
        latitud=None,
        longitud=None,
        supervisor_preferente_id=supervisor,
        supervisores_alternativos_ids=tuple(alternates),
        contratista_id=contractor,
        prioridad=3,
    )


def test_two_auditors_can_inspect_reciprocal_works_in_one_day():
    cfg = OptimizationConfig(
        hora_inicio="08:00",
        hora_fin="12:00",
        slot_minutos=30,
        time_limit_seconds=5,
        num_search_workers=1,
    )
    auditors = [Auditor("A"), Auditor("B")]
    works = [
        make_work("1", "A", 2, supervisor="S1"),
        make_work("2", "B", 2, supervisor="S2"),
    ]

    result = FeasibilitySolver(works, auditors, cfg).solve(1)

    assert result.factible
    assert len(result.plan) == 2
    assert {
        tuple(sorted((p.auditor_responsable, p.auditor_acompanante)))
        for p in result.plan
    } == {("A", "B")}


def test_alternative_supervisor_can_remove_simultaneous_conflict():
    cfg = OptimizationConfig(
        hora_inicio="08:00",
        hora_fin="10:00",
        slot_minutos=30,
        time_limit_seconds=5,
        num_search_workers=1,
    )
    auditors = [
        Auditor("A"),
        Auditor("B"),
        Auditor("C"),
        Auditor("D"),
    ]
    works = [
        make_work("1", "A", 2, supervisor="S1"),
        make_work(
            "2",
            "C",
            2,
            supervisor="S1",
            alternates=("S2",),
        ),
    ]

    result = FeasibilitySolver(works, auditors, cfg).solve(1)

    assert result.factible
    assert {p.supervisor_seleccionado for p in result.plan} == {
        "S1",
        "S2",
    }


def test_shared_contractor_blocks_two_simultaneous_inspections():
    cfg = OptimizationConfig(
        hora_inicio="08:00",
        hora_fin="10:00",
        slot_minutos=30,
        time_limit_seconds=5,
        num_search_workers=1,
    )
    auditors = [
        Auditor("A"),
        Auditor("B"),
        Auditor("C"),
        Auditor("D"),
    ]
    works = [
        make_work(
            "1",
            "A",
            2,
            supervisor="S1",
            contractor="C1",
        ),
        make_work(
            "2",
            "C",
            2,
            supervisor="S2",
            contractor="C1",
        ),
    ]

    result = FeasibilitySolver(works, auditors, cfg).solve(1)

    assert not result.factible
    assert result.status == "INFEASIBLE"
