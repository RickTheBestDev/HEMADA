# Arquivo: app/route/chat.py
"""
Módulo do Assistente de IA do HEMADA.
Recebe uma pergunta do usuário vinculada a um documento já analisado,
envia o contexto à API da Groq e retorna a resposta em linguagem natural.

Correções aplicadas (Etapa 3 — validação):
- Texto do documento truncado a 6.000 caracteres para respeitar o TPM da Groq.
- Timeout de 30s configurado na requisição HTTP.
- Tratamento individual dos códigos de erro da Groq (401, 403, 404, 429, 500/503).
- Tratamento explícito de erros de rede (ConnectionError, Timeout).
- Modelo lido do .env (GROQ_MODEL) com fallback para openai/gpt-oss-20b.
- Nenhuma chave ou credencial é exposta nas mensagens de erro.
"""

import os
import re
import time
import requests
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.database import SessionLocal
from app.model.documento import Documento

chat_router = APIRouter()

# Limite conservador de caracteres do contexto enviado ao chat (~1.500 tokens).
# Auxilia a manter a requisição dentro de patamares razoáveis de consumo por minuto (TPM),
# sem garantir isenção de rate limit caso a conta possua cotas restritas ou requisições concorrentes.
LIMITE_CONTEXTO_CHAT = 6000

# Modelo padrão oficial recomendado pela Groq (após descontinuação de modelos anteriores em 2026)
MODELO_PADRAO_CHAT = "openai/gpt-oss-20b"

# Tempo máximo de espera pela resposta da Groq
TIMEOUT_REQUISICAO = 30


class PerguntaChat(BaseModel):
    """Dados obrigatórios que o front-end deve enviar para o chat."""
    documento_id: int
    pergunta: str


def truncar_contexto(texto: str, limite: int = LIMITE_CONTEXTO_CHAT) -> str:
    """
    Trunca o texto do documento para o limite de caracteres configurado,
    preservando palavras completas. Acrescenta aviso quando o texto é cortado.
    """
    if len(texto) <= limite:
        return texto
    # Corta no último espaço antes do limite para não quebrar palavras
    trecho = texto[:limite]
    ultimo_espaco = trecho.rfind(" ")
    if ultimo_espaco > limite * 0.8:
        trecho = trecho[:ultimo_espaco]
    return trecho + "\n\n[Texto truncado — documento extenso. Apenas as primeiras seções foram consideradas.]"


def tratar_erro_groq_chat(resposta: requests.Response) -> None:
    """
    Converte os códigos de erro HTTP da Groq em mensagens claras e seguras,
    sem expor chaves de API ou informações internas do servidor.
    """
    status = resposta.status_code

    if status == 401:
        raise HTTPException(
            status_code=401,
            detail="Falha de autenticação na API da Groq (Erro 401). A chave de API configurada é inválida ou foi revogada."
        )
    if status == 403:
        raise HTTPException(
            status_code=403,
            detail="Acesso negado pela API da Groq (Erro 403). Verifique as permissões da sua conta Groq."
        )
    if status == 404:
        raise HTTPException(
            status_code=404,
            detail="O modelo de IA configurado não foi encontrado na Groq (Erro 404). Verifique a variável GROQ_MODEL no arquivo .env."
        )
    if status == 429:
        # Tenta extrair o tempo sugerido pela Groq na mensagem de erro
        tempo_sugerido = "30 segundos"
        try:
            dados = resposta.json()
            mensagem = str(dados.get("error", {}).get("message", ""))
            match = re.search(r"try again in ([0-9\.]+s)", mensagem, re.IGNORECASE)
            if match:
                tempo_sugerido = match.group(1)
        except Exception:
            pass
        raise HTTPException(
            status_code=429,
            detail=f"Limite de requisições da Groq atingido (Erro 429). Aguarde aproximadamente {tempo_sugerido} e tente novamente."
        )
    if status in (500, 503):
        raise HTTPException(
            status_code=503,
            detail=f"Os servidores da Groq estão temporariamente indisponíveis (Erro {status}). Tente novamente em alguns instantes."
        )

    # Para outros códigos, extrai mensagem sem vazar credenciais
    mensagem_segura = ""
    try:
        dados = resposta.json()
        bruto = str(dados.get("error", {}).get("message", ""))
        # Remove qualquer fragmento de chave (gsk_...)
        mensagem_segura = re.split(r"gsk_", bruto)[0].strip()
    except Exception:
        pass

    detalhe = f"A API da Groq retornou o código de erro {status}."
    if mensagem_segura:
        detalhe += f" Detalhe: {mensagem_segura}"

    raise HTTPException(status_code=502, detail=detalhe)


