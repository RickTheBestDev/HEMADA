# Arquivo: app/route/upload.py
"""
Módulo de Upload e Inteligência Documental do HEMADA.
Responsável por receber arquivos PDF, validar formato e integridade,
extrair texto via PyMuPDF e processar a análise inteligente estruturada via Groq API.
Suporta documentos pequenos e extensos com divisão em partes, controle rigoroso
de taxa de tokens (TPM), retry automático com espera progressiva e consolidação em Python.
"""

import os
import re
import json
import time
import requests
import pymupdf
from fastapi import APIRouter, UploadFile, File, Form, HTTPException

from app.database import SessionLocal
from app.model.documento import Documento

upload = APIRouter()

# Limite máximo de tamanho do arquivo para upload: 10 Megabytes (em bytes)
TAMANHO_MAXIMO_BYTES = 10 * 1024 * 1024

# Limite de caracteres por parte para envio à Groq (~1.500 tokens de entrada)
# Reduzido para 6.000 caracteres para operar com folga dentro do teto de 8.000 TPM da Groq
LIMITE_CARACTERES_PARTE = 6000

# Pausa preventiva entre partes de documentos extensos (em segundos)
# Permite a recarga contínua da cota de tokens (~133 tokens/segundo)
PAUSA_ENTRE_PARTES_SEGUNDOS = 3.0

# Número máximo de tentativas de retry para erros temporários (como HTTP 429)
MAXIMO_TENTATIVAS_RETRY = 3

# Tempo padrão de espera quando a Groq não especificar no cabeçalho ou mensagem
TEMPO_ESPERA_PADRAO_RETRY = 3.0

# Modelo padrão da Groq caso não esteja configurado no .env
MODELO_PADRAO_GROQ = "openai/gpt-oss-20b"

# Prompt de sistema para orientar a inteligência artificial da Groq na análise documental
PROMPT_SISTEMA = (
    "Você é o assistente de inteligência documental do sistema HEMADA.\n"
    "Sua função é ler o texto extraído de um documento e produzir uma análise estruturada, "
    "organizada e estritamente factual.\n\n"
    "REGRAS OBRIGATÓRIAS:\n"
    "1. Baseie-se ÚNICA E EXCLUSIVAMENTE nas informações presentes no texto do documento.\n"
    "2. NUNCA invente, presuma ou deduza nomes, datas, valores ou fatos que não estejam explícitos.\n"
    "3. Se uma informação solicitada não existir no documento, indique explicitamente 'Não identificado no documento' "
    "ou retorne uma lista vazia.\n"
    "4. Retorne sua resposta EXCLUSIVAMENTE em formato JSON válido, sem qualquer texto ou explicação fora do JSON.\n\n"
    "ESTRUTURA OBRIGATÓRIA DO JSON:\n"
    "{\n"
    '  "resumo_geral": "Breve resumo geral sobre o conteúdo do documento",\n'
    '  "assunto_principal": "Tema ou assunto central do documento",\n'
    '  "informacoes_importantes": ["Ponto importante 1", "Ponto importante 2"],\n'
    '  "datas_identificadas": ["Data encontrada com respectivo contexto"],\n'
    '  "valores_monetarios": ["Valor encontrado com respectivo contexto"],\n'
    '  "pessoas_e_empresas": ["Nome da pessoa ou empresa citada"],\n'
    '  "pendencias": ["Pendência ou obrigação pendente identificada"],\n'
    '  "pontos_de_atencao": ["Alerta, risco ou ponto de atenção identificado"]\n'
    "}"
)

CAMPOS_OBRIGATORIOS = [
    "resumo_geral",
    "assunto_principal",
    "informacoes_importantes",
    "datas_identificadas",
    "valores_monetarios",
    "pessoas_e_empresas",
    "pendencias",
    "pontos_de_atencao"
]


def validar_arquivo_pdf(nome_arquivo: str, conteudo: bytes) -> None:
    """
    Valida as regras de segurança e formato do arquivo:
    - Extensão deve ser .pdf
    - Não pode ser vazio (0 bytes)
    - Não pode exceder 10 MB
    - Deve conter a assinatura mágica de cabeçalho do padrão PDF (%PDF-)
    """
    if not nome_arquivo or not nome_arquivo.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=400,
            detail="Formato de arquivo inválido. Apenas arquivos PDF (.pdf) são aceitos."
        )

    tamanho = len(conteudo)
    if tamanho == 0:
        raise HTTPException(
            status_code=400,
            detail="O arquivo enviado está vazio (0 bytes)."
        )

    if tamanho > TAMANHO_MAXIMO_BYTES:
        raise HTTPException(
            status_code=400,
            detail="O arquivo excede o limite máximo permitido de 10 MB."
        )

    if not conteudo.startswith(b"%PDF-"):
        raise HTTPException(
            status_code=400,
            detail="O arquivo enviado não é um documento PDF válido ou está corrompido."
        )


