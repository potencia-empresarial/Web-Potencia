require('dotenv').config();
const express = require('express');
const Anthropic = require('@anthropic-ai/sdk');
const path = require('path');

const app = express();
const PORT = process.env.PORT || 3000;

app.use(express.json());
app.use(express.static(path.join(__dirname)));

const client = new Anthropic({ apiKey: process.env.ANTHROPIC_API_KEY });

app.post('/api/diagnostico', async (req, res) => {
  const datos = req.body;

  const prompt = `Eres un consultor senior de transformación digital e inteligencia artificial de PotencIA Empresarial.
Tu tarea es analizar el diagnóstico de una empresa y generar un reporte ejecutivo profesional en formato JSON estricto.

DATOS DEL DIAGNÓSTICO:
- Empresa: ${datos.empresa}
- Industria: ${datos.industria}
- Empleados: ${datos.empleados}
- Facturación mensual aprox: ${datos.facturacion}
- Representante: ${datos.nombre}
- Correo: ${datos.correo}

PRESENCIA DIGITAL:
- Tiene página web: ${datos.tienePaginaWeb}
- Redes sociales activas: ${datos.redesSociales?.join(', ') || 'Ninguna'}
- Herramientas de gestión: ${datos.herramientas?.join(', ') || 'Ninguna'}
- Gestión de leads: ${datos.gestionLeads}

OPERACIONES:
- Horas semanales en tareas manuales: ${datos.horasManuales}
- Procesos más manuales: ${datos.procesosManuales?.join(', ') || 'No especificado'}
- Tiene automatizaciones: ${datos.tieneAutomatizaciones}
- Descripción automatizaciones: ${datos.descripcionAutomatizaciones || 'Ninguna'}

MARKETING Y VENTAS:
- Invierte en publicidad digital: ${datos.tienePublicidad}
- Presupuesto mensual marketing: ${datos.presupuestoMarketing}
- Cómo mide resultados: ${datos.mideResultados}
- Canal principal de ventas: ${datos.canalVentas}

METAS:
- Objetivo principal: ${datos.objetivo}
- Mayor desafío: ${datos.desafio}

Genera el análisis en el siguiente formato JSON (sin markdown, solo JSON puro):

{
  "score": <número entre 0 y 100>,
  "nivel": "<uno de: Inicial | En Desarrollo | Intermedio | Avanzado | Líder Digital>",
  "descripcionNivel": "<2 oraciones sobre el estado actual de la empresa>",
  "scoreDetalle": {
    "presenciaDigital": <0-25>,
    "automatizacion": <0-25>,
    "datosDecisiones": <0-25>,
    "marketingIA": <0-25>
  },
  "fortalezas": [
    "<fortaleza 1 concreta>",
    "<fortaleza 2 concreta>",
    "<fortaleza 3 concreta>"
  ],
  "oportunidades": [
    {
      "titulo": "<nombre de la oportunidad>",
      "descripcion": "<qué se implementa y cómo>",
      "impacto": "<Alto | Medio>",
      "plazo": "<30 días | 60 días | 90 días>",
      "roiEstimado": "<porcentaje o descripción cuantificable del retorno>",
      "herramientasSugeridas": ["<herramienta 1>", "<herramienta 2>"]
    },
    {
      "titulo": "<nombre>",
      "descripcion": "<descripción>",
      "impacto": "<Alto | Medio>",
      "plazo": "<30 días | 60 días | 90 días>",
      "roiEstimado": "<ROI>",
      "herramientasSugeridas": ["<herramienta>"]
    },
    {
      "titulo": "<nombre>",
      "descripcion": "<descripción>",
      "impacto": "<Alto | Medio>",
      "plazo": "<30 días | 60 días | 90 días>",
      "roiEstimado": "<ROI>",
      "herramientasSugeridas": ["<herramienta>"]
    }
  ],
  "planAccion": {
    "mes1": {
      "titulo": "Fundación Digital",
      "acciones": ["<acción 1>", "<acción 2>", "<acción 3>"]
    },
    "mes2": {
      "titulo": "Implementación IA",
      "acciones": ["<acción 1>", "<acción 2>", "<acción 3>"]
    },
    "mes3": {
      "titulo": "Optimización y Escala",
      "acciones": ["<acción 1>", "<acción 2>", "<acción 3>"]
    }
  },
  "mensajeFinal": "<2-3 oraciones motivadoras y específicas para esta empresa, mencionando su industria y objetivo principal>"
}`;

  try {
    const message = await client.messages.create({
      model: 'claude-sonnet-4-6',
      max_tokens: 2000,
      messages: [{ role: 'user', content: prompt }],
    });

    const rawText = message.content[0].text.trim();
    const jsonStart = rawText.indexOf('{');
    const jsonEnd = rawText.lastIndexOf('}') + 1;
    const jsonStr = rawText.slice(jsonStart, jsonEnd);
    const resultado = JSON.parse(jsonStr);

    res.json({ ok: true, resultado });
  } catch (err) {
    console.error('Error Claude API:', err.message);
    res.status(500).json({ ok: false, error: 'Error al procesar el diagnóstico. Intenta de nuevo.' });
  }
});

app.listen(PORT, () => {
  console.log(`✅ PotencIA Empresarial - Servidor corriendo en http://localhost:${PORT}`);
  console.log(`📊 Diagnóstico disponible en http://localhost:${PORT}/diagnostico.html`);
});
