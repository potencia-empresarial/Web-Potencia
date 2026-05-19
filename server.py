import os
import json
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import anthropic
from dotenv import dotenv_values

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

# === PANCAKE CRM — integración para persistencia de leads ===
# Endpoint confirmado (mayo 2026):
#   POST https://pos.pages.fm/api/v1/shops/{SHOP_ID}/crm/{TABLE_NAME}/records?api_key={KEY}
# Donde SHOP_ID = workspace ID que aparece en la URL del panel Pancake CRM (4851 para PotencIA).
PANCAKE_API_KEY = _get_env_var('PANCAKE_API_KEY')
PANCAKE_WORKSPACE_ID = _get_env_var('PANCAKE_WORKSPACE_ID', '4851')  # = SHOP_ID en la URL
PANCAKE_API_BASE = _get_env_var('PANCAKE_API_BASE', 'https://pos.pages.fm/api/v1')
# Nombre EXACTO de la tabla en el CRM (case-sensitive, se ve en CRM → Tablas).
# Defaults comunes: 'Contact', 'Customer', 'Lead'. Override con PANCAKE_TABLE_NAME en Render.
PANCAKE_TABLE_NAME = _get_env_var('PANCAKE_TABLE_NAME', 'Contact')

if PANCAKE_API_KEY:
    print(f'✅ PANCAKE_API_KEY cargada → shop {PANCAKE_WORKSPACE_ID}, tabla "{PANCAKE_TABLE_NAME}"')
else:
    print('⚠️  PANCAKE_API_KEY no configurada — los leads NO se enviarán a CRM (solo quedarán en logs)')

app = Flask(__name__, static_folder='.')
CORS(app, resources={r"/api/*": {"origins": "*"}})  # Permite llamadas desde cualquier frontend
client = anthropic.Anthropic(api_key=API_KEY) if API_KEY else None


def enviar_lead_a_pancake(datos, resultado):
    """
    Envía el lead capturado a Pancake CRM.
    Diseño defensivo: si falla, hace log pero NO interrumpe la respuesta al usuario.
    Timeout de 10 seg para no bloquear.

    Retorna: (ok: bool, mensaje: str)
    """
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

    # Payload Pancake CRM — usa PascalCase (convención de columnas en sus tablas custom).
    # Los campos extra que no existan en la tabla del CRM son ignorados por la API.
    # Si la tabla "Contact" tiene columnas con otros nombres, ajustar aquí.
    payload = {
        'Name': nombre_completo,
        'FirstName': primer_nombre,
        'LastName': apellido,
        'Email': datos.get('correo', ''),
        'Company': datos.get('empresa', ''),
        'Industry': datos.get('industria', ''),
        'Source': 'diagnostico-web-express',
        'Tags': ['lead-diagnostico-web', f'nivel-{nivel.lower().replace(" ", "-")}', f'score-{score}'],
        'Notes': notas,
        'Score': score,
        'Level': nivel,
        'Employees': datos.get('empleados', ''),
        'Revenue': datos.get('facturacion', ''),
        'Objective': datos.get('objetivo', ''),
        'Challenge': datos.get('desafio', ''),
    }

    # Endpoint confirmado: /shops/{SHOP_ID}/crm/{TABLE_NAME}/records?api_key=...
    url = f'{PANCAKE_API_BASE}/shops/{PANCAKE_WORKSPACE_ID}/crm/{PANCAKE_TABLE_NAME}/records?api_key={PANCAKE_API_KEY}'

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
        with urllib.request.urlopen(req, timeout=10) as resp:
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

    try:
        message = client.messages.create(
            model='claude-sonnet-4-6',
            max_tokens=2000,
            messages=[{'role': 'user', 'content': prompt}]
        )
        raw = message.content[0].text.strip()
        start = raw.find('{')
        end = raw.rfind('}') + 1
        resultado = json.loads(raw[start:end])

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

        # === ENVIAR A PANCAKE CRM (defensivo: si falla, NO interrumpe respuesta al user) ===
        try:
            crm_ok, crm_msg = enviar_lead_a_pancake(datos, resultado)
            print(f'🔗 Pancake CRM: {"✅" if crm_ok else "⚠️"} {crm_msg}', flush=True)
        except Exception as crm_err:
            # Cualquier error inesperado en la integración Pancake NO debe romper el diagnóstico
            print(f'⚠️  Excepción inesperada en integración Pancake (lead igual quedó en logs): {crm_err}', flush=True)

        return jsonify({'ok': True, 'resultado': resultado})
    except Exception as e:
        print(f'❌ ERROR en diagnostico para {datos.get("correo", "?")}: {e}', flush=True)
        return jsonify({'ok': False, 'error': str(e)}), 500


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 3000))
    print(f'✅ PotencIA Empresarial - Servidor en http://localhost:{port}')
    print(f'📊 Diagnóstico en http://localhost:{port}/diagnostico.html')
    app.run(host='0.0.0.0', port=port, debug=False)
