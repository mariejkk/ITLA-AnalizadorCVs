"""
Pipeline Inteligente de Procesamiento de CVs
Backend FastAPI + Azure AI Document Intelligence + Groq API
"""

import os
from dotenv import load_dotenv
load_dotenv()
import json
import uuid
import re
from pathlib import Path
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, UploadFile, File, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

# Azure SDK imports
from azure.ai.formrecognizer import DocumentAnalysisClient
from azure.core.credentials import AzureKeyCredential
from azure.storage.blob import BlobServiceClient
from openai import OpenAI

# Config (desde variables de entorno) 
AZURE_FORM_ENDPOINT   = os.getenv("AZURE_FORM_ENDPOINT")
AZURE_FORM_KEY        = os.getenv("AZURE_FORM_KEY")
GROQ_API_KEY          = os.getenv("GROQ_API_KEY")
AZURE_STORAGE_CONN    = os.getenv("AZURE_STORAGE_CONN", "")
AZURE_CONTAINER       = os.getenv("AZURE_CONTAINER", "cvs")

# FastAPI App 
app = FastAPI(title="CV Pipeline API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Clients 
def get_doc_client():
    if not AZURE_FORM_ENDPOINT or not AZURE_FORM_KEY:
        raise HTTPException(500, "Azure Document Intelligence no configurado")
    return DocumentAnalysisClient(
        endpoint=AZURE_FORM_ENDPOINT,
        credential=AzureKeyCredential(AZURE_FORM_KEY)
    )

def get_openai_client():
    if not GROQ_API_KEY:
        raise HTTPException(500, "Groq API no configurado")
    return OpenAI(
        api_key=GROQ_API_KEY,
        base_url="https://api.groq.com/openai/v1"
    )

def get_blob_client():
    if not AZURE_STORAGE_CONN:
        return None
    return BlobServiceClient.from_connection_string(AZURE_STORAGE_CONN)

# Models
class VacanteReq(BaseModel):
    titulo: str
    requisitos: str

class CVResult(BaseModel):
    candidato_id: str
    nombre: str
    email: Optional[str]
    telefono: Optional[str]
    experiencia_years: Optional[int]
    habilidades: list[str]
    educacion: str
    idiomas: list[str]
    match_score: int
    clasificacion: str
    resumen_ejecutivo: str
    blob_url: Optional[str]
    procesado_en: str

# Helpers 
def extract_text_from_result(result) -> str:
    """Concatena todo el texto extraído por Document Intelligence."""
    lines = []
    for page in result.pages:
        for line in page.lines:
            lines.append(line.content)
    return "\n".join(lines)

def parse_cv_with_gpt(raw_text: str, client) -> dict:
    resp = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": "Eres un extractor de información de CVs. Devuelve SOLO JSON válido con estos campos: nombre (str), email (str|null), telefono (str|null), experiencia_years (int|null), habilidades (list[str]), educacion (str), idiomas (list[str]). Sin markdown, sin explicaciones."},
            {"role": "user", "content": f"CV:\n{raw_text[:6000]}"}
        ],
        temperature=0
    )
    text = resp.choices[0].message.content.strip()
    text = re.sub(r"```(?:json)?", "", text).strip().rstrip("`")
    text = text.replace('\n', ' ').replace('\r', ' ')
    text = ''.join(char for char in text if ord(char) >= 32)
    text = text[text.find('{'):text.rfind('}')+1]
    return json.loads(text)

def score_and_classify(cv_data: dict, raw_text: str, vacante: VacanteReq, client) -> dict:
    resp = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": "Eres un reclutador senior experto. Devuelve SOLO JSON válido con: match_score (int 0-100), clasificacion (str: 'candidato_prioritario' si score>=75, 'candidato_en_espera' si 50<=score<75, 'descartado' si score<50), resumen_ejecutivo (str)."},
            {"role": "user", "content": f"VACANTE: {vacante.titulo}\nREQUISITOS:\n{vacante.requisitos}\n\nPERFIL CANDIDATO:\n{json.dumps(cv_data, ensure_ascii=False)}\n\nTEXTO CV:\n{raw_text[:3000]}"}
        ],
        temperature=0.3
    )
    text = resp.choices[0].message.content.strip()
    text = re.sub(r"```(?:json)?", "", text).strip().rstrip("`")
    text = text.replace('\n', ' ').replace('\r', ' ')
    text = ''.join(char for char in text if ord(char) >= 32)
    text = text[text.find('{'):text.rfind('}')+1]
    return json.loads(text)

