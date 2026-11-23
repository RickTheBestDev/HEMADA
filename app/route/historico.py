from fastapi import APIRouter
from app.database import SessionLocal
from app.model.documento import Documento

historico = APIRouter()

@historico.get("/historico/")
def listar_historico():
    banco = SessionLocal()
    try:
        documentos_salvos = banco.query(Documento).all() 
        return documentos_salvos
    finally:
        banco.close()

@historico.get("/limpar-historico/")
def apagar_historico():
    banco = SessionLocal()
    try:
        banco.query(Documento).delete()
        banco.commit()
        return {"status": "Histórico apagado"}
    finally:
        banco.close()