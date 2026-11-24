# 💱 Agente de conversión de divisas con Google ADK

Un agente de IA que convierte divisas usando **únicamente** los tipos de cambio de referencia oficiales del **Banco Central Europeo (BCE)**. Está construido con el [Agent Development Kit (ADK) 2.x](https://adk.dev/) de Google y Gemini.

Es un proyecto de aprendizaje pensado para desarrolladores hispanohablantes que empiezan con agentes de IA. El código es corto a propósito y cada decisión de diseño está explicada.

> 🇬🇧 **English speakers:** see the [English summary](#-english-summary) at the end.

---

## ¿Qué hace?

Le preguntas en lenguaje natural y responde en tu idioma:

> **Tú:** ¿Cuántos dólares eran 250 euros el día de Navidad de 2025?
>
> **Agente:** El BCE no publicó tipos de cambio el 25 de diciembre de 2025 por ser festivo, así que se usó el del día hábil anterior (24 de diciembre de 2025). 250 EUR = **294,68 USD** (tipo 1,1787). Fuente: tipos de referencia del BCE.
> *Solo de referencia: los tipos del BCE son informativos y no son los que ofrecen los bancos.*

El agente tiene dos herramientas (*tools*), que son funciones normales de Python:

| Herramienta | Qué hace |
|---|---|
| `get_today()` | Devuelve la fecha de hoy (UTC) y el día de la semana. |
| `convert_currency(amount, from_currency, to_currency, date)` | Pide el tipo de cambio del BCE a la API de Frankfurter, hace la multiplicación en código y devuelve el tipo, la fecha del tipo, el resultado y la fuente. Gestiona los errores 404 (no hay tipo) y 422 (petición inválida). |

---

## Por qué una sola fuente confiable

Un modelo de lenguaje **no sabe** el tipo de cambio de hoy. Si se lo preguntas sin darle datos, se lo inventa con total seguridad. Por eso este agente:

- Usa **una sola fuente oficial**: los tipos de referencia del BCE, que se publican cada día hábil hacia las 16:00 CET.
- Accede a ellos con la [API de Frankfurter v2](https://frankfurter.dev/), que es gratuita, sin API key y de código abierto, a través del endpoint **específico del proveedor BCE**:

  ```
  GET https://api.frankfurter.dev/v2/providers/ecb/rate/{base}/{quote}?date=YYYY-MM-DD
  ```

  Usar `/providers/ecb/` en lugar del endpoint general garantiza que los datos vienen **solo del BCE** y no de una mezcla de proveedores. Así cada respuesta se puede rastrear hasta su fuente.

---

## Las 3 lecciones

### 1. Una sola fuente confiable

El agente no puede "saber" datos que cambian cada día. Tiene que **consultarlos** con una herramienta, y las instrucciones le prohíben inventar tipos de cambio. Si la herramienta devuelve un error, el agente lo explica en vez de dar un número.

### 2. El código hace las cuentas, no el modelo

Los LLM se equivocan con la aritmética. En este agente, `convert_currency` hace la multiplicación en Python con `Decimal` (no `float`, para evitar errores de redondeo) y el modelo solo **comunica** el resultado. Las instrucciones dicen explícitamente: *"Never do arithmetic yourself."*

### 3. Dale la fecha de hoy

Un modelo no sabe qué día es: solo conoce su fecha de corte de entrenamiento. Si le preguntas *"¿cuánto era ayer?"*, necesita saber qué día es **hoy**. Para eso existe `get_today()`, y las instrucciones le dicen que la llame antes de calcular cualquier fecha relativa.

**Bonus: fines de semana y festivos.** El BCE no publica tipos en fines de semana ni en festivos de TARGET. En esos casos, Frankfurter devuelve el tipo del **día hábil anterior** sin dar ningún error. Por eso la herramienta compara la fecha pedida con la fecha del tipo (`rate_date_differs`) y añade una nota para que el agente se lo explique al usuario.

---

## Estructura del proyecto

```
currency-agent-adk/
├── currency_agent/
│   ├── __init__.py       # Hace de la carpeta un paquete Python e importa agent.py
│   ├── agent.py          # Herramientas, instrucciones y root_agent
│   └── .env.example      # Plantilla de configuración (cópiala a .env)
├── .gitignore
├── LICENSE
└── README.md
```

---

## Cómo ejecutarlo

### Requisitos

- **Python 3.11 o superior** (ADK 2.x lo requiere)
- **Google Cloud CLI** (`gcloud`)
- Un **proyecto de Google Cloud** con facturación activada

### 1. Autenticación con Application Default Credentials (sin API keys)

```bash
gcloud auth login
gcloud config set project TU_PROJECT_ID
gcloud auth application-default login
gcloud services enable aiplatform.googleapis.com
```

> 💡 En la pantalla de consentimiento de `application-default login`, marca **"Seleccionar todo"**. Si no aceptas el permiso de Google Cloud, el login falla.

### 2. Entorno virtual e instalación de ADK

```bash
git clone https://github.com/IsabelPalomar/currency-agent-adk.git
cd currency-agent-adk
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
```

ADK publica un **archivo de restricciones** (*constraints*) por cada versión de Python, con versiones de dependencias probadas juntas. Usa el que corresponda a tu versión (por ejemplo, `3.13`):

```bash
curl -fsSL -o constraints.txt https://raw.githubusercontent.com/google/adk-python/main/constraints-3.13.txt
pip install "google-adk>=2" -c constraints.txt
rm constraints.txt
```

### 3. Configuración

```bash
cp currency_agent/.env.example currency_agent/.env
```

Edita `currency_agent/.env` y pon tu project ID:

```dotenv
GOOGLE_GENAI_USE_ENTERPRISE=TRUE
GOOGLE_CLOUD_PROJECT=tu-project-id
GOOGLE_CLOUD_LOCATION=global
```

> `GOOGLE_GENAI_USE_ENTERPRISE` es el nombre nuevo de `GOOGLE_GENAI_USE_VERTEXAI`. Ambos hacen lo mismo.

### 4. Iniciar la interfaz web

Ejecútalo desde la carpeta **padre** de `currency_agent/`:

```bash
adk web --port 8000
```

Abre <http://127.0.0.1:8000>, elige **currency_agent** y prueba con:

- `¿Cuántos dólares son 100 euros?`
- `¿Y en yenes?`
- `Convierte 50 libras a francos suizos del viernes pasado`
- `¿Cuánto era 1 dólar en pesos mexicanos el 25 de diciembre de 2025?` (festivo)
- `Convierte 10 EUR a XYZ` (divisa inválida)

En el panel **Events** puedes hacer clic en cada llamada a una herramienta para ver los argumentos que envió Gemini y el JSON que devolvió.

> ⚠️ `adk web` es una herramienta de desarrollo y no está pensada para producción.

---

## ⚠️ Aviso importante

Los tipos de cambio de este agente son **solo de referencia**. Los tipos de referencia del BCE se publican con fines **informativos** y **no** son los tipos que ofrecen los bancos ni los que se aplican en transacciones. No uses este agente para tomar decisiones financieras.

---

## Licencia

[Apache 2.0](LICENSE)

Datos de tipos de cambio: [Banco Central Europeo](https://www.ecb.europa.eu/stats/policy_and_exchange_rates/euro_reference_exchange_rates/html/index.es.html), vía la [API de Frankfurter](https://frankfurter.dev/).

---

## 🇬🇧 English summary

A currency conversion agent built with **Google ADK 2.x** and Gemini that uses **only** the official **European Central Bank (ECB)** reference rates, fetched from the ECB-specific endpoint of the [Frankfurter API v2](https://frankfurter.dev/). It answers in the user's language.

**Three lessons:**
1. **Single trusted source.** LLMs don't know today's exchange rates, so the agent must fetch them with a tool and is told never to invent them.
2. **Code does the math.** The tool multiplies with Python's `Decimal`; the model only reports the result.
3. **Give it today's date.** Models don't know what day it is, so `get_today()` lets the agent resolve relative dates like "yesterday".

On weekends and TARGET holidays the ECB publishes no rates, and Frankfurter silently returns the previous business day's rate. The tool detects this and the agent explains it.

**Quick start:** authenticate with `gcloud auth application-default login`, enable `aiplatform.googleapis.com`, create a venv, install `google-adk` with the official constraints file, copy `currency_agent/.env.example` to `.env` with your project ID, and run `adk web` from the repo root.

**Disclaimer:** rates are for reference only. ECB reference rates are published for information purposes and are not transaction rates.

Licensed under [Apache 2.0](LICENSE).