def extrair_texto_pdf(conteudo: bytes) -> tuple[str, int]:
    """
    Abre o PDF em memória utilizando PyMuPDF, percorre todas as páginas
    e extrai o conteúdo de texto.
    Retorna uma tupla contendo (texto_completo, total_paginas).
    """
    try:
        doc_pdf = pymupdf.open(stream=conteudo, filetype="pdf")
    except Exception as erro:
        raise HTTPException(
            status_code=400,
            detail=f"Não foi possível abrir o PDF. Arquivo ilegível ou corrompido: {str(erro)}"
        )

    total_paginas = len(doc_pdf)
    if total_paginas == 0:
        doc_pdf.close()
        raise HTTPException(
            status_code=400,
            detail="O arquivo PDF não possui páginas."
        )

    textos_das_paginas = []
    try:
        for pagina in doc_pdf:
            texto = pagina.get_text()
            if texto:
                textos_das_paginas.append(texto.strip())
    except Exception as erro:
        doc_pdf.close()
        raise HTTPException(
            status_code=400,
            detail=f"Erro durante a extração de páginas do PDF: {str(erro)}"
        )
    finally:
        doc_pdf.close()

    texto_completo = "\n\n".join(textos_das_paginas).strip()

    if not texto_completo:
        raise HTTPException(
            status_code=400,
            detail="O documento PDF não contém texto selecionável. Documentos escaneados ou baseados apenas em imagem não são suportados nesta versão."
        )

    return texto_completo, total_paginas


def dividir_texto_em_partes(texto: str, tamanho_maximo: int = LIMITE_CARACTERES_PARTE) -> list[str]:
    """
    Divide um texto longo em blocos menores (chunks) de até `tamanho_maximo` caracteres,
    respeitando as quebras de parágrafo e linhas para não cortar frases ou palavras no meio.
    """
    texto = texto.strip()
    if len(texto) <= tamanho_maximo:
        return [texto]

    paragrafos = texto.split("\n\n")
    partes = []
    bloco_atual = []
    tamanho_atual = 0

    for paragrafo in paragrafos:
        tam_paragrafo = len(paragrafo)

        # Se um único parágrafo for maior que o limite, quebra linha por linha
        if tam_paragrafo > tamanho_maximo:
            linhas = paragrafo.split("\n")
            for linha in linhas:
                tam_linha = len(linha)
                if tamanho_atual + tam_linha + 1 > tamanho_maximo and bloco_atual:
                    partes.append("\n".join(bloco_atual).strip())
                    bloco_atual = [linha]
                    tamanho_atual = tam_linha
                else:
                    bloco_atual.append(linha)
                    tamanho_atual += tam_linha + 1
        elif tamanho_atual + tam_paragrafo + 2 > tamanho_maximo and bloco_atual:
            partes.append("\n\n".join(bloco_atual).strip())
            bloco_atual = [paragrafo]
            tamanho_atual = tam_paragrafo
        else:
            bloco_atual.append(paragrafo)
            tamanho_atual += tam_paragrafo + 2

    if bloco_atual:
        sobra = "\n\n".join(bloco_atual).strip()
        if sobra:
            partes.append(sobra)

    return partes if partes else [texto]


