"""Clientes HTTP de datos públicos. Se entregan los contratos, NO la solución."""
import json
import os
from pathlib import Path
import requests

GEO_URL = os.getenv("OPEN_METEO_GEO_URL", "https://geocoding-api.open-meteo.com/v1/search")
METEO_URL = os.getenv("OPEN_METEO_WEATHER_URL", "https://api.open-meteo.com/v1/forecast")
OVERPASS_URL = os.getenv("OVERPASS_URL", "https://overpass-api.de/api/interpreter")

TIMEOUT = 8
HEADERS = {
    "User-Agent": "CityPilotIA/1.0 (taller educativo; contacto: misandser@gmail.com)",
    "Accept": "*/*",
}


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

ETIQUETAS_POR_TIPO = {
    "cultural": [
        ("tourism", "museum|attraction|gallery"),
        ("historic", "monument|castle|memorial"),
    ],
    "gastronomica": [
        ("amenity", "restaurant|cafe|food_court"),
    ],
    "naturaleza": [
        ("leisure", "park|garden"),
    ],
    "familiar": [
        ("tourism", "attraction|zoo"),
        ("leisure", "park|playground"),
    ],
}
MAX_LUGARES = 12
RADIO_M = 2500

def obtener_lugares(lat: float, lon: float, tipo: str) -> list[dict]:
    """Coordenadas + tipo -> lista normalizada de lugares reales de OSM.

    Un solo intento. Lanza ErrorProveedor si Overpass falla o no responde.
    Devuelve [] si no hay lugares con nombre.
    """
    if tipo not in ETIQUETAS_POR_TIPO:
        raise ValueError(f"Tipo de turismo no permitido: {tipo!r}")

    lat = float(lat)
    lon = float(lon)

    filtros = ""
    for clave, valores in ETIQUETAS_POR_TIPO[tipo]:
        filtros += f'  nwr(around:{RADIO_M},{lat},{lon})["{clave}"~"^({valores})$"]["name"];\n'

    consulta = f"[out:json][timeout:25];\n(\n{filtros});\nout center 60;"

    try:
        r = requests.post(OVERPASS_URL, data={"data": consulta}, headers=HEADERS, timeout=30)
        r.raise_for_status()
        contenido = r.json()
    except (requests.RequestException, ValueError) as e:
        raise ErrorProveedor("No se pudo consultar OpenStreetMap (Overpass).") from e

    lugares = []
    vistos = set()
    for el in contenido.get("elements", []):
        tags = el.get("tags") or {}
        nombre = (tags.get("name") or "").strip()
        if not nombre or nombre.lower() in vistos:
            continue

        if el.get("type") == "node":
            punto_lat, punto_lon = el.get("lat"), el.get("lon")
        else:
            centro = el.get("center") or {}
            punto_lat, punto_lon = centro.get("lat"), centro.get("lon")
        if punto_lat is None or punto_lon is None:
            continue

        categoria = (
            tags.get("tourism") or tags.get("historic")
            or tags.get("amenity") or tags.get("leisure") or tipo
        )
        vistos.add(nombre.lower())
        lugares.append({
            "nombre": nombre,
            "categoria": categoria,
            "lat": float(punto_lat),
            "lon": float(punto_lon),
            "fuente": "OpenStreetMap",
            "demo": False,
        })
        if len(lugares) >= MAX_LUGARES:
            break

    return lugares


def cargar_fixture_lugares() -> list[dict]:
    """Utilidad entregada para simular Overpass durante pruebas sin Internet.

    Los lugares son FICTICIOS y deben identificarse como DEMO en la UI.
    """
    file_path = Path("/fixtures/puntos_demo.json")
    if not file_path.exists():
        file_path = Path(__file__).resolve().parents[2] / "fixtures/puntos_demo.json"
    return json.loads(file_path.read_text(encoding="utf-8"))["lugares"]
