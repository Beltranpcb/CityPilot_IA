import pytest
from app import api_clients
from app.api_clients import CiudadNoEncontrada, geocodificar, obtener_lugares


class RespuestaFalsa:
    def __init__(self, datos):
        self._datos = datos

    def raise_for_status(self):
        pass

    def json(self):
        return self._datos


def test_geocodificar_ciudad_inexistente(monkeypatch):
    # Open-Meteo no devuelve la clave "results" si no hay coincidencia
    monkeypatch.setattr(api_clients.requests, "get", lambda *a, **k: RespuestaFalsa({}))
    with pytest.raises(CiudadNoEncontrada):
        geocodificar("asdfgh")


def test_obtener_lugares_normaliza_way_y_descarta(monkeypatch):
    elementos = {
        "elements": [
            {"type": "node", "lat": 39.1, "lon": -0.1, "tags": {"name": "Museo A", "tourism": "museum"}},
            {"type": "way", "center": {"lat": 39.2, "lon": -0.2}, "tags": {"name": "Castillo B", "historic": "castle"}},
            {"type": "node", "lat": 39.3, "lon": -0.3, "tags": {"name": "museo a"}},  # duplicado
            {"type": "node", "lat": 39.4, "lon": -0.4, "tags": {"tourism": "museum"}},  # sin nombre
        ]
    }
    monkeypatch.setattr(api_clients.requests, "post", lambda *a, **k: RespuestaFalsa(elementos))
    lugares = obtener_lugares(39.47, -0.38, "cultural")

    assert [l["nombre"] for l in lugares] == ["Museo A", "Castillo B"]
    assert lugares[1]["lat"] == 39.2 and lugares[1]["lon"] == -0.2
    assert all(l["fuente"] == "OpenStreetMap" and l["demo"] is False for l in lugares)


def test_obtener_lugares_rechaza_tipo_no_permitido():
    with pytest.raises(ValueError):
        obtener_lugares(39.47, -0.38, "tipo_libre; out;")