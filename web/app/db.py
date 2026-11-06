"""Acceso a PostgreSQL. Conexión mínima dada; funciones de negocio pendientes."""
import os
import json
from sqlalchemy import create_engine, text

DATABASE_URL = os.environ.get("DATABASE_URL", "")
engine = create_engine(DATABASE_URL, pool_pre_ping=True) if DATABASE_URL else None


def ping_db():
    if engine is None:
        raise RuntimeError("Falta DATABASE_URL")
    with engine.connect() as conn:
        return conn.execute(text("SELECT 1")).scalar_one()

def guardar_solicitud(registro: dict) -> int:
    consulta = text("""
        INSERT INTO solicitudes (
            ciudad, pais, tipo_turismo, duracion_horas, preferencias,
            latitud, longitud, meteorologia, lugares, prompt_usado,
            itinerario, estado, duracion_ms, error_resumido,
            modo_demo, modo_modelo
        ) VALUES (
            :ciudad, :pais, :tipo_turismo, :duracion_horas, :preferencias,
            :latitud, :longitud,
            CAST(:meteorologia AS jsonb),
            CAST(:lugares AS jsonb),
            :prompt_usado, :itinerario, :estado, :duracion_ms,
            :error_resumido, :modo_demo, :modo_modelo
        )
        RETURNING id
    """)

    valores = {
        "ciudad": registro["ciudad"],
        "pais": registro.get("pais"),
        "tipo_turismo": registro["tipo_turismo"],
        "duracion_horas": registro["duracion_horas"],
        "preferencias": registro.get("preferencias", ""),
        "latitud": registro.get("latitud"),
        "longitud": registro.get("longitud"),
        "meteorologia": json.dumps(registro.get("meteorologia", {})),
        "lugares": json.dumps(registro.get("lugares", [])),
        "prompt_usado": registro.get("prompt_usado"),
        "itinerario": registro.get("itinerario"),
        "estado": registro.get("estado", "pendiente"),
        "duracion_ms": registro.get("duracion_ms"),
        "error_resumido": registro.get("error_resumido"),
        "modo_demo": registro.get("modo_demo", False),
        "modo_modelo": registro.get("modo_modelo"),
    }

    if engine is None:
        raise RuntimeError("Falta DATABASE_URL")

    with engine.begin() as conn:
        resultado = conn.execute(consulta, valores)
        return resultado.scalar_one()
#Elle renvoie au maximum huit demandes, des plus récentes aux plus anciennes, sans inclure les prompts
def obtener_estadisticas() -> dict:
    """TODO(ALUMNADO): total, agrupación por ciudad/tipo y nº errores."""
    if engine is None:
        raise RuntimeError("Falta DATABASE_URL")
    if limite<0:
        raise ValueError("El límite debe ser un número positivo")
    consulta = text("""
        Select id,fehca,cuidad, tipo_turism, estado, duracion_ms
        from solicitudes
        order by fecha DESC id DESC
        limit :limite
    """)
    with engine.connect() as conn:
        filas = conn.execute(
            consulta,
            {"limite": limite}
        ).mappings().all()

    return [dict(fila) for fila in filas]

def obtener_ultimas_solicitudes(limite: int = 8) -> list[dict]:
    """TODO(ALUMNADO): últimas solicitudes sin mostrar claves ni secretos."""
    if engine is None:
        raise RuntimeError("Falta DATABASE_URL")

    if limite < 0:
        raise ValueError("El límite no puede ser negativo")

    consulta = text("""
        SELECT id, fecha, ciudad, tipo_turismo, estado, duracion_ms
        FROM solicitudes
        ORDER BY fecha DESC, id DESC
        LIMIT :limite
    """)

    with engine.connect() as conn:
        filas = conn.execute(
            consulta,
            {"limite": limite}
        ).mappings().all()
    return [dict(fila) for fila in filas]