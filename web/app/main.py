"""Rutas web y API de CityPilot IA."""
from io import BytesIO

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import requests
from flask import Flask, jsonify, render_template, request, send_file

from app.db import (
    obtener_estadisticas,
    obtener_ultimas_solicitudes,
    ping_db,
)
from app.orchestrator import (
    DURACIONES_VALIDAS,
    TIPOS_VALIDOS,
    procesar_solicitud,
)


def _leer_solicitud(datos: dict) -> dict:
    """Comprueba los campos recibidos antes de llamar al orquestador."""
    ciudad = datos.get("ciudad", "")
    tipo_turismo = datos.get("tipo_turismo", "")
    preferencias = datos.get("preferencias", "")
    duracion = datos.get("duracion_horas", "")

    if not isinstance(ciudad, str) or not ciudad.strip():
        raise ValueError("La ciudad es obligatoria.")
    if len(ciudad.strip()) > 80:
        raise ValueError("La ciudad no puede superar 80 caracteres.")
    if not isinstance(tipo_turismo, str) or tipo_turismo not in TIPOS_VALIDOS:
        raise ValueError("El tipo de turismo no es válido.")
    if not isinstance(preferencias, str) or len(preferencias) > 200:
        raise ValueError("Las preferencias no pueden superar 200 caracteres.")
    if isinstance(duracion, bool):
        raise ValueError("La duración debe ser 2, 4 o 6 horas.")

    try:
        duracion_horas = int(duracion)
    except (TypeError, ValueError):
        raise ValueError("La duración debe ser 2, 4 o 6 horas.") from None

    if duracion_horas not in DURACIONES_VALIDAS:
        raise ValueError("La duración debe ser 2, 4 o 6 horas.")

    return {
        "ciudad": ciudad.strip(),
        "tipo_turismo": tipo_turismo,
        "duracion_horas": duracion_horas,
        "preferencias": preferencias.strip(),
    }


def create_app():
    app = Flask(__name__)

    @app.get("/")
    def inicio():
        return render_template("index.html")

    @app.get("/api/health")
    def health():
        try:
            ping_db()
            return jsonify(servicio="citypilot", estado="ok", db="ok")
        except Exception:
            return jsonify(servicio="citypilot", estado="degradado", db="error"), 503

    @app.post("/planificar")
    def planificar_html():
        try:
            datos = _leer_solicitud(request.form)
            resultado = procesar_solicitud(**datos)
        except ValueError as error:
            return render_template("resultado.html", error=str(error)), 400
        except (requests.RequestException, RuntimeError) as error:
            return render_template("resultado.html", error=str(error)), 502

        return render_template("resultado.html", **resultado)

    @app.post("/api/planificar")
    def planificar_api():
        datos = request.get_json(silent=True)
        if not isinstance(datos, dict):
            return jsonify(error="Se esperaba un objeto JSON."), 400

        try:
            campos = _leer_solicitud(datos)
            resultado = procesar_solicitud(**campos)
        except ValueError as error:
            return jsonify(error=str(error)), 400
        except (requests.RequestException, RuntimeError) as error:
            return jsonify(error=str(error)), 502

        return jsonify(resultado), 200

    @app.get("/api/estadisticas")
    def estadisticas_api():
        return jsonify(obtener_estadisticas())

    @app.get("/analitica")
    def analitica():
        estadisticas = obtener_estadisticas()
        ultimas = obtener_ultimas_solicitudes(8)
        return render_template(
            "analitica.html",
            estadisticas=estadisticas,
            ultimas=ultimas,
        )

    @app.get("/analitica/grafico.png")
    def grafico():
        ciudades = obtener_estadisticas()["por_ciudad"]
        figura, eje = plt.subplots(figsize=(8, 4))

        if ciudades:
            nombres = [fila["ciudad"] for fila in ciudades]
            cantidades = [fila["cantidad"] for fila in ciudades]
            eje.bar(nombres, cantidades)
            eje.set_title("Solicitudes por ciudad")
            eje.set_ylabel("Número de solicitudes")
            eje.tick_params(axis="x", labelrotation=30)
        else:
            eje.text(0.5, 0.5, "Aún no hay solicitudes", ha="center", va="center")
            eje.set_axis_off()

        imagen = BytesIO()
        figura.tight_layout()
        figura.savefig(imagen, format="png")
        plt.close(figura)
        imagen.seek(0)
        return send_file(imagen, mimetype="image/png")

    return app


app = create_app()
