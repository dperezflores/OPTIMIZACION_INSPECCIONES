from services.google_routes_service import _batch_pairs, matrix_signature, unique_locations
from src.models import Obra


def make_work(obra_id: str, lat: float, lon: float) -> Obra:
    return Obra(
        obra_id=obra_id,
        contrato=obra_id,
        descripcion=obra_id,
        auditor_responsable="A",
        duracion_minutos=60,
        latitud=lat,
        longitud=lon,
        supervisor_preferente_id=None,
    )


def test_unique_locations_deduplicates_same_coordinate():
    obras = [
        make_work("1", 21.1, -101.6),
        make_work("2", 21.1, -101.6),
        make_work("3", 21.2, -101.7),
    ]
    nodes = unique_locations(obras)
    assert len(nodes) == 2
    assert matrix_signature(obras) == matrix_signature(list(reversed(obras)))


def test_google_batches_never_exceed_625_elements():
    nodes = unique_locations(
        [make_work(str(i), 20 + i / 1000, -101 - i / 1000) for i in range(44)]
    )
    batches = _batch_pairs(nodes)
    assert batches
    assert max(len(origins) * len(destinations) for origins, destinations in batches) <= 625
