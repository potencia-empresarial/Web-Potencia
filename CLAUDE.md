# Instrucciones para Claude — potencia-web

Este es el **repo de la web pública** de PotencIA Empresarial. Contiene `index.html` (sitio principal) y `diagnostico.html` (Diagnóstico Web Express + backend Flask).

Forma parte de un sistema mayor de 4 repos (`potencia-sop`, `potencia-docs`, `potencia-skills`, `potencia-agentes`). Todos viven en `../` dentro de la carpeta raíz `Potencia-Empresarial/`.

## Antes de actuar

Lee primero estos documentos del sistema:

1. `../potencia-sop/POE-SOP-01-manual-operacion.md` — manual operativo del sistema completo
2. `../potencia-docs/bloque-1-fundacion/DOC-M-01-brand-book.md` — identidad visual y verbal (NO negociable)
3. `../potencia-docs/bloque-1-fundacion/DOC-R-01-icp-detallado.md` — ICP de PotencIA (audiencia objetivo)
4. `../potencia-docs/bloque-2-comercial/DOC-P-04-procedimiento-diagnostico.md` — proceso del diagnóstico profundo (referencia para entender cómo se relaciona con el web express)

## Reglas de oro para este repo

- **Paleta NO negociable**: Navy `#0D1B2A` (primario), Teal `#004F5F` (secundario), Yellow `#FECD1A` (acento). Texto sobre Yellow siempre Navy.
- **Tipografía**: Poppins Bold (títulos), Helvetica Light (cuerpo).
- **Voz**: directa, concreta, técnica cuando aporta. Ver Brand Book §3.
- **Clichés vetados**: ver Brand Book §6.1. NUNCA usar "Potencia tu negocio", "Nueva era", "Transformación digital", "Lleva al siguiente nivel", etc.
- **Cualquier cambio visual o de copy debe pasar por el Brand Book primero.**

## Stack

- **Frontend**: HTML5 + Tailwind CSS (CDN) + Chart.js + html2pdf.js
- **Backend**: Python 3.9 + Flask
- **IA**: Anthropic Claude API (`claude-sonnet-4-6`)
- **Hosting web estático**: Webcake.io (pendiente migración para `diagnostico.html`)
- **Backend hosting**: pendiente (opciones: Render, Railway, PythonAnywhere)
- **Dominio**: potenciaempresarial.site

## Productos en este repo

| Archivo | Producto | Documentación oficial |
|---|---|---|
| `index.html` | Sitio web público | (futuro DOC-P-XX) |
| `diagnostico.html` + `server.py` | Diagnóstico Web Express | `../potencia-docs/bloque-5-marketing/DOC-T-09-diagnostico-web-express.md` |

## Trazabilidad

Cualquier cambio sustancial debe:
1. Versionarse en Git (`feat:`, `fix:`, `docs:`, `style:`)
2. Si afecta producto, actualizar la doc oficial referenciada arriba
3. Si rompe convención del Brand Book, justificar y esperar aprobación de Hanssen
