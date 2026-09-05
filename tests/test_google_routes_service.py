from services import google_routes_service as grs
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


def test_google_matrix_is_cached_and_expanded_to_works(monkeypatch, tmp_path):
    obras = [
        make_work("1", 21.1, -101.6),
        make_work("2", 21.1, -101.6),
        make_work("3", 21.2, -101.7),
    ]
    cache_path = tmp_path / "routes.json"
    calls = []

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return [
                {"originIndex": 0, "destinationIndex": 0, "status": {}, "condition": "ROUTE_EXISTS", "distanceMeters": 0, "duration": "0s"},
                {"originIndex": 0, "destinationIndex": 1, "status": {}, "condition": "ROUTE_EXISTS", "distanceMeters": 12000, "duration": "1200s"},
                {"originIndex": 1, "destinationIndex": 0, "status": {}, "condition": "ROUTE_EXISTS", "distanceMeters": 13000, "duration": "1320s"},
                {"originIndex": 1, "destinationIndex": 1, "status": {}, "condition": "ROUTE_EXISTS", "distanceMeters": 0, "duration": "0s"},
            ]

    def fake_post(url, headers, json, timeout):
        calls.append((url, headers, json, timeout))
        assert headers["X-Goog-Api-Key"] == "test-key"
        assert json["travelMode"] == "DRIVE"
        assert json["routingPreference"] == "TRAFFIC_UNAWARE"
        return FakeResponse()

    monkeypatch.setattr(grs.requests, "post", fake_post)
    first = grs.build_google_routes_matrix(
        obras,
        "test-key",
        cache_path=cache_path,
    )
    assert first.source == "google_routes"
    assert first.unique_locations == 2
    assert first.billed_elements == 4
    assert first.matrix[("1", "2")].tiempo_estimado_min == 0
    assert first.matrix[("1", "3")].distancia_estimada_km == 12
    assert cache_path.exists()
    assert len(calls) == 1

    def should_not_call(*args, **kwargs):
        raise AssertionError("La segunda carga debía reutilizar la caché")

    monkeypatch.setattr(grs.requests, "post", should_not_call)
    second = grs.build_google_routes_matrix(
        obras,
        "test-key",
        cache_path=cache_path,
    )
    assert second.source == "google_cache"
    assert second.billed_elements == 0
    assert second.matrix[("3", "1")].distancia_estimada_km == 13
