"""Clientes HTTP de datos públicos. Se entregan los contratos, NO la solución."""
import json
import os
from pathlib import Path
import requests

GEO_URL = os.getenv("OPEN_METEO_GEO_URL", "https://geocoding-api.open-meteo.com/v1/search")
METEO_URL = os.getenv("OPEN_METEO_WEATHER_URL", "https://api.open-meteo.com/v1/forecast")
OVERPASS_URL = os.getenv("OVERPASS_URL", "https://overpass-api.de/api/interpreter")

TIMEOUT = 8


class CiudadNoEncontrada(ValueError):
    """La ciudad no existe en el geocodificador (error del usuario, 400)."""


class ErrorProveedor(Exception):
    """Falla un servicio externo: HTTP, timeout o JSON raro (502/503)."""

def geocodificar(ciudad: str) -> dict:
    """Ciudad -> {'ciudad', 'pais', 'lat', 'lon'} usando Open-Meteo Geocoding.

    Lanza CiudadNoEncontrada si no hay coincidencia y ErrorProveedor si falla el servicio.
    """
    ciudad = (ciudad or "").strip()
    if not ciudad:
        raise CiudadNoEncontrada("La ciudad está vacía.")

    params = {"name": ciudad, "count": 1, "language": "es", "countryCode": "ES"}
    try:
        r = requests.get(GEO_URL, params=params, timeout=TIMEOUT)
        r.raise_for_status()
        contenido = r.json()
    except (requests.RequestException, ValueError) as e:
        raise ErrorProveedor("No se pudo consultar el servicio de geocodificación.") from e

    resultados = contenido.get("results")
    if not resultados:
        raise CiudadNoEncontrada(f"No se ha encontrado la ciudad «{ciudad}» en España.")

    primero = resultados[0]
    try:
        return {
            "ciudad": primero["name"],
            "pais": primero.get("country", "España"),
            "lat": float(primero["latitude"]),
            "lon": float(primero["longitude"]),
        }
    except (KeyError, TypeError, ValueError) as e:
        raise ErrorProveedor("Respuesta de geocodificación incompleta.") from e


def obtener_meteorologia(lat: float, lon: float) -> dict:
    """Coordenadas -> condiciones actuales normalizadas (Open-Meteo Forecast).

    Los campos ausentes se devuelven como None, nunca como 0.
    """
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": "temperature_2m,precipitation,weather_code",
        "timezone": "auto",
    }
    try:
        r = requests.get(METEO_URL, params=params, timeout=TIMEOUT)
        r.raise_for_status()
        contenido = r.json()
    except (requests.RequestException, ValueError) as e:
        raise ErrorProveedor("No se pudo consultar el servicio meteorológico.") from e

    actual = contenido.get("current")
    if not isinstance(actual, dict):
        raise ErrorProveedor("Respuesta meteorológica sin datos actuales.")

    return {
        "temperatura_c": actual.get("temperature_2m"),
        "precipitacion_mm": actual.get("precipitation"),
        "codigo_tiempo": actual.get("weather_code"),
        "instante": actual.get("time"),
    }


def obtener_lugares(lat: float, lon: float, tipo: str) -> list[dict]:
    """TODO(ALUMNADO).

    Consultar un radio urbano acotado de Overpass/OSM (2-3 km).
    Filtrar según tipo: cultural, gastronomica, naturaleza, familiar.
    Normalizar a [{nombre, categoria, lat, lon, fuente, ...}], máximo
    8-12 lugares. Gestionar nodos (lat/lon) y ways/relations (center).
    Nunca introducir valores libres del usuario en una consulta QL.
    """
    raise NotImplementedError("Implementa consulta de puntos de interés")


def cargar_fixture_lugares() -> list[dict]:
    """Utilidad entregada para simular Overpass durante pruebas sin Internet.

    Los lugares son FICTICIOS y deben identificarse como DEMO en la UI.
    """
    file_path = Path("/fixtures/puntos_demo.json")
    if not file_path.exists():
        file_path = Path(__file__).resolve().parents[2] / "fixtures/puntos_demo.json"
    return json.loads(file_path.read_text(encoding="utf-8"))["lugares"]
