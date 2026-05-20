import os
import re
import json
import traceback
import threading
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import anthropic
from dotenv import dotenv_values


def extraer_json_robusto(raw):
    """
    Extrae JSON de la respuesta de Claude manejando todos los formatos típicos:
    - JSON puro
    - JSON dentro de ```json ... ```
    - JSON con texto explicativo antes/después
    Levanta ValueError descriptivo si no encuentra JSON parseable.
    """
    if not raw or not raw.strip():
        raise ValueError('Respuesta de Claude vacía')

    raw = raw.strip()

    # Caso 1: markdown fence ```json ... ``` o ``` ... ```
    fence = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', raw, re.DOTALL)
    if fence:
        return json.loads(fence.group(1))

    # Caso 2: buscar primer { y último } balanceados
    start = raw.find('{')
    end = raw.rfind('}') + 1
    if start == -1 or end <= start:
        raise ValueError(f'No se detectó JSON en la respuesta. Inicio: {raw[:300]!r}')

    return json.loads(raw[start:end])

# === API Key resolution (producción primero, .env como fallback dev) ===
def _get_env_var(key, fallback=''):
    """Lee primero de os.environ (producción/Render), luego de .env (desarrollo local)."""
    val = os.environ.get(key, '').strip()
    if val:
        return val
    env_path = Path(__file__).parent / '.env'
    if env_path.exists():
        _env = dotenv_values(dotenv_path=env_path)
        return (_env.get(key) or fallback).strip()
    return fallback

# === ANTHROPIC (Claude API) ===
API_KEY = _get_env_var('ANTHROPIC_API_KEY')
if API_KEY:
    print(f'✅ ANTHROPIC_API_KEY cargada (longitud: {len(API_KEY)} chars, prefijo: {API_KEY[:12]}...)')
else:
    print('❌ ANTHROPIC_API_KEY no encontrada — el endpoint /api/diagnostico fallará')

# === PANCAKE CRM v2 — integración para persistencia de leads ===
# KILL-SWITCH: PANCAKE_ENABLED='true' activa la integración. Default 'false' por seguridad.
# Mientras no confirmemos el método de auth correcto de Pancake CRM v2 (api_key vs access_token
# vs header), mantenemos la integración desactivada para no degradar el diagnóstico.
# Los leads quedan en logs estructurados de Render aunque Pancake esté off.
PANCAKE_ENABLED = _get_env_var('PANCAKE_ENABLED', 'false').lower() == 'true'
PANCAKE_API_KEY = _get_env_var('PANCAKE_API_KEY')
PANCAKE_WORKSPACE_ID = _get_env_var('PANCAKE_WORKSPACE_ID', '4961')
PANCAKE_TABLE_NAME = _get_env_var('PANCAKE_TABLE_NAME', 'lead')
PANCAKE_API_URL = _get_env_var(
    'PANCAKE_API_URL',
    f'https://crm.pancake.vn/api/v2/workspace/{PANCAKE_WORKSPACE_ID}/{PANCAKE_TABLE_NAME}'
)
# Timeout corto: si Pancake no responde en X seg, abortamos y NO bloqueamos al user.
PANCAKE_TIMEOUT_SEG = int(_get_env_var('PANCAKE_TIMEOUT_SEG', '5'))

if PANCAKE_ENABLED and PANCAKE_API_KEY:
    print(f'✅ PANCAKE habilitado → POST {PANCAKE_API_URL} (timeout {PANCAKE_TIMEOUT_SEG}s)')
elif PANCAKE_ENABLED and not PANCAKE_API_KEY:
    print('⚠️  PANCAKE_ENABLED=true pero PANCAKE_API_KEY vacía — no se enviarán leads')
else:
    print('🔌 PANCAKE desactivado (PANCAKE_ENABLED!=true). Leads solo en logs.')

