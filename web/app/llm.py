"""Adaptador Cohere. El PROMPT lo redacta el alumnado."""
import os
import requests

LLM_MODE = os.getenv("LLM_MODE", "mock").lower()
COHERE_MODEL = os.getenv("COHERE_MODEL", "command-r7b-12-2024")
COHERE_URL = "https://api.cohere.com/v2/chat"


def _construir_prompt(contexto: dict) -> str:
    """Prompt v1. Se separa de la llamada HTTP para poder testearlo."""
    ciudad = contexto.get("ciudad", "la ciudad")
    tipo = contexto.get("tipo_turismo", "libre")
    horas = contexto.get("duracion_horas", 4)
    preferencias = (contexto.get("preferencias") or "").strip() or "ninguna"
    meteo = contexto.get("meteorologia") or {}
    lugares = contexto.get("lugares") or []

    temp = meteo.get("temperatura_c")
    lluvia = meteo.get("precipitacion_mm")
    temp_txt = f"{temp} °C" if temp is not None else "no disponible"

    if lluvia is None:
        clima_txt = "La precipitación actual no está disponible; no asumas que hace buen tiempo."
    elif lluvia > 0:
        clima_txt = (
            f"Ahora mismo llueve ({lluvia} mm). Prioriza paradas de interior "
            "y explica que lo haces por la lluvia."
        )
    else:
        clima_txt = "Ahora no llueve: puedes incluir paradas al aire libre."

    if lugares:
        lineas_lugares = "\n".join(
            f"- {l.get('nombre', 'Sin nombre')} "
            f"(categoría: {l.get('categoria', 'n/d')}; "
            f"lat {l.get('lat')}, lon {l.get('lon')})"
            for l in lugares
        )
    else:
        lineas_lugares = "(no hay lugares disponibles)"

    aviso_demo = ""
    if any(l.get("demo") for l in lugares):
        aviso_demo = (
            "\nAVISO: algunos lugares son datos de demostración ficticios. "
            "Indícalo explícitamente en tu respuesta.\n"
        )

    return f"""Eres un planificador de rutas turísticas urbanas. Respondes siempre en castellano.

DATOS VERIFICABLES (única información que puedes usar):
- Ciudad: {ciudad}
- Tipo de turismo: {tipo}
- Duración disponible: {horas} horas
- Preferencias del visitante: {preferencias}
- Temperatura actual: {temp_txt}
- Tiempo: {clima_txt}

LUGARES DISPONIBLES (procedentes de OpenStreetMap):
{lineas_lugares}
{aviso_demo}
TAREA:
Propón una ruta de 3 a 5 paradas, en orden de visita, elegidas SOLO de la lista de lugares disponibles.
Para cada parada, explica en una o dos frases por qué encaja con el tipo de turismo, las preferencias y el tiempo.
Ajusta el número de paradas a la duración: con 2 horas, menos paradas; con 6 horas, más.

RESTRICCIONES (obligatorias):
- No menciones ningún lugar que no esté en la lista.
- No inventes horarios de apertura, precios, eventos ni tiempos de desplazamiento.
- No afirmes que un sitio está abierto: los horarios no están verificados.
- Si hay menos de 3 lugares o no hay ninguno, dilo claramente y propón solo los que existan, sin rellenar con otros.
- Termina con una nota breve recordando que los horarios no están verificados.
"""


def _llamar_cohere(prompt: str, api_key: str) -> str:
    """Llama a Cohere Chat v2 y devuelve el texto. Nunca incluye la clave en los errores."""
    cabeceras = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    cuerpo = {
        "model": COHERE_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
    }
    try:
        resp = requests.post(COHERE_URL, headers=cabeceras, json=cuerpo, timeout=30)
    except requests.Timeout:
        raise RuntimeError("Cohere no respondió a tiempo (timeout).") from None
    except requests.RequestException:
        raise RuntimeError("No se pudo conectar con Cohere.") from None

    if resp.status_code == 401:
        raise RuntimeError("Cohere rechazó la clave (401). Revisa COHERE_API_KEY en .env.")
    if resp.status_code == 429:
        raise RuntimeError("Cohere ha alcanzado el límite de peticiones (429). Prueba en unos minutos.")
    if resp.status_code >= 400:
        raise RuntimeError(f"Cohere devolvió un error HTTP {resp.status_code}.")

    try:
        datos = resp.json()
    except ValueError:
        raise RuntimeError("Cohere devolvió una respuesta que no es JSON.") from None

    partes = (datos.get("message") or {}).get("content") or []
    texto = "".join(
        p.get("text", "") for p in partes if isinstance(p, dict)
    ).strip()
    if not texto:
        raise RuntimeError("Cohere devolvió una respuesta vacía.")
    return texto


def generar_itinerario(contexto: dict) -> tuple[str, str]:
    """Devuelve (texto_itinerario, prompt_usado).

    `contexto` incluye: ciudad, tipo_turismo, duracion_horas,
    preferencias, meteorologia y lista de lugares REALES de la fuente.
    """
    if LLM_MODE == "mock":
        return _simulador(contexto), "[SIMULADOR: sin llamada a modelo]"

    if LLM_MODE != "cohere":
        raise ValueError("LLM_MODE debe ser 'mock' o 'cohere'")

    api_key = os.getenv("COHERE_API_KEY", "")
    if not api_key:
        raise RuntimeError("Falta COHERE_API_KEY (pedirla al docente)")

    prompt = _construir_prompt(contexto)
    texto = _llamar_cohere(prompt, api_key)
    return texto, prompt


def _simulador(contexto: dict) -> str:
    """Salida no generativa para pruebas y para cuando no hay credenciales."""
    lugares = contexto.get("lugares") or []
    ciudad = contexto.get("ciudad", "la ciudad")
    tipo = contexto.get("tipo_turismo", "libre")
    nombres = [x.get("nombre", "Lugar sin nombre") for x in lugares[:4]]
    visitas = "\n".join(f"{i}. {nombre}" for i, nombre in enumerate(nombres, 1))
    if not visitas:
        visitas = "No hay lugares verificados disponibles."
    return f"[MODO SIMULACIÓN - NO ES IA]\nPlan {tipo} en {ciudad}:\n{visitas}"