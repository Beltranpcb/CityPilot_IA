"""Tests propios de la rama B: prompt y orquestador (con mocks, sin red)."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import llm, orchestrator


def _contexto(lluvia_mm):
    return {
        "ciudad": "Valencia",
        "tipo_turismo": "cultural",
        "duracion_horas": 4,
        "preferencias": "con niños",
        "meteorologia": {"temperatura_c": 18.0, "precipitacion_mm": lluvia_mm},
        "lugares": [{"nombre": "Museo de Prueba", "categoria": "museo", "lat": 39.47, "lon": -0.38}],
    }


def test_prompt_con_lluvia_pide_interior():
    prompt = llm._construir_prompt(_contexto(2.5))
    assert "interior" in prompt.lower()
    assert "Museo de Prueba" in prompt


def test_prompt_sin_lluvia_no_menciona_lluvia_actual():
    prompt = llm._construir_prompt(_contexto(0.0))
    assert "Ahora mismo llueve" not in prompt


def test_ciudad_vacia_no_consume_apis(monkeypatch):
    def prohibido(*args, **kwargs):
        raise AssertionError("No debe llamarse con una entrada inválida")

    monkeypatch.setattr(orchestrator.api_clients, "geocodificar", prohibido)
    with pytest.raises(ValueError):
        orchestrator.procesar_solicitud("", "cultural", 4, "")


def _preparar_mocks(monkeypatch, lugares_ok=True):
    guardados = []
    monkeypatch.setattr(
        orchestrator.api_clients, "geocodificar",
        lambda c: {"ciudad": "Valencia", "pais": "España", "lat": 39.47, "lon": -0.38},
    )
    monkeypatch.setattr(
        orchestrator.api_clients, "obtener_meteorologia",
        lambda lat, lon: {"temperatura_c": 20.0, "precipitacion_mm": 0.0,
                          "codigo_tiempo": 1, "instante": "2026-11-06T12:00"},
    )
    if lugares_ok:
        monkeypatch.setattr(
            orchestrator.api_clients, "obtener_lugares",
            lambda lat, lon, tipo: [{"nombre": "Museo Real", "categoria": "museo",
                                     "lat": 39.47, "lon": -0.38,
                                     "fuente": "OpenStreetMap", "demo": False}],
        )
    else:
        def falla(lat, lon, tipo):
            raise RuntimeError("Overpass caído")
        monkeypatch.setattr(orchestrator.api_clients, "obtener_lugares", falla)
    monkeypatch.setattr(
        orchestrator.llm, "generar_itinerario",
        lambda ctx: ("Ruta de prueba", "prompt de prueba"),
    )

    def guardar(registro):
        guardados.append(registro)
        return 7

    monkeypatch.setattr(orchestrator.db, "guardar_solicitud", guardar)
    return guardados


def test_flujo_correcto_devuelve_contrato(monkeypatch):
    guardados = _preparar_mocks(monkeypatch)
    res = orchestrator.procesar_solicitud("valencia", "cultural", "4", "con niños")
    for clave in ("solicitud_id", "ciudad", "tipo_turismo", "meteorologia",
                  "lugares", "itinerario", "modo_demo"):
        assert clave in res
    assert res["solicitud_id"] == 7
    assert res["modo_demo"] is False
    assert guardados[0]["estado"] == "ok"


def test_si_falla_overpass_usa_fixture_marcado_demo(monkeypatch):
    _preparar_mocks(monkeypatch, lugares_ok=False)
    res = orchestrator.procesar_solicitud("Valencia", "cultural", 4)
    assert res["modo_demo"] is True
    assert all(l["demo"] for l in res["lugares"])