def extrair_tempo_espera_groq(resposta: requests.Response, tentativa: int) -> float:
    """
    Identifica o tempo em segundos que o sistema deve aguardar antes de reenviar
    a requisição após receber um código HTTP 429 (Rate Limit).
    Consulta cabeçalhos oficiais (retry-after, x-ratelimit-reset-tokens) e a mensagem de erro.
    """
    # 1. Tenta obter pelo cabeçalho padrão 'retry-after'
    retry_after = resposta.headers.get("retry-after")
    if retry_after:
        try:
            return min(max(float(retry_after) + 0.5, 1.0), 15.0)
        except ValueError:
            pass

    # 2. Tenta obter pelo cabeçalho 'x-ratelimit-reset-tokens' da Groq (ex: '3.4s' ou '800ms')
    reset_tokens = resposta.headers.get("x-ratelimit-reset-tokens")
    if reset_tokens:
        try:
            if reset_tokens.endswith("ms"):
                return min(max(float(reset_tokens[:-2]) / 1000.0 + 0.5, 1.0), 15.0)
            elif reset_tokens.endswith("s"):
                return min(max(float(reset_tokens[:-1]) + 0.5, 1.0), 15.0)
        except ValueError:
            pass

    # 3. Tenta extrair da mensagem de erro JSON (ex: "Please try again in 4.25s.")
    try:
        dados = resposta.json()
        if isinstance(dados, dict) and "error" in dados:
            mensagem = str(dados["error"].get("message", ""))
            match = re.search(r"try again in ([0-9\.]+)s", mensagem, re.IGNORECASE)
            if match:
                return min(max(float(match.group(1)) + 0.5, 1.0), 15.0)
    except Exception:
        pass

    # 4. Fallback: espera progressiva baseada no número da tentativa
    return min(TEMPO_ESPERA_PADRAO_RETRY * tentativa, 10.0)


def tratar_erro_resposta_groq(resposta: requests.Response) -> None:
    """
    Trata erros HTTP retornados pela API da Groq de forma transparente e segura,
    informando o código exato e a causa sem expor credenciais ou chaves de API.
    """
    status = resposta.status_code

    if status == 401:
        raise HTTPException(
            status_code=401,
            detail="Falha de autenticação na API da Groq (Erro 401). Verifique se a chave API_KEY no arquivo .env está correta."
        )
    elif status == 403:
        raise HTTPException(
            status_code=403,
            detail="Acesso negado pela API da Groq (Erro 403). Verifique as permissões da sua conta ou da chave de API."
        )
    elif status == 404:
        raise HTTPException(
            status_code=404,
            detail="O modelo de inteligência artificial configurado não foi encontrado na Groq (Erro 404). Verifique a variável GROQ_MODEL no .env."
        )
    elif status == 413:
        raise HTTPException(
            status_code=413,
            detail="O documento ou lote de texto enviado é muito extenso e ultrapassou o limite de processamento da API da Groq (Erro 413). O sistema processa em partes, mas o volume de texto excedeu a capacidade do modelo."
        )
    elif status == 429:
        raise HTTPException(
            status_code=429,
            detail="A inteligência artificial atingiu o limite temporário de processamento por minuto da Groq (8.000 tokens/min). O sistema realizou tentativas automáticas de espera, mas a cota permaneceu ocupada. Por favor, aguarde cerca de 30 segundos e envie o arquivo novamente."
        )
    elif status in (500, 503):
        raise HTTPException(
            status_code=503,
            detail=f"Os servidores da inteligência artificial estão temporariamente indisponíveis ou instáveis (Erro {status}). Tente novamente em alguns instantes."
        )

    # Extrai mensagem de detalhe da Groq sem vazar chaves de API
    mensagem_detalhe = ""
    try:
        dados_erro = resposta.json()
        if isinstance(dados_erro, dict) and "error" in dados_erro:
            bruto = str(dados_erro["error"].get("message", ""))
            # Remove qualquer menção a chaves gsk_
            mensagem_detalhe = bruto.split("gsk_")[0].strip()
    except Exception:
        mensagem_detalhe = ""

    detalhe_final = f"A API da Groq retornou o código de erro {status}."
    if mensagem_detalhe:
        detalhe_final += f" Causa: {mensagem_detalhe}"

    raise HTTPException(status_code=502, detail=detalhe_final)


