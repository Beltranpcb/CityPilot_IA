"""Punto ÚNICO de integración para web y API JSON."""
import time

from app import api_clients, db, llm

TIPOS_VALIDOS = {"cultural", "gastronomica", "naturaleza", "familiar"}
DURACIONES_VALIDAS = {2, 4, 6}


class ProveedorError(RuntimeError):
    """Fallo de un servicio externo o de guardado (las rutas responden 502)."""


def _validar(ciudad, tipo_turismo, duracion_horas, preferencias):
    ciudad = (ciudad or "").strip()
    tipo = (tipo_turismo or "").strip().lower()
    preferencias = (preferencias or "").strip()

    if not ciudad:
        raise ValueError("La ciudad es obligatoria.")
    if len(ciudad) > 80:
        raise ValueError("La ciudad no puede superar los 80 caracteres.")
    if tipo not in TIPOS_VALIDOS:
        raise ValueError("Tipo de turismo no válido.")
    try:
        duracion = int(duracion_horas)
    except (TypeError, ValueError):
        raise ValueError("La duración debe ser 2, 4 o 6 horas.") from None
    if duracion not in DURACIONES_VALIDAS:
        raise ValueError("La duración debe ser 2, 4 o 6 horas.")
    if len(preferencias) > 200:
        raise ValueError("Las preferencias no pueden superar los 200 caracteres.")
    return ciudad, tipo, duracion, preferencias


def _ms(inicio: float) -> int:
    return int((time.perf_counter() - inicio) * 1000)


def procesar_solicitud(ciudad: str, tipo_turismo: str, duracion_horas: int, preferencias: str = "") -> dict:
    """Valida, consulta APIs, genera el itinerario, guarda en BD y devuelve el contrato."""
    # 1) Validación: si falla, ValueError y NO se consulta ningún servicio externo.
    ciudad, tipo, duracion, preferencias = _validar(
        ciudad, tipo_turismo, duracion_horas, preferencias
    )

    inicio = time.perf_counter()
    registro = {
        "ciudad": ciudad,
        "pais": None,
        "tipo_turismo": tipo,
        "duracion_horas": duracion,
        "preferencias": preferencias,
        "latitud": None,
        "longitud": None,
        "meteorologia": {},
        "lugares": [],
        "prompt_usado": None,
        "itinerario": None,
        "estado": "pendiente",
        "duracion_ms": None,
        "error_resumido": None,
        "modo_demo": False,
        "modo_modelo": llm.LLM_MODE,
    }

    try:
        # 2) Geocodificación y clima
        geo = api_clients.geocodificar(ciudad)
        registro.update(
            ciudad=geo["ciudad"],
            pais=geo["pais"],
            latitud=geo["lat"],
            longitud=geo["lon"],
        )
        meteo = api_clients.obtener_meteorologia(geo["lat"], geo["lon"])
        registro["meteorologia"] = meteo

        # 3) Lugares reales; si Overpass falla, fixture marcado como demo
        try:
            lugares = api_clients.obtener_lugares(geo["lat"], geo["lon"], tipo)
            modo_demo = False
        except Exception:
            lugares = [
                {**lugar, "demo": True}
                for lugar in api_clients.cargar_fixture_lugares()
            ]
            modo_demo = True
        registro["lugares"] = lugares
        registro["modo_demo"] = modo_demo

        # 4) Itinerario (sin lugares no se inventa una ruta)
        if lugares:
            contexto = {
                "ciudad": geo["ciudad"],
                "tipo_turismo": tipo,
                "duracion_horas": duracion,
                "preferencias": preferencias,
                "meteorologia": meteo,
                "lugares": lugares,
            }
            itinerario, prompt = llm.generar_itinerario(contexto)
        else:
            itinerario = (
                "No hay lugares reales disponibles para esta búsqueda, "
                "así que no se puede proponer una ruta."
            )
            prompt = "[SIN LLAMADA AL MODELO: no hay lugares]"

        registro.update(itinerario=itinerario, prompt_usado=prompt, estado="ok")

    except Exception as exc:
        # Se guarda la fila con el error (resumido, sin claves ni trazas)
        registro["estado"] = "error"
        registro["error_resumido"] = f"{type(exc).__name__}: {exc}"[:300]
        registro["duracion_ms"] = _ms(inicio)
        try:
            db.guardar_solicitud(registro)
        except Exception:
            pass  # no tapar el error original
        raise ProveedorError(f"No se pudo completar la solicitud: {exc}") from exc

    # 5) Guardar el caso correcto
    registro["duracion_ms"] = _ms(inicio)
    try:
        solicitud_id = db.guardar_solicitud(registro)
    except Exception as exc:
        raise ProveedorError("La ruta se generó, pero no se pudo guardar en la base de datos.") from exc

    # 6) Contrato común para HTML y API JSON
    return {
        "solicitud_id": solicitud_id,
        "ciudad": registro["ciudad"],
        "tipo_turismo": tipo,
        "duracion_horas": duracion,
        "meteorologia": registro["meteorologia"],
        "lugares": registro["lugares"],
        "itinerario": registro["itinerario"],
        "modo_demo": registro["modo_demo"],
        "modo_modelo": registro["modo_modelo"],
    }