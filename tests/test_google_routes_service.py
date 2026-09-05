from services import google_routes_service as grs
from services.google_routes_service import _batch_pairs, matrix_signature, unique_locations
from src.depot import DEPOT_ID
from src.models import Obra


def make_work(obra_id: str, lat: float, lon: float) -> Obra:
    return Obra(
        obra_id=obra_id, contrato=obra_id, descripcion=obra_id,
        auditor_responsable="A", duracion_minutos=60,
        latitud=lat, longitud=lon, supervisor_preferente_id=None,
    )


def test_unique_locations_deduplicates_same_coordinate_and_adds_depot():
    obras = [
        make_work("1", 21.1, -101.6),
        make_work("2", 21.1, -101.6),
        make_work("3", 21.2, -101.7),
    ]
    nodes = unique_locations(obras)
    assert len(nodes) == 3  # 2 sitios de trabajo + ASEG
    assert matrix_signature(obras) == matrix_signature(list(reversed(obras)))


def test_google_batches_never_exceed_625_elements():
    nodes = unique_locations([make_work(str(i), 20 + i / 1000, -101 - i / 1000) for i in range(44)])
    batches = _batch_pairs(nodes)
    assert batches
    assert max(len(origins) * len(destinations) for origins, destinations in batches) <= 625


def test_google_matrix_is_cached_expanded_and_contains_depot(monkeypatch, tmp_path):
    obras = [
        make_work("1", 21.1, -101.6),
        make_work("2", 21.1, -101.6),
        make_work("3", 21.2, -101.7),
    ]
    cache_path = tmp_path / "routes.json"
    calls = []

    class FakeResponse:
        def __init__(self, origins, destinations):
            self.origins = origins
            self.destinations = destinations

        def raise_for_status(self):
            return None

        def json(self):
            rows = []
            for oi, origin in enumerate(self.origins):
                for di, destination in enumerate(self.destinations):
                    same = origin == destination
                    rows.append({
                        "originIndex": oi,
                        "destinationIndex": di,
                        "status": {},
                        "condition": "ROUTE_EXISTS",
                        "distanceMeters": 0 if same else 10000 + 1000 * oi + 100 * di,
                        "duration": "0s" if same else "1200s",
                    })
            return rows

    def fake_post(url, headers, json, timeout):
        calls.append((url, headers, json, timeout))
        assert headers["X-Goog-Api-Key"] == "test-key"
        assert json["travelMode"] == "DRIVE"
        assert json["routingPreference"] == "TRAFFIC_UNAWARE"
        origins = [str(o["waypoint"]["location"]["latLng"]) for o in json["origins"]]
        destinations = [str(d["waypoint"]["location"]["latLng"]) for d in json["destinations"]]
        return FakeResponse(origins, destinations)

    monkeypatch.setattr(grs.requests, "post", fake_post)
    first = grs.build_google_routes_matrix(obras, "test-key", cache_path=cache_path)
    assert first.source == "google_routes"
    assert first.unique_locations == 3
    assert first.billed_elements == 9
    assert first.matrix[("1", "2")].tiempo_estimado_min == 0
    assert (DEPOT_ID, "1") in first.matrix
    assert ("1", DEPOT_ID) in first.matrix
    assert cache_path.exists()
    assert len(calls) == 1

    def should_not_call(*args, **kwargs):
        raise AssertionError("La segunda carga debía reutilizar la caché")

    monkeypatch.setattr(grs.requests, "post", should_not_call)
    second = grs.build_google_routes_matrix(obras, "test-key", cache_path=cache_path)
    assert second.source == "google_cache"
    assert second.billed_elements == 0
    assert (DEPOT_ID, "3") in second.matrix