def upload_blob(file_bytes: bytes, filename: str, vacante_id: str) -> Optional[str]:
    client = get_blob_client()
    if not client:
        return None
    blob_name = f"cv_{Path(filename).stem}_{vacante_id}.pdf"
    container = client.get_container_client(AZURE_CONTAINER)
    try:
        container.create_container()
    except Exception:
        pass
    blob = container.get_blob_client(blob_name)
    blob.upload_blob(file_bytes, overwrite=True)
    return blob.url

# Endpoints 
@app.get("/")
async def root():
    # Servir el frontend index.html
    index_path = Path(__file__).parent / "index.html"
    if index_path.exists():
        with open(index_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return {
        "message": "CV Pipeline API funcionando",
        "status": "online",
        "endpoints": ["/health", "/api/process-cv", "/api/process-batch"]
    }

@app.get("/health")
def health():
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}

@app.post("/api/process-cv", response_model=CVResult)
async def process_cv(
    file: UploadFile = File(...),
    vacante_titulo: str = Form(...),
    vacante_requisitos: str = Form(...)
):
    # 1. Leer archivo
    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(400, "Archivo demasiado grande (máx 10 MB)")

    vacante = VacanteReq(titulo=vacante_titulo, requisitos=vacante_requisitos)
    candidato_id = str(uuid.uuid4())[:8].upper()

    # 2. Extraer texto con Document Intelligence
    try:
        doc_client = get_doc_client()
        poller = doc_client.begin_analyze_document(
            "prebuilt-document",
            document=content,
        )
        result = poller.result()
        raw_text = extract_text_from_result(result)
    except Exception as e:
        raise HTTPException(500, f"Error en Document Intelligence: {str(e)}")

    if not raw_text.strip():
        raise HTTPException(422, "No se pudo extraer texto del documento")

    # 3. Parsear CV con Groq
    try:
        openai_client = get_openai_client()
        cv_data = parse_cv_with_gpt(raw_text, openai_client)
    except Exception as e:
        raise HTTPException(500, f"Error al parsear CV: {str(e)}")

    # 4. Scoring y resumen
    try:
        evaluation = score_and_classify(cv_data, raw_text, vacante, openai_client)
    except Exception as e:
        raise HTTPException(500, f"Error al evaluar CV: {str(e)}")

    # 5. Subir a Blob Storage
    blob_url = None
    try:
        blob_url = upload_blob(content, file.filename or "cv.pdf", candidato_id)
    except Exception:
        pass

    return CVResult(
        candidato_id=candidato_id,
        nombre=cv_data.get("nombre", "Desconocido"),
        email=cv_data.get("email"),
        telefono=cv_data.get("telefono"),
        experiencia_years=cv_data.get("experiencia_years"),
        habilidades=cv_data.get("habilidades", []),
        educacion=cv_data.get("educacion", ""),
        idiomas=cv_data.get("idiomas", []),
        match_score=evaluation.get("match_score", 0),
        clasificacion=evaluation.get("clasificacion", "descartado"),
        resumen_ejecutivo=evaluation.get("resumen_ejecutivo", ""),
        blob_url=blob_url,
        procesado_en=datetime.utcnow().isoformat()
    )

@app.post("/api/process-batch")
async def process_batch(
    files: list[UploadFile] = File(...),
    vacante_titulo: str = Form(...),
    vacante_requisitos: str = Form(...)
):
    """Procesa múltiples CVs en lote."""
    results = []
    errors = []
    
    for f in files:
        try:
            content = await f.read()
            vacante = VacanteReq(titulo=vacante_titulo, requisitos=vacante_requisitos)
            candidato_id = str(uuid.uuid4())[:8].upper()
            
            doc_client = get_doc_client()
            poller = doc_client.begin_analyze_document(
                "prebuilt-document",
                document=content,
            )
            result = poller.result()
            raw_text = extract_text_from_result(result)
            
            openai_client = get_openai_client()
            cv_data = parse_cv_with_gpt(raw_text, openai_client)
            evaluation = score_and_classify(cv_data, raw_text, vacante, openai_client)

            results.append({
                "archivo": f.filename,
                "candidato_id": candidato_id,
                "nombre": cv_data.get("nombre", "Desconocido"),
                "match_score": evaluation.get("match_score", 0),
                "clasificacion": evaluation.get("clasificacion", "descartado"),
            })
        except Exception as e:
            errors.append({"archivo": f.filename, "error": str(e)})

    return {
        "total": len(files),
        "exitosos": len(results),
        "fallidos": len(errors),
        "resultados": sorted(results, key=lambda x: x["match_score"], reverse=True),
        "errores": errors
    }

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)