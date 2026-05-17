import os
import json
from pathlib import Path
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import anthropic
from dotenv import dotenv_values

env_path = Path(__file__).parent / '.env'
_env = dotenv_values(dotenv_path=env_path)
API_KEY = _env.get('ANTHROPIC_API_KEY') or os.environ.get('ANTHROPIC_API_KEY', '')

app = Flask(__name__, static_folder='.')
CORS(app, resources={r"/api/*": {"origins": "*"}})  # Permite llamadas desde cualquier frontend
client = anthropic.Anthropic(api_key=API_KEY)


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
        return jsonify({'ok': True, 'resultado': resultado})
    except Exception as e:
        print(f'Error: {e}')
        return jsonify({'ok': False, 'error': str(e)}), 500


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 3000))
    print(f'✅ PotencIA Empresarial - Servidor en http://localhost:{port}')
    print(f'📊 Diagnóstico en http://localhost:{port}/diagnostico.html')
    app.run(host='0.0.0.0', port=port, debug=False)