def enviar_requisicao_groq(payload: dict, chave_api: str) -> dict:
    """
    Envia a requisição HTTP POST para a API da Groq com timeout configurado.
    Implementa retry automático com espera progressiva para erro HTTP 429 (Rate Limit).
    Trata erros de rede, status codes e valida o retorno JSON.
    """
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {chave_api}",
        "Content-Type": "application/json"
    }

    ultima_resposta = None

    for tentativa in range(1, MAXIMO_TENTATIVAS_RETRY + 1):
        try:
            resposta = requests.post(url, headers=headers, json=payload, timeout=30)
            ultima_resposta = resposta
        except requests.exceptions.Timeout:
            if tentativa == MAXIMO_TENTATIVAS_RETRY:
                raise HTTPException(
                    status_code=504,
                    detail="Tempo limite esgotado ao aguardar resposta da inteligência artificial (Timeout de 30s)."
                )
            time.sleep(2.0)
            continue
        except requests.exceptions.ConnectionError:
            raise HTTPException(
                status_code=502,
                detail="Falha de conexão com os servidores da Groq. Verifique sua conexão com a internet."
            )
        except requests.exceptions.RequestException as erro:
            raise HTTPException(
                status_code=502,
                detail=f"Erro de comunicação com a Groq durante a requisição: {str(erro)}"
            )

        # Se for sucesso (200), processa e retorna
        if resposta.status_code == 200:
            try:
                corpo = resposta.json()
                conteudo_bruto = corpo["choices"][0]["message"]["content"]
                analise_json = json.loads(conteudo_bruto)
                return analise_json
            except Exception:
                raise HTTPException(
                    status_code=502,
                    detail="A inteligência artificial retornou uma resposta em formato inválido (não foi possível converter para JSON)."
                )

        # Se for 429 (Rate Limit), aguarda o tempo informado pela Groq e tenta novamente
        if resposta.status_code == 429:
            if tentativa < MAXIMO_TENTATIVAS_RETRY:
                tempo_espera = extrair_tempo_espera_groq(resposta, tentativa)
                time.sleep(tempo_espera)
                continue
            else:
                # Esgotou as tentativas
                raise HTTPException(
                    status_code=429,
                    detail="A inteligência artificial atingiu o limite temporário de processamento por minuto da Groq (8.000 tokens/min). O sistema realizou tentativas automáticas de espera, mas a cota permaneceu ocupada. Por favor, aguarde cerca de 30 segundos e envie o arquivo novamente."
                )

        # Para outros erros que não são 429 (ex: 401, 403, 404, 413, 500), trata imediatamente sem retry inútil
        tratar_erro_resposta_groq(resposta)

    if ultima_resposta is not None:
        tratar_erro_resposta_groq(ultima_resposta)

    raise HTTPException(
        status_code=502,
        detail="Não foi possível obter resposta da inteligência artificial após múltiplas tentativas."
    )


def analisar_parte_com_ia(texto_parte: str, chave_api: str, modelo_groq: str,
                          comando_adicional: str = "", indice: int = 1, total: int = 1) -> dict:
    """
    Analisa um bloco específico de texto enviando-o à Groq.
    Retorna o dicionário com os campos da análise para aquela parte.
    """
    if total > 1:
        mensagem_usuario = f"CONTEÚDO DO DOCUMENTO (SEÇÃO {indice} DE {total}):\n---\n{texto_parte}\n---"
    else:
        mensagem_usuario = f"CONTEÚDO DO DOCUMENTO:\n---\n{texto_parte}\n---"

    if comando_adicional and comando_adicional.strip():
        mensagem_usuario += f"\n\nINSTRUÇÃO ADICIONAL DO USUÁRIO:\n{comando_adicional.strip()}"

    payload = {
        "model": modelo_groq,
        "messages": [
            {"role": "system", "content": PROMPT_SISTEMA},
            {"role": "user", "content": mensagem_usuario}
        ],
        "temperature": 0.1,
        "response_format": {"type": "json_object"}
    }

    analise_json = enviar_requisicao_groq(payload, chave_api)

    # Normaliza campos obrigatórios
    for campo in CAMPOS_OBRIGATORIOS:
        if campo not in analise_json or analise_json[campo] is None:
            analise_json[campo] = [] if campo not in ["resumo_geral", "assunto_principal"] else "Não identificado no documento."

    return analise_json


def consolidar_listas(analises_parciais: list[dict], campo: str) -> list:
    """
    Une itens de lista de múltiplas análises parciais em Python puro (custo zero de tokens na IA),
    removendo duplicatas e preservando integralmente todas as informações relevantes.
    """
    itens_consolidados = []
    itens_vistos = set()

    for analise in analises_parciais:
        valores = analise.get(campo, [])
        if isinstance(valores, list):
            for v in valores:
                v_limpo = str(v).strip()
                v_lower = v_limpo.lower()
                if v_limpo and v_lower not in ["não identificado no documento", "nenhum", "nenhuma", "n/a", "não identificado"] and v_lower not in itens_vistos:
                    itens_consolidados.append(v_limpo)
                    itens_vistos.add(v_lower)
        elif isinstance(valores, str) and valores.strip():
            v_limpo = valores.strip()
            v_lower = v_limpo.lower()
            if v_lower not in ["não identificado no documento", "nenhum", "nenhuma", "n/a", "não identificado"] and v_lower not in itens_vistos:
                itens_consolidados.append(v_limpo)
                itens_vistos.add(v_lower)

    return itens_consolidados if itens_consolidados else ["Não identificado no documento"]


