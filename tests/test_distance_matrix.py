from src.distance_matrix import haversine_km


def test_haversine_same_point_is_zero():
    assert haversine_km(21.135374, -101.652066, 21.135374, -101.652066) == 0
