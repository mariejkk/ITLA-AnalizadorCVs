# 📄 Analizador Inteligente de CVs

Pipeline automatizado de reclutamiento que extrae, evalúa y clasifica candidatos desde PDFs usando Inteligencia Artificial.

---

## ¿Qué hace?

Sube uno o varios CVs en PDF, define los requisitos de tu vacante y el sistema genera automáticamente un ranking de candidatos con puntaje de compatibilidad.

---

## 🛠️ Stack

- **Backend:** Python + FastAPI
- **Frontend:** HTML/CSS (integrado)
- **Extracción de texto:** Azure Document Intelligence
- **Análisis con IA:** Groq API — LLaMA 3.3 70B
- **Almacenamiento:** Azure Blob Storage
  
---

## ⚙️ Instalación Local

### 1. Clona el repositorio
```bash
git clone https://github.com/tu-usuario/ProyectoAnalizadorCVs.git
cd ProyectoAnalizadorCVs
```

### 2. Instala dependencias
```bash
pip install -r requirements.txt
```

### 3. Configura las variables de entorno
Crea un archivo `.env` basado en `.env.example`:
```bash
cp .env.example .env
```

Llena tus credenciales en `.env`:
```
AZURE_FORM_ENDPOINT=https://tu-recurso.cognitiveservices.azure.com/
AZURE_FORM_KEY=tu_clave_azure
GROQ_API_KEY=tu_clave_groq
AZURE_STORAGE_CONN=tu_connection_string
AZURE_CONTAINER=cvs
```

### 4. Corre el servidor
```bash
uvicorn main:app --reload
```

Abre tu navegador en `http://localhost:8000`

---

## 📡 Endpoints

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/` | Interfaz web |
| GET | `/health` | Estado del servidor |
| POST | `/api/process-cv` | Analiza un CV individual |
| POST | `/api/process-batch` | Analiza múltiples CVs en lote |

---

## 📋 Requisitos previos

- Python 3.10+
- Cuenta en [Azure](https://azure.microsoft.com/) con Document Intelligence y Blob Storage activos
- API Key de [Groq](https://console.groq.com/)
  
---

## 📁 Estructura del proyecto

```
ProyectoAnalizadorCVs/
├── main.py           # Backend FastAPI
├── index.html        # Frontend
├── requirements.txt  # Dependencias
├── .env.example      # Plantilla de variables de entorno
└── .gitignore
```