def consolidar_analises_em_python(analises_parciais: list[dict]) -> dict:
    """
    Consolida as análises de múltiplas partes de um documento longo em Python,
    evitando chamadas adicionais à IA para poupar a cota de tokens por minuto (TPM).
    Garante a integridade total das oito categorias documentais sem perder informações.
    """
    if len(analises_parciais) == 1:
        return analises_parciais[0]

    # Consolida os assuntos principais identificados
    assuntos_encontrados = []
    for p in analises_parciais:
        assunto = str(p.get("assunto_principal", "")).strip()
        if assunto and assunto.lower() not in ["não identificado no documento", "não informado"] and assunto not in assuntos_encontrados:
            assuntos_encontrados.append(assunto)

    assunto_final = " / ".join(assuntos_encontrados) if assuntos_encontrados else "Documento Extenso"

    # Consolida os resumos parciais em uma narrativa fluida e sequencial
    resumos_validos = []
    for i, p in enumerate(analises_parciais, start=1):
        resumo = str(p.get("resumo_geral", "")).strip()
        if resumo and resumo.lower() not in ["não identificado no documento", "não informado"]:
            if len(analises_parciais) > 1 and not resumo.lower().startswith(f"seção {i}"):
                resumos_validos.append(f"[Parte {i}] {resumo}")
            else:
                resumos_validos.append(resumo)

    resumo_final = " ".join(resumos_validos) if resumos_validos else "Não identificado no documento."

    # Consolida as 6 categorias de listas sem descartar nada
    analise_consolidada = {
        "resumo_geral": resumo_final,
        "assunto_principal": assunto_final,
        "informacoes_importantes": consolidar_listas(analises_parciais, "informacoes_importantes"),
        "datas_identificadas": consolidar_listas(analises_parciais, "datas_identificadas"),
        "valores_monetarios": consolidar_listas(analises_parciais, "valores_monetarios"),
        "pessoas_e_empresas": consolidar_listas(analises_parciais, "pessoas_e_empresas"),
        "pendencias": consolidar_listas(analises_parciais, "pendencias"),
        "pontos_de_atencao": consolidar_listas(analises_parciais, "pontos_de_atencao")
    }

    return analise_consolidada


def analisar_documento_com_ia(texto_documento: str, comando_adicional: str = "") -> dict:
    """
    Orquestra a análise com inteligência artificial:
    - Se o texto for pequeno (<= 6.000 caracteres), processa em chamada única direta.
    - Se o texto for extenso (> 6.000 caracteres), divide em blocos de até 6.000 caracteres,
      processa cada parte sequencialmente com pausa preventiva de 3s e retry inteligente para 429,
      e consolida integralmente as oito categorias em Python.
    """
    chave_api = os.getenv("API_KEY")
    if not chave_api:
        raise HTTPException(
            status_code=500,
            detail="Chave de API da Groq não configurada no servidor (.env)."
        )

    modelo_groq = os.getenv("GROQ_MODEL", MODELO_PADRAO_GROQ)

    # Divide o texto em blocos de até 6.000 caracteres para respeitar os limites de TPM (8.000 tokens/min)
    partes = dividir_texto_em_partes(texto_documento, LIMITE_CARACTERES_PARTE)
    total_partes = len(partes)

    # Caso 1: Documento cabe em um único bloco (processamento direto)
    if total_partes == 1:
        return analisar_parte_com_ia(partes[0], chave_api, modelo_groq, comando_adicional, 1, 1)

    # Caso 2: Documento extenso dividido em múltiplas seções
    analises_parciais = []
    for indice, parte in enumerate(partes, start=1):
        analise_parte = analisar_parte_com_ia(
            texto_parte=parte,
            chave_api=chave_api,
            modelo_groq=modelo_groq,
            comando_adicional=comando_adicional,
            indice=indice,
            total=total_partes
        )
        analises_parciais.append(analise_parte)

        # Pausa preventiva entre partes para permitir que a Groq reabasteça a cota de TPM (~133 tokens/s)
        if indice < total_partes:
            time.sleep(PAUSA_ENTRE_PARTES_SEGUNDOS)

    # Consolida os resultados das partes em Python, sem gastar tokens adicionais
    return consolidar_analises_em_python(analises_parciais)


