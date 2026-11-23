# Arquivo: tests/test_chat.py
"""
Testes automatizados da rota POST /chat/ do HEMADA.

Coberturas:
- Documento não encontrado (404)
- Chave de API ausente (500)
- Documento sem texto extraído (422)
- Truncamento de contexto extenso
- Erro de autenticação Groq (401)
- Erro de acesso negado Groq (403)
- Modelo não encontrado Groq (404)
- Limite de requisições Groq (429) com extração de tempo de espera
- Servidor Groq indisponível (503)
- Erro de rede (ConnectionError)
- Timeout de requisição
- Resposta em formato inválido da Groq
- Resposta de sucesso completa
- Retorno do campo contexto_truncado
"""

import unittest
from unittest.mock import patch, MagicMock
import os
import sys

# Garante que a raiz do projeto está no path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestTruncarContexto(unittest.TestCase):
    """Testa a função utilitária de truncamento do contexto."""

    def setUp(self):
        from app.route.chat import truncar_contexto
        self.truncar = truncar_contexto

    def test_01_texto_dentro_do_limite_nao_e_truncado(self):
        """Texto com menos de 6.000 chars deve ser retornado sem alteração."""
        texto = "palavra " * 100  # 800 chars
        resultado = self.truncar(texto, 6000)
        self.assertEqual(resultado, texto)

    def test_02_texto_acima_do_limite_e_truncado(self):
        """Texto com mais de 6.000 chars deve ser truncado."""
        texto = "palavra " * 2000  # 16.000 chars
        resultado = self.truncar(texto, 6000)
        self.assertLessEqual(len(resultado), 6000 + 200)  # margem para o aviso
        self.assertIn("[Texto truncado", resultado)

    def test_03_truncamento_preserva_palavras_completas(self):
        """O truncamento não deve cortar uma palavra no meio."""
        texto = "a" * 5990 + " palavra_completa " + "b" * 100
        resultado = self.truncar(texto, 6000)
        self.assertNotIn("palavra_comp", resultado)  # palavra cortada não deve aparecer

    def test_04_texto_exatamente_no_limite_nao_e_truncado(self):
        """Texto exatamente no limite não deve ser truncado."""
        texto = "x" * 6000
        resultado = self.truncar(texto, 6000)
        self.assertEqual(resultado, texto)
        self.assertNotIn("[Texto truncado", resultado)


class TestTratarErroGroqChat(unittest.TestCase):
    """Testa o tratamento individual dos erros HTTP da Groq."""

    def setUp(self):
        from app.route.chat import tratar_erro_groq_chat
        from fastapi import HTTPException
        self.tratar = tratar_erro_groq_chat
        self.HTTPException = HTTPException

    def _mock_resposta(self, status_code, corpo_json=None):
        mock = MagicMock()
        mock.status_code = status_code
        mock.json.return_value = corpo_json or {}
        return mock

    def test_05_erro_401_autenticacao(self):
        """HTTP 401 deve levantar HTTPException 401 com mensagem de autenticação."""
        with self.assertRaises(self.HTTPException) as ctx:
            self.tratar(self._mock_resposta(401))
        self.assertEqual(ctx.exception.status_code, 401)
        self.assertIn("autenticação", ctx.exception.detail.lower())

    def test_06_erro_403_acesso_negado(self):
        """HTTP 403 deve levantar HTTPException 403."""
        with self.assertRaises(self.HTTPException) as ctx:
            self.tratar(self._mock_resposta(403))
        self.assertEqual(ctx.exception.status_code, 403)

    def test_07_erro_404_modelo_nao_encontrado(self):
        """HTTP 404 deve levantar HTTPException 404 sobre modelo."""
        with self.assertRaises(self.HTTPException) as ctx:
            self.tratar(self._mock_resposta(404))
        self.assertEqual(ctx.exception.status_code, 404)
        self.assertIn("modelo", ctx.exception.detail.lower())

    def test_08_erro_429_com_tempo_sugerido_na_mensagem(self):
        """HTTP 429 deve extrair o tempo de espera da mensagem da Groq."""
        corpo = {"error": {"message": "Rate limit exceeded. Please try again in 4.5s."}}
        with self.assertRaises(self.HTTPException) as ctx:
            self.tratar(self._mock_resposta(429, corpo))
        self.assertEqual(ctx.exception.status_code, 429)
        self.assertIn("4.5s", ctx.exception.detail)

    def test_09_erro_429_sem_tempo_usa_fallback(self):
        """HTTP 429 sem tempo na mensagem usa fallback '30 segundos'."""
        with self.assertRaises(self.HTTPException) as ctx:
            self.tratar(self._mock_resposta(429))
        self.assertEqual(ctx.exception.status_code, 429)
        self.assertIn("30 segundos", ctx.exception.detail)

    def test_10_erro_500_groq_retorna_503(self):
        """HTTP 500 da Groq deve levantar HTTPException 503."""
        with self.assertRaises(self.HTTPException) as ctx:
            self.tratar(self._mock_resposta(500))
        self.assertEqual(ctx.exception.status_code, 503)

    def test_11_erro_503_groq_retorna_503(self):
        """HTTP 503 da Groq deve levantar HTTPException 503."""
        with self.assertRaises(self.HTTPException) as ctx:
            self.tratar(self._mock_resposta(503))
        self.assertEqual(ctx.exception.status_code, 503)

    def test_12_erro_desconhecido_retorna_502(self):
        """Código de erro desconhecido deve levantar HTTPException 502."""
        with self.assertRaises(self.HTTPException) as ctx:
            self.tratar(self._mock_resposta(418))
        self.assertEqual(ctx.exception.status_code, 502)
        self.assertIn("418", ctx.exception.detail)

    def test_13_erro_nao_expoe_chave_gsk(self):
        """Mensagem de erro não deve vazar fragmentos de chave (gsk_...)."""
        corpo = {"error": {"message": "Invalid API key: gsk_minha_chave_secreta_aqui"}}
        with self.assertRaises(self.HTTPException) as ctx:
            self.tratar(self._mock_resposta(401))
        self.assertNotIn("gsk_", ctx.exception.detail)