app = Flask(__name__, static_folder='.')
# CORS explícito: el frontend (potenciaempresarial.site) llama directo a este backend
# (potencia-api.onrender.com) — es cross-origin. Declaramos methods y headers permitidos
# para que el preflight OPTIONS pase sin problemas.
CORS(app, resources={r"/api/*": {
    "origins": "*",
    "methods": ["GET", "POST", "OPTIONS"],
    "allow_headers": ["Content-Type"],
}})
client = anthropic.Anthropic(api_key=API_KEY) if API_KEY else None


def enviar_lead_a_pancake(datos, resultado):
    """
    Envía el lead capturado a Pancake CRM.
    Diseño defensivo: si falla, hace log pero NO interrumpe la respuesta al usuario.
    Timeout de 10 seg para no bloquear.

    Retorna: (ok: bool, mensaje: str)
    """
    if not PANCAKE_ENABLED:
        return False, 'PANCAKE_ENABLED=false (kill-switch activo)'
    if not PANCAKE_API_KEY:
        return False, 'PANCAKE_API_KEY no configurada'

    # === Payload mapeado: campos del diagnóstico → campos del CRM ===
    nombre_completo = (datos.get('nombre') or '').strip()
    partes = nombre_completo.split(' ', 1)
    primer_nombre = partes[0] if partes else ''
    apellido = partes[1] if len(partes) > 1 else ''

    score = resultado.get('score', 0)
    nivel = resultado.get('nivel', 'Sin clasificar')

    # Notas estructuradas del diagnóstico (para que el equipo comercial tenga contexto)
    notas = f"""DIAGNÓSTICO WEB EXPRESS — {datetime.now().strftime('%Y-%m-%d %H:%M')}

📊 SCORE: {score}/100 — {nivel}

🏢 EMPRESA: {datos.get('empresa', 'N/A')}
📍 Industria: {datos.get('industria', 'N/A')}
👥 Empleados: {datos.get('empleados', 'N/A')}
💰 Facturación: {datos.get('facturacion', 'N/A')}

🎯 OBJETIVO: {datos.get('objetivo', 'N/A')}
⚠️ DESAFÍO: {datos.get('desafio', 'N/A')}

🌐 PRESENCIA DIGITAL:
  - Web: {datos.get('tienePaginaWeb', 'N/A')}
  - Redes: {', '.join(datos.get('redesSociales', [])) or 'Ninguna'}
  - CRM: {datos.get('gestionLeads', 'N/A')}

⚙️ AUTOMATIZACIÓN:
  - Tiene: {datos.get('tieneAutomatizaciones', 'N/A')}
  - Horas manuales: {datos.get('horasManuales', 'N/A')}

📣 MARKETING:
  - Publicidad: {datos.get('tienePublicidad', 'N/A')}
  - Presupuesto: {datos.get('presupuestoMarketing', 'N/A')}
  - Canal ventas: {datos.get('canalVentas', 'N/A')}

🎁 TOP OPORTUNIDAD SUGERIDA:
{resultado.get('oportunidades', [{}])[0].get('titulo', 'N/A') if resultado.get('oportunidades') else 'N/A'}
"""

    # Payload Pancake CRM v2 — versión MÍNIMA (debug incremental).
    # Histórico de errores:
    # - PascalCase ('Name'): rechazado, exige snake_case
    # - snake_case completo con tags/score/level: rechazado por "multi_value invalid"
    #   (probablemente Pancake llama a algún campo array internamente "multi_value"
    #   con validación estricta de tipo)
    # Estrategia: empezar con campos universales (name, email, phone, notes) y agregar
    # campos custom uno a uno cuando se confirme cuál tabla del CRM los acepta.
    # TODA la info del diagnóstico va dentro de 'notes' como texto plano (no se pierde nada).
    payload = {
        'name': nombre_completo or '(Sin nombre)',  # obligatorio
        'email': datos.get('correo', ''),
        'phone': datos.get('telefono', ''),  # opcional, casi nunca lo capturamos hoy
        'notes': notas,  # contiene TODA la info estructurada del diagnóstico
    }

    # URL completa configurable. La api_key se añade aquí para no logguearla.
    url = f'{PANCAKE_API_URL}?api_key={PANCAKE_API_KEY}'

    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode('utf-8'),
            headers={
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                'User-Agent': 'PotencIA-Diagnostico/1.0',
            },
            method='POST',
        )
        with urllib.request.urlopen(req, timeout=PANCAKE_TIMEOUT_SEG) as resp:
            response_data = resp.read().decode('utf-8')
            print(f'✅ Lead enviado a Pancake CRM (HTTP {resp.status}): {response_data[:200]}', flush=True)
            return True, f'OK (HTTP {resp.status})'
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', errors='replace')[:500]
        print(f'❌ Pancake CRM rechazó el lead (HTTP {e.code}): {body}', flush=True)
        return False, f'HTTP {e.code}: {body}'
    except urllib.error.URLError as e:
        print(f'❌ No se pudo conectar a Pancake CRM: {e.reason}', flush=True)
        return False, f'URLError: {e.reason}'
    except Exception as e:
        print(f'❌ Error inesperado enviando a Pancake CRM: {e}', flush=True)
        return False, f'Exception: {e}'