def formatar_analise_para_texto(analise: dict) -> str:
    """
    Converte o dicionário de análise estruturada em um texto limpo e legível,
    ideal para visualização nos cards do front-end e armazenamento no banco.
    """
    linhas = []

    resumo = analise.get("resumo_geral") or "Não identificado no documento."
    linhas.append(f"📋 RESUMO GERAL:\n{resumo}\n")

    assunto = analise.get("assunto_principal") or "Não identificado no documento."
    linhas.append(f"📌 ASSUNTO PRINCIPAL:\n{assunto}\n")

    def formatar_itens(titulo: str, icone: str, itens) -> str:
        if not itens or itens == ["Não identificado no documento"] or itens == [""]:
            return f"{icone} {titulo}:\n• Nenhum item identificado no documento.\n"
        if isinstance(itens, list):
            validos = [f"• {str(i)}" for i in itens if str(i).strip()]
            return f"{icone} {titulo}:\n" + "\n".join(validos) + "\n" if validos else f"{icone} {titulo}:\n• Nenhum item identificado no documento.\n"
        return f"{icone} {titulo}:\n• {str(itens)}\n"

    linhas.append(formatar_itens("INFORMAÇÕES IMPORTANTES", "⭐", analise.get("informacoes_importantes")))
    linhas.append(formatar_itens("DATAS IDENTIFICADAS", "📅", analise.get("datas_identificadas")))
    linhas.append(formatar_itens("VALORES MONETÁRIOS", "💰", analise.get("valores_monetarios")))
    linhas.append(formatar_itens("PESSOAS E EMPRESAS", "👥", analise.get("pessoas_e_empresas")))
    linhas.append(formatar_itens("PENDÊNCIAS", "⚠️", analise.get("pendencias")))
    linhas.append(formatar_itens("PONTOS DE ATENÇÃO", "🔍", analise.get("pontos_de_atencao")))

    return "\n".join(linhas).strip()


def salvar_documento_no_banco(nome_arquivo: str, total_paginas: int, texto_extraido: str, resposta_ia: str) -> int:
    """
    Persiste as informações do documento analisado na tabela SQLite com fechamento seguro de sessão.
    """
    banco = SessionLocal()
    try:
        novo_doc = Documento(
            nome_arquivo=nome_arquivo,
            total_paginas=total_paginas,
            texto_extraido=texto_extraido,
            resposta_ia=resposta_ia
        )
        banco.add(novo_doc)
        banco.commit()
        banco.refresh(novo_doc)
        return novo_doc.id
    finally:
        banco.close()


@upload.post("/uploads/")
def processar_pdf(arquivo: UploadFile = File(...), pergunta: str = Form(default="")):
    """
    Rota principal de upload e processamento do PDF:
    1. Lê o arquivo recebido
    2. Valida extensão, tamanho e integridade
    3. Extrai texto das páginas com PyMuPDF
    4. Analisa conteúdo com a Groq (com divisão em partes e controle de tokens TPM)
    5. Formata a resposta para exibição
    6. Salva no banco de dados SQLite
    7. Retorna dados estruturados para o front-end
    """
    # 1. Lê o conteúdo do arquivo
    conteudo_arquivo = arquivo.file.read()

    # 2. Valida o arquivo PDF
    validar_arquivo_pdf(arquivo.filename, conteudo_arquivo)

    # 3. Extrai o texto do PDF
    texto_completo, total_paginas = extrair_texto_pdf(conteudo_arquivo)

    # 4. Processa a análise com IA (suporta pequenos e grandes documentos)
    analise_estruturada = analisar_documento_com_ia(texto_completo, comando_adicional=pergunta)

    # 5. Formata o texto para exibição
    texto_ia_formatado = formatar_analise_para_texto(analise_estruturada)

    # 6. Salva no banco SQLite
    id_gerado = salvar_documento_no_banco(
        nome_arquivo=arquivo.filename,
        total_paginas=total_paginas,
        texto_extraido=texto_completo,
        resposta_ia=texto_ia_formatado
    )

    # 7. Retorna o resultado para o front-end
    return {
        "mensagem": "Sucesso",
        "arquivo": arquivo.filename,
        "total_paginas": total_paginas,
        "resposta_ia": texto_ia_formatado,
        "analise_estruturada": analise_estruturada,
        "documento_id": id_gerado
    }