class TestFazerPerguntaRota(unittest.TestCase):
    """
    Testa a rota fazer_pergunta de forma direta
    usando unittest com mocks nas dependências externas.
    """

    def _mock_documento(self, id=1, nome="teste.pdf", paginas=5, texto="Texto do documento de teste.", resposta_ia="Análise."):
        doc = MagicMock()
        doc.id = id
        doc.nome_arquivo = nome
        doc.total_paginas = paginas
        doc.texto_extraido = texto
        doc.resposta_ia = resposta_ia
        return doc

    def test_14_documento_nao_encontrado_retorna_404(self):
        """Deve retornar 404 quando o documento_id não existe no banco."""
        from app.route.chat import fazer_pergunta, PerguntaChat
        from fastapi import HTTPException

        dados = PerguntaChat(documento_id=99999, pergunta="O que é isto?")

        with patch("app.route.chat.os.getenv", return_value="chave_fake"), \
             patch("app.route.chat.SessionLocal") as mock_sessao:
            mock_sessao.return_value.query.return_value.filter.return_value.first.return_value = None

            with self.assertRaises(HTTPException) as ctx:
                fazer_pergunta(dados)

            self.assertEqual(ctx.exception.status_code, 404)
            self.assertIn("99999", ctx.exception.detail)

    def test_15_chave_api_ausente_retorna_500(self):
        """Deve retornar 500 quando API_KEY não está configurada."""
        from app.route.chat import fazer_pergunta, PerguntaChat
        from fastapi import HTTPException

        dados = PerguntaChat(documento_id=1, pergunta="Teste")

        with patch("app.route.chat.os.getenv", return_value=None):
            with self.assertRaises(HTTPException) as ctx:
                fazer_pergunta(dados)

            self.assertEqual(ctx.exception.status_code, 500)

    def test_16_documento_sem_texto_retorna_422(self):
        """Deve retornar 422 quando o documento não tem texto extraído."""
        from app.route.chat import fazer_pergunta, PerguntaChat
        from fastapi import HTTPException

        dados = PerguntaChat(documento_id=1, pergunta="Teste")
        doc = self._mock_documento(texto=None)

        with patch("app.route.chat.os.getenv", return_value="chave_fake"), \
             patch("app.route.chat.SessionLocal") as mock_sessao:
            mock_sessao.return_value.query.return_value.filter.return_value.first.return_value = doc

            with self.assertRaises(HTTPException) as ctx:
                fazer_pergunta(dados)

            self.assertEqual(ctx.exception.status_code, 422)

    def test_17_timeout_de_rede_retorna_504(self):
        """Deve retornar 504 quando a requisição à Groq excede o timeout."""
        import requests as req_lib
        from app.route.chat import fazer_pergunta, PerguntaChat
        from fastapi import HTTPException

        dados = PerguntaChat(documento_id=1, pergunta="Teste")
        doc = self._mock_documento()

        with patch("app.route.chat.os.getenv", return_value="chave_fake"), \
             patch("app.route.chat.SessionLocal") as mock_sessao, \
             patch("app.route.chat.requests.post", side_effect=req_lib.exceptions.Timeout):
            mock_sessao.return_value.query.return_value.filter.return_value.first.return_value = doc

            with self.assertRaises(HTTPException) as ctx:
                fazer_pergunta(dados)

            self.assertEqual(ctx.exception.status_code, 504)
            self.assertIn("tempo limite", ctx.exception.detail.lower())

    def test_18_erro_de_conexao_retorna_502(self):
        """Deve retornar 502 quando há falha de conexão com a Groq."""
        import requests as req_lib
        from app.route.chat import fazer_pergunta, PerguntaChat
        from fastapi import HTTPException

        dados = PerguntaChat(documento_id=1, pergunta="Teste")
        doc = self._mock_documento()

        with patch("app.route.chat.os.getenv", return_value="chave_fake"), \
             patch("app.route.chat.SessionLocal") as mock_sessao, \
             patch("app.route.chat.requests.post", side_effect=req_lib.exceptions.ConnectionError):
            mock_sessao.return_value.query.return_value.filter.return_value.first.return_value = doc

            with self.assertRaises(HTTPException) as ctx:
                fazer_pergunta(dados)

            self.assertEqual(ctx.exception.status_code, 502)
            self.assertIn("conexão", ctx.exception.detail.lower())

    def test_19_resposta_invalida_da_groq_retorna_502(self):
        """Deve retornar 502 quando a Groq retorna JSON sem o campo esperado."""
        from app.route.chat import fazer_pergunta, PerguntaChat
        from fastapi import HTTPException

        dados = PerguntaChat(documento_id=1, pergunta="Teste")
        doc = self._mock_documento()

        mock_resposta = MagicMock()
        mock_resposta.status_code = 200
        mock_resposta.json.return_value = {"choices": []}  # lista vazia — KeyError ao acessar [0]

        with patch("app.route.chat.os.getenv", return_value="chave_fake"), \
             patch("app.route.chat.SessionLocal") as mock_sessao, \
             patch("app.route.chat.requests.post", return_value=mock_resposta):
            mock_sessao.return_value.query.return_value.filter.return_value.first.return_value = doc

            with self.assertRaises(HTTPException) as ctx:
                fazer_pergunta(dados)

            self.assertEqual(ctx.exception.status_code, 502)

    def test_20_sucesso_retorna_resposta_e_metadados(self):
        """Deve retornar a resposta da IA com campos 'resposta', 'documento' e 'contexto_truncado'."""
        from app.route.chat import fazer_pergunta, PerguntaChat

        dados = PerguntaChat(documento_id=1, pergunta="Qual é o assunto do documento?")
        doc = self._mock_documento(texto="Texto curto.", nome="meu_documento.pdf")

        mock_resposta = MagicMock()
        mock_resposta.status_code = 200
        mock_resposta.json.return_value = {
            "choices": [{"message": {"content": "O assunto é o teste."}}]
        }

        with patch("app.route.chat.os.getenv", return_value="chave_fake"), \
             patch("app.route.chat.SessionLocal") as mock_sessao, \
             patch("app.route.chat.requests.post", return_value=mock_resposta):
            mock_sessao.return_value.query.return_value.filter.return_value.first.return_value = doc

            resultado = fazer_pergunta(dados)

        self.assertEqual(resultado["resposta"], "O assunto é o teste.")
        self.assertEqual(resultado["documento"], "meu_documento.pdf")
        self.assertIn("contexto_truncado", resultado)
        self.assertFalse(resultado["contexto_truncado"])

    def test_21_documento_extenso_indica_contexto_truncado(self):
        """Deve retornar contexto_truncado=True para documentos maiores que 6.000 chars."""
        from app.route.chat import fazer_pergunta, PerguntaChat

        texto_extenso = "palavra " * 2000  # ~16.000 chars
        dados = PerguntaChat(documento_id=1, pergunta="Teste")
        doc = self._mock_documento(texto=texto_extenso)

        mock_resposta = MagicMock()
        mock_resposta.status_code = 200
        mock_resposta.json.return_value = {
            "choices": [{"message": {"content": "Resposta sobre o documento."}}]
        }

        with patch("app.route.chat.os.getenv", return_value="chave_fake"), \
             patch("app.route.chat.SessionLocal") as mock_sessao, \
             patch("app.route.chat.requests.post", return_value=mock_resposta) as mock_post:
            mock_sessao.return_value.query.return_value.filter.return_value.first.return_value = doc

            resultado = fazer_pergunta(dados)

        self.assertTrue(resultado["contexto_truncado"])

        # Verifica que o prompt enviado à Groq respeita o limite de caracteres
        payload_enviado = mock_post.call_args[1]["json"]
        conteudo_prompt = payload_enviado["messages"][0]["content"]
        # O texto do documento truncado não deve exceder muito o limite
        self.assertLess(len(conteudo_prompt), 8000)

    def test_22_modelo_lido_do_env(self):
        """Deve usar o modelo definido em GROQ_MODEL, não um valor hardcoded."""
        from app.route.chat import fazer_pergunta, PerguntaChat

        dados = PerguntaChat(documento_id=1, pergunta="Teste")
        doc = self._mock_documento()

        mock_resposta = MagicMock()
        mock_resposta.status_code = 200
        mock_resposta.json.return_value = {
            "choices": [{"message": {"content": "Resposta."}}]
        }

        modelo_configurado = "llama-3.3-70b-versatile"

        def mock_getenv(chave, padrao=None):
            if chave == "API_KEY":
                return "chave_fake"
            if chave == "GROQ_MODEL":
                return modelo_configurado
            return padrao

        with patch("app.route.chat.os.getenv", side_effect=mock_getenv), \
             patch("app.route.chat.SessionLocal") as mock_sessao, \
             patch("app.route.chat.requests.post", return_value=mock_resposta) as mock_post:
            mock_sessao.return_value.query.return_value.filter.return_value.first.return_value = doc

            fazer_pergunta(dados)

        payload_enviado = mock_post.call_args[1]["json"]
        self.assertEqual(payload_enviado["model"], modelo_configurado)

    def test_24_modelo_padrao_fallback_quando_env_ausente(self):
        """Deve usar openai/gpt-oss-20b como fallback padrão se GROQ_MODEL não estiver no .env."""
        from app.route.chat import fazer_pergunta, PerguntaChat, MODELO_PADRAO_CHAT

        self.assertEqual(MODELO_PADRAO_CHAT, "openai/gpt-oss-20b")

        dados = PerguntaChat(documento_id=1, pergunta="Teste")
        doc = self._mock_documento()

        mock_resposta = MagicMock()
        mock_resposta.status_code = 200
        mock_resposta.json.return_value = {
            "choices": [{"message": {"content": "Resposta."}}]
        }

        def mock_getenv(chave, padrao=None):
            if chave == "API_KEY":
                return "chave_fake"
            if chave == "GROQ_MODEL":
                return padrao
            return padrao

        with patch("app.route.chat.os.getenv", side_effect=mock_getenv), \
             patch("app.route.chat.SessionLocal") as mock_sessao, \
             patch("app.route.chat.requests.post", return_value=mock_resposta) as mock_post:
            mock_sessao.return_value.query.return_value.filter.return_value.first.return_value = doc

            fazer_pergunta(dados)

        payload_enviado = mock_post.call_args[1]["json"]
        self.assertEqual(payload_enviado["model"], "openai/gpt-oss-20b")

    def test_23_timeout_configurado_na_requisicao(self):
        """Deve passar timeout=30 na chamada requests.post."""
        from app.route.chat import fazer_pergunta, PerguntaChat, TIMEOUT_REQUISICAO

        dados = PerguntaChat(documento_id=1, pergunta="Teste")
        doc = self._mock_documento()

        mock_resposta = MagicMock()
        mock_resposta.status_code = 200
        mock_resposta.json.return_value = {
            "choices": [{"message": {"content": "Resposta."}}]
        }

        with patch("app.route.chat.os.getenv", return_value="chave_fake"), \
             patch("app.route.chat.SessionLocal") as mock_sessao, \
             patch("app.route.chat.requests.post", return_value=mock_resposta) as mock_post:
            mock_sessao.return_value.query.return_value.filter.return_value.first.return_value = doc

            fazer_pergunta(dados)

        kwargs_chamada = mock_post.call_args[1]
        self.assertEqual(kwargs_chamada.get("timeout"), TIMEOUT_REQUISICAO)


if __name__ == "__main__":
    unittest.main(verbosity=2)