@chat_router.post("/chat/")
def fazer_pergunta(dados: PerguntaChat):
    """
    Recebe uma pergunta do usuário vinculada a um documento já analisado,
    busca o texto no banco SQLite, envia o contexto à Groq e retorna a resposta.
    """
    # 1. Carrega a chave da API do ambiente
    chave_api = os.getenv("API_KEY")
    if not chave_api:
        raise HTTPException(
            status_code=500,
            detail="Chave de API da Groq não configurada no servidor. Verifique o arquivo .env."
        )

    modelo = os.getenv("GROQ_MODEL") or MODELO_PADRAO_CHAT

    # 2. Busca o documento no banco de dados
    banco = SessionLocal()
    try:
        documento = banco.query(Documento).filter(Documento.id == dados.documento_id).first()
    finally:
        banco.close()

    if not documento:
        raise HTTPException(
            status_code=404,
            detail=f"Documento com ID {dados.documento_id} não encontrado no banco de dados."
        )

    if not documento.texto_extraido:
        raise HTTPException(
            status_code=422,
            detail="O documento selecionado não possui texto extraído disponível para consulta."
        )

    # 3. Trunca o texto para um volume conservador de caracteres (~1.500 tokens), reduzindo o consumo de TPM
    contexto = truncar_contexto(documento.texto_extraido, LIMITE_CONTEXTO_CHAT)

    # 4. Monta o prompt com ancoragem factual no documento
    prompt = (
        f"Você é o assistente de análise documental do HEMADA.\n"
        f"Utilize o texto abaixo como base factual prioritária para responder à pergunta.\n"
        f"Caso o documento não contenha elementos suficientes para responder, indique isso de forma clara.\n\n"
        f"DOCUMENTO: {documento.nome_arquivo}\n"
        f"---\n{contexto}\n---\n\n"
        f"PERGUNTA DO USUÁRIO: {dados.pergunta}\n\n"
        f"Responda de forma objetiva, profissional e em português."
    )

    payload = {
        "model": modelo,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3
    }

    cabecalhos = {
        "Authorization": f"Bearer {chave_api}",
        "Content-Type": "application/json"
    }

    # 5. Envia a requisição com tratamento completo de erros
    try:
        resposta = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers=cabecalhos,
            json=payload,
            timeout=TIMEOUT_REQUISICAO
        )
    except requests.exceptions.Timeout:
        raise HTTPException(
            status_code=504,
            detail="Tempo limite esgotado ao aguardar resposta da Groq (timeout de 30s). Tente novamente."
        )
    except requests.exceptions.ConnectionError:
        raise HTTPException(
            status_code=502,
            detail="Falha de conexão com os servidores da Groq. Verifique sua conexão com a internet."
        )
    except requests.exceptions.RequestException as erro:
        raise HTTPException(
            status_code=502,
            detail=f"Erro de comunicação com a Groq: {str(erro)}"
        )

    # 6. Trata erros HTTP da Groq de forma específica
    if resposta.status_code != 200:
        tratar_erro_groq_chat(resposta)

    # 7. Extrai e retorna o texto da resposta
    try:
        texto_resposta = resposta.json()["choices"][0]["message"]["content"]
    except (KeyError, IndexError, ValueError):
        raise HTTPException(
            status_code=502,
            detail="A Groq retornou uma resposta em formato inesperado. Tente novamente."
        )

    return {
        "resposta": texto_resposta,
        "documento": documento.nome_arquivo,
        "contexto_truncado": len(documento.texto_extraido) > LIMITE_CONTEXTO_CHAT
    }
