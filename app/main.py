import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

from app.database import Base, engine
from app.model.documento import Documento
from app.route.upload import upload
from app.route.historico import historico
from app.route.chat import chat_router

# Carrega variáveis de ambiente do arquivo .env
load_dotenv()

# Garante que as tabelas sejam criadas no banco SQLite
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="HEMADA - Inteligência Documental",
    description="Sistema web de extração e análise de documentos PDF com IA",
    version="1.0.0"
)

# Endpoint simples para verificação de funcionamento da API
@app.get("/health")
def verificar_status():
    return {"status": "ok", "projeto": "HEMADA"}

# Registra os roteadores da aplicação
app.include_router(upload)
app.include_router(historico)
app.include_router(chat_router)

# Caminho absoluto para a pasta 'static' (garante carregamento em qualquer diretório)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC_DIR = os.path.join(BASE_DIR, "static")

if os.path.exists(STATIC_DIR):
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