@app.route('/health')
def health():
    """Endpoint de salud — Render lo usa para verificar que la app está viva."""
    return jsonify({'status': 'ok', 'service': 'PotencIA API'})


@app.route('/')
def index():
    return send_from_directory('.', 'index.html')


@app.route('/<path:filename>')
def static_files(filename):
    return send_from_directory('.', filename)


@app.route('/api/diagnostico', methods=['POST'])
def diagnostico():
    if client is None:
        return jsonify({
            'ok': False,
            'error': 'Configuración del servidor incompleta — falta ANTHROPIC_API_KEY. Contacta al administrador.'
        }), 500

    datos = request.get_json()

    redes = ', '.join(datos.get('redesSociales', [])) or 'Ninguna'
    herramientas = ', '.join(datos.get('herramientas', [])) or 'Ninguna'
    procesos = ', '.join(datos.get('procesosManuales', [])) or 'No especificado'

    prompt = f"""Eres un consultor senior de transformación digital e inteligencia artificial de PotencIA Empresarial.
Tu tarea es analizar el diagnóstico de una empresa y generar un reporte ejecutivo profesional en formato JSON estricto.

DATOS DEL DIAGNÓSTICO:
- Empresa: {datos.get('empresa')}
- Industria: {datos.get('industria')}
- Empleados: {datos.get('empleados')}
- Facturación mensual aprox: {datos.get('facturacion')}
- Representante: {datos.get('nombre')}
- Correo: {datos.get('correo')}

PRESENCIA DIGITAL:
- Tiene página web: {datos.get('tienePaginaWeb')}
- Redes sociales activas: {redes}
- Herramientas de gestión: {herramientas}
- Gestión de leads: {datos.get('gestionLeads')}

OPERACIONES:
- Horas semanales en tareas manuales: {datos.get('horasManuales')}
- Procesos más manuales: {procesos}
- Tiene automatizaciones: {datos.get('tieneAutomatizaciones')}
- Descripción automatizaciones: {datos.get('descripcionAutomatizaciones') or 'Ninguna'}

MARKETING Y VENTAS:
- Invierte en publicidad digital: {datos.get('tienePublicidad')}
- Presupuesto mensual marketing: {datos.get('presupuestoMarketing')}
- Cómo mide resultados: {datos.get('mideResultados')}
- Canal principal de ventas: {datos.get('canalVentas')}

METAS:
- Objetivo principal: {datos.get('objetivo')}
- Mayor desafío: {datos.get('desafio')}

Genera el análisis ÚNICAMENTE como JSON puro (sin markdown, sin explicaciones, solo el objeto JSON):

{{
  "score": <número entre 0 y 100>,
  "nivel": "<uno de: Inicial | En Desarrollo | Intermedio | Avanzado | Líder Digital>",
  "descripcionNivel": "<2 oraciones sobre el estado actual de la empresa>",
  "scoreDetalle": {{
    "presenciaDigital": <0-25>,
    "automatizacion": <0-25>,
    "datosDecisiones": <0-25>,
    "marketingIA": <0-25>
  }},
  "fortalezas": [
    "<fortaleza 1 concreta>",
    "<fortaleza 2 concreta>",
    "<fortaleza 3 concreta>"
  ],
  "oportunidades": [
    {{
      "titulo": "<nombre de la oportunidad>",
      "descripcion": "<qué se implementa y cómo>",
      "impacto": "<Alto | Medio>",
      "plazo": "<30 días | 60 días | 90 días>",
      "roiEstimado": "<porcentaje o descripción cuantificable del retorno>",
      "herramientasSugeridas": ["<herramienta 1>", "<herramienta 2>"]
    }},
    {{
      "titulo": "<nombre>",
      "descripcion": "<descripción>",
      "impacto": "<Alto | Medio>",
      "plazo": "<30 días | 60 días | 90 días>",
      "roiEstimado": "<ROI>",
      "herramientasSugeridas": ["<herramienta>"]
    }},
    {{
      "titulo": "<nombre>",
      "descripcion": "<descripción>",
      "impacto": "<Alto | Medio>",
      "plazo": "<30 días | 60 días | 90 días>",
      "roiEstimado": "<ROI>",
      "herramientasSugeridas": ["<herramienta>"]
    }}
  ],
  "planAccion": {{
    "mes1": {{
      "titulo": "Fundación Digital",
      "acciones": ["<acción 1>", "<acción 2>", "<acción 3>"]
    }},
    "mes2": {{
      "titulo": "Implementación IA",
      "acciones": ["<acción 1>", "<acción 2>", "<acción 3>"]
    }},
    "mes3": {{
      "titulo": "Optimización y Escala",
      "acciones": ["<acción 1>", "<acción 2>", "<acción 3>"]
    }}
  }},
  "mensajeFinal": "<2-3 oraciones motivadoras y específicas para esta empresa>"
}}"""

    inicio = datetime.now()
    raw = ''  # para tener referencia si falla el parsing

    try:
        message = client.messages.create(
            model='claude-sonnet-4-6',
            max_tokens=2000,
            messages=[{'role': 'user', 'content': prompt}]
        )
        raw = message.content[0].text.strip()
        resultado = extraer_json_robusto(raw)

        # === LOG ESTRUCTURADO — cada diagnóstico queda registrado en Render Logs ===
        duracion = (datetime.now() - inicio).total_seconds()
        log_lead = {
            'timestamp': inicio.isoformat(),
            'tipo': 'DIAGNOSTICO_NUEVO',
            'lead': {
                'nombre': datos.get('nombre'),
                'correo': datos.get('correo'),
                'empresa': datos.get('empresa'),
                'industria': datos.get('industria'),
                'empleados': datos.get('empleados'),
                'facturacion': datos.get('facturacion'),
            },
            'resultado': {
                'score': resultado.get('score'),
                'nivel': resultado.get('nivel'),
            },
            'metrica_tecnica': {
                'duracion_seg': round(duracion, 2),
                'tokens_input': message.usage.input_tokens,
                'tokens_output': message.usage.output_tokens,
                'costo_usd_aprox': round((message.usage.input_tokens * 3 + message.usage.output_tokens * 15) / 1_000_000, 4),
            }
        }
        print(f'📊 LEAD CAPTURADO: {json.dumps(log_lead, ensure_ascii=False)}', flush=True)

        # === ENVIAR A PANCAKE CRM EN BACKGROUND (POE-N-01 §2: no bloquear ruta crítica) ===
        # Guarda dura: si el kill-switch está off, NO lanzamos thread (cero overhead).
        # El lead ya quedó en logs estructurados de Render (LEAD CAPTURADO arriba).
        if PANCAKE_ENABLED and PANCAKE_API_KEY:
            def _enviar_pancake_background(datos_snapshot, resultado_snapshot):
                try:
                    crm_ok, crm_msg = enviar_lead_a_pancake(datos_snapshot, resultado_snapshot)
                    print(f'🔗 Pancake CRM (async): {"✅" if crm_ok else "⚠️"} {crm_msg}', flush=True)
                except Exception as crm_err:
                    print(f'⚠️  Excepción en integración Pancake async (lead en logs): {crm_err}', flush=True)

            threading.Thread(
                target=_enviar_pancake_background,
                args=(datos, resultado),
                daemon=True,
                name='pancake-crm-async',
            ).start()

        return jsonify({'ok': True, 'resultado': resultado})

    # === MANEJO DE ERRORES GRANULAR (POE-N-01 §5: logging proactivo) ===
    # Cada tipo de error registra contexto completo en logs y devuelve un
    # mensaje user-friendly al frontend (no jerga técnica).
    except anthropic.APIStatusError as e:
        # Errores HTTP del API de Anthropic (rate limit, content policy, etc.)
        print(f'❌ ANTHROPIC API ERROR para {datos.get("correo", "?")}: '
              f'status={e.status_code} message={e.message}', flush=True)
        msg_user = ('El servicio de IA está temporalmente saturado o rechazó la solicitud. '
                    'Intenta de nuevo en 1 minuto.')
        return jsonify({'ok': False, 'error': msg_user, 'codigo': 'anthropic_api_error'}), 503

    except anthropic.APIConnectionError as e:
        # Problema de conexión con Anthropic
        print(f'❌ ANTHROPIC CONNECTION ERROR para {datos.get("correo", "?")}: {e}', flush=True)
        msg_user = 'No pudimos conectar con el servicio de IA. Intenta de nuevo en unos segundos.'
        return jsonify({'ok': False, 'error': msg_user, 'codigo': 'anthropic_conn_error'}), 503

    except json.JSONDecodeError as e:
        # Claude devolvió algo que no es JSON parseable
        print(f'❌ JSON PARSE ERROR para {datos.get("correo", "?")}: {e}', flush=True)
        print(f'   RAW (primeros 500 chars): {raw[:500]!r}', flush=True)
        msg_user = ('Hubo un problema procesando la respuesta de IA. '
                    'Intenta de nuevo (suele resolverse al reintentar).')
        return jsonify({'ok': False, 'error': msg_user, 'codigo': 'json_parse_error'}), 500

    except ValueError as e:
        # extraer_json_robusto levantó ValueError (no encontró JSON)
        print(f'❌ NO JSON IN CLAUDE RESPONSE para {datos.get("correo", "?")}: {e}', flush=True)
        print(f'   RAW (primeros 500 chars): {raw[:500]!r}', flush=True)
        msg_user = 'La respuesta de IA llegó incompleta. Intenta de nuevo.'
        return jsonify({'ok': False, 'error': msg_user, 'codigo': 'incomplete_response'}), 500

    except Exception as e:
        # Cualquier otro error — log COMPLETO con traceback para debug post-mortem
        print(f'❌ ERROR INESPERADO para {datos.get("correo", "?")}: '
              f'{type(e).__name__}: {e}', flush=True)
        print(f'   Traceback completo:\n{traceback.format_exc()}', flush=True)
        msg_user = ('Hubo un error inesperado generando el diagnóstico. '
                    'Por favor intenta de nuevo. Si persiste, contáctanos.')
        return jsonify({'ok': False, 'error': msg_user, 'codigo': 'unexpected_error'}), 500


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 3000))
    print(f'✅ PotencIA Empresarial - Servidor en http://localhost:{port}')
    print(f'📊 Diagnóstico en http://localhost:{port}/diagnostico.html')
    app.run(host='0.0.0.0', port=port, debug=False)
