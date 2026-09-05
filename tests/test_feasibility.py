from src.config import OptimizationConfig
from src.feasibility import FeasibilitySolver
from src.models import Auditor, Obra, TIPO_PROYECTO


def make_work(
    obra_id,
    responsable,
    hours,
    supervisor="S1",
    alternates=(),
    contractor=None,
    tipo_revision="INSPECCION_FISICA",
    lat=None,
    lon=None,
):
    return Obra(
        obra_id=str(obra_id),
        contrato=f"C-{obra_id}",
        descripcion=f"Obra {obra_id}",
        auditor_responsable=responsable,
        duracion_minutos=int(hours * 60),
        latitud=lat,
        longitud=lon,
        supervisor_preferente_id=supervisor,
        supervisores_alternativos_ids=tuple(alternates),
        contratista_id=contractor,
        prioridad=3,
        tipo_revision=tipo_revision,
    )


def test_two_auditors_can_inspect_reciprocal_works_in_one_day():
    cfg = OptimizationConfig(hora_inicio="08:00", hora_fin="12:00", slot_minutos=30, time_limit_seconds=5, num_search_workers=1)
    auditors = [Auditor("A"), Auditor("B")]
    works = [make_work("1", "A", 2, supervisor="S1"), make_work("2", "B", 2, supervisor="S2")]
    result = FeasibilitySolver(works, auditors, cfg).solve(1)
    assert result.factible
    assert len(result.plan) == 2


def test_project_documentary_review_needs_only_responsible_auditor():
    cfg = OptimizationConfig(hora_inicio="08:00", hora_fin="10:00", slot_minutos=30, time_limit_seconds=5, num_search_workers=1)
    result = FeasibilitySolver(
        [make_work("P1", "A", 2, supervisor=None, tipo_revision=TIPO_PROYECTO)],
        [Auditor("A")], cfg,
    ).solve(1)
    assert result.factible
    assert result.plan[0].auditor_acompanante is None


def test_project_and_physical_review_can_share_same_day():
    cfg = OptimizationConfig(hora_inicio="08:00", hora_fin="12:00", slot_minutos=30, time_limit_seconds=5, num_search_workers=1)
    works = [make_work("P1", "A", 2, supervisor="S1", tipo_revision=TIPO_PROYECTO), make_work("F1", "A", 2, supervisor="S2")]
    result = FeasibilitySolver(works, [Auditor("A"), Auditor("B")], cfg).solve(1)
    assert result.factible


def test_alternative_supervisor_can_remove_simultaneous_conflict():
    cfg = OptimizationConfig(hora_inicio="08:00", hora_fin="10:00", slot_minutos=30, time_limit_seconds=5, num_search_workers=1)
    auditors = [Auditor("A"), Auditor("B"), Auditor("C"), Auditor("D")]
    works = [make_work("1", "A", 2, supervisor="S1"), make_work("2", "C", 2, supervisor="S1", alternates=("S2",))]
    result = FeasibilitySolver(works, auditors, cfg).solve(1)
    assert result.factible
    assert {p.supervisor_seleccionado for p in result.plan} == {"S1", "S2"}


def test_shared_contractor_blocks_two_simultaneous_inspections():
    cfg = OptimizationConfig(hora_inicio="08:00", hora_fin="10:00", slot_minutos=30, time_limit_seconds=5, num_search_workers=1)
    auditors = [Auditor("A"), Auditor("B"), Auditor("C"), Auditor("D")]
    works = [make_work("1", "A", 2, supervisor="S1", contractor="C1"), make_work("2", "C", 2, supervisor="S2", contractor="C1")]
    result = FeasibilitySolver(works, auditors, cfg).solve(1)
    assert not result.factible


def test_travel_time_can_make_same_day_infeasible():
    # ~55 km geodésicos entre los puntos. A 60 km/h y factor 1 equivale a ~55 min,
    # redondeados a 60 min con slots de 30. Dos revisiones de 2 h necesitan 5 h.
    cfg = OptimizationConfig(
        hora_inicio="08:00", hora_fin="12:30", slot_minutos=30,
        time_limit_seconds=5, num_search_workers=1,
        factor_distancia_vial=1.0, velocidad_promedio_kmh=60.0,
        incluir_traslados=True,
    )
    works = [
        make_work("P1", "A", 2, supervisor=None, tipo_revision=TIPO_PROYECTO, lat=21.0, lon=-101.0),
        make_work("P2", "A", 2, supervisor=None, tipo_revision=TIPO_PROYECTO, lat=21.5, lon=-101.0),
    ]
    result = FeasibilitySolver(works, [Auditor("A")], cfg).solve(1)
    assert not result.factible


def test_same_coordinates_require_zero_travel():
    cfg = OptimizationConfig(hora_inicio="08:00", hora_fin="12:00", slot_minutos=30, time_limit_seconds=5, num_search_workers=1)
    works = [
        make_work("P1", "A", 2, supervisor=None, tipo_revision=TIPO_PROYECTO, lat=21.1, lon=-101.6),
        make_work("P2", "A", 2, supervisor=None, tipo_revision=TIPO_PROYECTO, lat=21.1, lon=-101.6),
    ]
    result = FeasibilitySolver(works, [Auditor("A")], cfg).solve(1)
    assert result.factible
    assert result.auditor_travel_km == 0
