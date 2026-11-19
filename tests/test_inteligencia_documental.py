"""
HEMADA - Testes Automatizados da Inteligência Documental (Etapa 2)
Testa validações de arquivo PDF, extração com PyMuPDF, divisão em partes de 6.000 caracteres,
consolidação em Python das 8 categorias, retry automático em HTTP 429 e falha persistente.
Utiliza mocks para simular as respostas da Groq sem consumir créditos da API.
"""

import unittest
from unittest.mock import patch, MagicMock
import os
import json
import pymupdf
from fastapi import HTTPException

from app.route.upload import (
    validar_arquivo_pdf,
    extrair_texto_pdf,
    dividir_texto_em_partes,
    consolidar_listas,
    consolidar_analises_em_python,
    analisar_documento_com_ia,
    formatar_analise_para_texto,
    TAMANHO_MAXIMO_BYTES,
    LIMITE_CARACTERES_PARTE,
    CAMPOS_OBRIGATORIOS
)


class TestInteligenciaDocumental(unittest.TestCase):

    def criar_pdf_em_memoria(self, texto: str = "") -> bytes:
        """Utilitário para gerar um PDF válido em memória usando PyMuPDF."""
        doc = pymupdf.open()
        pagina = doc.new_page()
        if texto:
            pagina.insert_text((50, 72), texto)
        pdf_bytes = doc.tobytes()
        doc.close()
        return pdf_bytes

    # 1. Envio de arquivo que não seja PDF
    def test_01_arquivo_nao_pdf(self):
        with self.assertRaises(HTTPException) as contexto:
            validar_arquivo_pdf("planilha.xlsx", b"%PDF-1.4 conteudo")
        self.assertEqual(contexto.exception.status_code, 400)
        self.assertIn("Apenas arquivos PDF (.pdf) são aceitos", contexto.exception.detail)

    # 2. Envio de arquivo vazio (0 bytes)
    def test_02_arquivo_vazio(self):
        with self.assertRaises(HTTPException) as contexto:
            validar_arquivo_pdf("documento.pdf", b"")
        self.assertEqual(contexto.exception.status_code, 400)
        self.assertIn("vazio (0 bytes)", contexto.exception.detail)

    # 3. Envio de arquivo acima de 10 MB
    def test_03_arquivo_acima_10mb(self):
        conteudo_gigante = b"%PDF-" + b"0" * (TAMANHO_MAXIMO_BYTES + 10)
        with self.assertRaises(HTTPException) as contexto:
            validar_arquivo_pdf("documento_pesado.pdf", conteudo_gigante)
        self.assertEqual(contexto.exception.status_code, 400)
        self.assertIn("excede o limite máximo permitido de 10 MB", contexto.exception.detail)

    # 4. Envio de arquivo sem cabeçalho PDF válido
    def test_04_pdf_cabecalho_invalido(self):
        with self.assertRaises(HTTPException) as contexto:
            validar_arquivo_pdf("falso.pdf", b"ISSO NAO E UM PDF")
        self.assertEqual(contexto.exception.status_code, 400)
        self.assertIn("não é um documento PDF válido", contexto.exception.detail)

    # 5. Envio de PDF corrompido
    def test_05_pdf_corrompido(self):
        pdf_corrompido = b"%PDF-1.4\n%%EOF\nLIXO_CORROMPIDO_SEM_ESTRUTURA"
        with self.assertRaises(HTTPException) as contexto:
            extrair_texto_pdf(pdf_corrompido)
        self.assertEqual(contexto.exception.status_code, 400)
        self.assertIn("corrompido", contexto.exception.detail)

    # 6. PDF sem texto extraível (simulando imagem ou documento em branco)
    def test_06_pdf_sem_texto_extraivel(self):
        pdf_em_branco = self.criar_pdf_em_memoria(texto="")
        with self.assertRaises(HTTPException) as contexto:
            extrair_texto_pdf(pdf_em_branco)
        self.assertEqual(contexto.exception.status_code, 400)
        self.assertIn("não contém texto selecionável", contexto.exception.detail)

    # 7. Extração correta de texto do PDF
    def test_07_extracao_texto_sucesso(self):
        texto_original = "Contrato de Prestacao de Servicos entre Alfa e Beta."
        pdf_valido = self.criar_pdf_em_memoria(texto=texto_original)
        texto_extraido, total_paginas = extrair_texto_pdf(pdf_valido)
        self.assertEqual(total_paginas, 1)
        self.assertIn("Contrato de Prestacao de Servicos", texto_extraido)

    # 8. Teste de divisão de texto em partes de 6.000 caracteres
    def test_08_divisao_texto_em_partes_6000(self):
        self.assertEqual(LIMITE_CARACTERES_PARTE, 6000)
        # Cria um texto com ~15.000 caracteres
        paragrafo = "Este é um parágrafo longo de contrato contendo termos jurídicos detalhados.\n\n"
        texto_longo = paragrafo * 200
        partes = dividir_texto_em_partes(texto_longo, tamanho_maximo=6000)
        self.assertTrue(len(partes) >= 2, "Deveria ter gerado pelo menos 2 partes.")
        for p in partes:
            self.assertTrue(len(p) <= 6500, "Nenhuma parte deve exceder excessivamente os 6.000 caracteres.")

    # 9. Teste de consolidação de listas sem duplicatas e sem perder dados
    def test_09_consolidacao_listas_sem_duplicatas(self):
        analises = [
            {"datas_identificadas": ["10/05/2026", "15/06/2026"], "valores_monetarios": ["R$ 10.000,00"]},
            {"datas_identificadas": ["10/05/2026", "20/07/2026", "Não identificado no documento"], "valores_monetarios": ["R$ 5.000,00", "R$ 10.000,00"]}
        ]
        datas = consolidar_listas(analises, "datas_identificadas")
        valores = consolidar_listas(analises, "valores_monetarios")

        self.assertEqual(len(datas), 3)
        self.assertIn("10/05/2026", datas)
        self.assertIn("15/06/2026", datas)
        self.assertIn("20/07/2026", datas)
        self.assertNotIn("Não identificado no documento", datas)

        self.assertEqual(len(valores), 2)
        self.assertIn("R$ 10.000,00", valores)
        self.assertIn("R$ 5.000,00", valores)

    # 10. Teste de consolidação em Python das oito categorias
    def test_10_consolidacao_em_python_oito_categorias(self):
        p1 = {
            "resumo_geral": "Contrato de locação comercial celebrado entre as partes.",
            "assunto_principal": "Locação comercial",
            "informacoes_importantes": ["Imóvel em São Paulo"],
            "datas_identificadas": ["01/02/2026"],
            "valores_monetarios": ["R$ 12.000,00"],
            "pessoas_e_empresas": ["Empresa Alfa S.A."],
            "pendencias": ["Entregar alvará"],
            "pontos_de_atencao": ["Multa por atraso"]
        }
        p2 = {
            "resumo_geral": "Cláusulas de garantia e rescisão antecipada.",
            "assunto_principal": "Garantias locatícias",
            "informacoes_importantes": ["Seguro fiança aprovado"],
            "datas_identificadas": ["15/03/2026"],
            "valores_monetarios": ["R$ 36.000,00"],
            "pessoas_e_empresas": ["Empresa Beta Ltda."],
            "pendencias": ["Renovar seguro anualmente"],
            "pontos_de_atencao": ["Rescisão imotivada"]
        }

        consolidado = consolidar_analises_em_python([p1, p2])

        # Verifica preservação de todas as 8 categorias
        for campo in CAMPOS_OBRIGATORIOS:
            self.assertIn(campo, consolidado)

        # Verifica preservação de informações das duas partes sem perdas
        self.assertIn("Contrato de locação", consolidado["resumo_geral"])
        self.assertIn("Cláusulas de garantia", consolidado["resumo_geral"])
        self.assertIn("Locação comercial / Garantias locatícias", consolidado["assunto_principal"])
        self.assertEqual(len(consolidado["informacoes_importantes"]), 2)
        self.assertEqual(len(consolidado["datas_identificadas"]), 2)
        self.assertEqual(len(consolidado["valores_monetarios"]), 2)
        self.assertEqual(len(consolidado["pessoas_e_empresas"]), 2)
        self.assertEqual(len(consolidado["pendencias"]), 2)
        self.assertEqual(len(consolidado["pontos_de_atencao"]), 2)

    # 11. Processamento de documento pequeno (chamada única direta)
    @patch.dict(os.environ, {"API_KEY": "gsk_teste"})
    @patch("requests.post")
    def test_11_documento_pequeno_chamada_unica(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{
                "message": {
                    "content": json.dumps({
                        "resumo_geral": "Resumo de documento curto.",
                        "assunto_principal": "Contrato simples",
                        "informacoes_importantes": ["Valor R$ 1.000,00"],
                        "datas_identificadas": ["01/01/2026"],
                        "valores_monetarios": ["R$ 1.000,00"],
                        "pessoas_e_empresas": ["Empresa A"],
                        "pendencias": [],
                        "pontos_de_atencao": []
                    })
                }
            }]
        }
        mock_post.return_value = mock_resp

        resultado = analisar_documento_com_ia("Texto curto com poucas palavras.")
        # Deve ter feito exatamente 1 chamada HTTP à Groq
        self.assertEqual(mock_post.call_count, 1)
        self.assertEqual(resultado["resumo_geral"], "Resumo de documento curto.")
        self.assertEqual(resultado["assunto_principal"], "Contrato simples")

    # 12. Processamento de documento extenso com múltiplas partes e consolidação
    @patch.dict(os.environ, {"API_KEY": "gsk_teste"})
    @patch("app.route.upload.LIMITE_CARACTERES_PARTE", 40)
    @patch("app.route.upload.PAUSA_ENTRE_PARTES_SEGUNDOS", 0.01)
    @patch("requests.post")
    def test_12_documento_extenso_multiplas_partes(self, mock_post):
        mock_resp_parte1 = MagicMock()
        mock_resp_parte1.status_code = 200
        mock_resp_parte1.json.return_value = {
            "choices": [{"message": {"content": json.dumps({
                "resumo_geral": "Parte 1: contratação de serviços.",
                "assunto_principal": "Prestação de serviços",
                "informacoes_importantes": ["Item da parte 1"],
                "datas_identificadas": ["10/01/2026"],
                "valores_monetarios": ["R$ 5.000,00"],
                "pessoas_e_empresas": ["Empresa A"],
                "pendencias": ["Entregar certidão"],
                "pontos_de_atencao": []
            })}}]
        }

        mock_resp_parte2 = MagicMock()
        mock_resp_parte2.status_code = 200
        mock_resp_parte2.json.return_value = {
            "choices": [{"message": {"content": json.dumps({
                "resumo_geral": "Parte 2: cláusulas rescisórias.",
                "assunto_principal": "Cláusulas do contrato",
                "informacoes_importantes": ["Item da parte 2"],
                "datas_identificadas": ["20/02/2026"],
                "valores_monetarios": ["R$ 1.000,00"],
                "pessoas_e_empresas": ["Empresa B"],
                "pendencias": [],
                "pontos_de_atencao": ["Multa de 10%"]
            })}}]
        }

        mock_post.side_effect = [mock_resp_parte1, mock_resp_parte2]

        texto_longo = "Primeira secao do documento.\n\nSegunda secao do documento."
        resultado = analisar_documento_com_ia(texto_longo)

        # 2 partes analisadas via IA e consolidadas em Python (custo zero de chamada adicional)
        self.assertEqual(mock_post.call_count, 2)
        self.assertIn("Parte 1", resultado["resumo_geral"])
        self.assertIn("Parte 2", resultado["resumo_geral"])
        self.assertIn("10/01/2026", resultado["datas_identificadas"])
        self.assertIn("20/02/2026", resultado["datas_identificadas"])
        self.assertIn("R$ 5.000,00", resultado["valores_monetarios"])
        self.assertIn("R$ 1.000,00", resultado["valores_monetarios"])
        self.assertIn("Empresa A", resultado["pessoas_e_empresas"])
        self.assertIn("Empresa B", resultado["pessoas_e_empresas"])

    # 13. Simulação de HTTP 429 com recuperação automática (Retry bem-sucedido)
    @patch.dict(os.environ, {"API_KEY": "gsk_teste"})
    @patch("time.sleep")  # Mock do time.sleep para o teste ser instantâneo
    @patch("requests.post")
    def test_13_simulacao_429_com_recuperacao_automatica_retry(self, mock_post, mock_sleep):
        # Tentativa 1: Groq responde 429 informando para aguardar 2 segundos
        mock_429 = MagicMock()
        mock_429.status_code = 429
        mock_429.headers = {"x-ratelimit-reset-tokens": "2.0s"}
        mock_429.json.return_value = {
            "error": {"message": "Rate limit reached on TPM. Limit: 8,000. Please try again in 2.0s."}
        }

        # Tentativa 2: Groq responde 200 com sucesso após a espera
        mock_200 = MagicMock()
        mock_200.status_code = 200
        mock_200.json.return_value = {
            "choices": [{"message": {"content": json.dumps({
                "resumo_geral": "Sucesso após recuperação automática de rate limit.",
                "assunto_principal": "Recuperação 429",
                "informacoes_importantes": ["Retry com sucesso"],
                "datas_identificadas": [],
                "valores_monetarios": [],
                "pessoas_e_empresas": [],
                "pendencias": [],
                "pontos_de_atencao": []
            })}}]
        }

        mock_post.side_effect = [mock_429, mock_200]

        resultado = analisar_documento_com_ia("Texto de teste com retry.")

        # Deve ter tentado 2 vezes e recuperado sem erro
        self.assertEqual(mock_post.call_count, 2)
        mock_sleep.assert_called()  # Verificou que o sleep foi executado
        self.assertEqual(resultado["resumo_geral"], "Sucesso após recuperação automática de rate limit.")

    # 14. Simulação de HTTP 429 com falha persistente após esgotar o limite de tentativas
    @patch.dict(os.environ, {"API_KEY": "gsk_teste"})
    @patch("time.sleep")
    @patch("requests.post")
    def test_14_simulacao_429_falha_persistente_apos_limite(self, mock_post, mock_sleep):
        # Todas as 3 tentativas retornam 429
        mock_429 = MagicMock()
        mock_429.status_code = 429
        mock_429.headers = {"retry-after": "5"}
        mock_429.json.return_value = {
            "error": {"message": "Rate limit reached on TPM. Limit: 8,000."}
        }
        mock_post.return_value = mock_429

        with self.assertRaises(HTTPException) as contexto:
            analisar_documento_com_ia("Texto de teste com falha persistente.")

        self.assertEqual(contexto.exception.status_code, 429)
        self.assertIn("8.000 tokens/min", contexto.exception.detail)
        self.assertIn("tentativas automáticas de espera", contexto.exception.detail)
        self.assertEqual(mock_post.call_count, 3)  # Fez as 3 tentativas antes de falhar

    # 15. Tratamento de Erro HTTP 401 (Autenticação inválida)
    @patch.dict(os.environ, {"API_KEY": "gsk_invalida"})
    @patch("requests.post")
    def test_15_erro_401_autenticacao(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_post.return_value = mock_resp

        with self.assertRaises(HTTPException) as contexto:
            analisar_documento_com_ia("Texto qualquer")
        self.assertEqual(contexto.exception.status_code, 401)
        self.assertIn("Falha de autenticação", contexto.exception.detail)

    # 16. Tratamento de Erro HTTP 404 (Modelo não encontrado)
    @patch.dict(os.environ, {"API_KEY": "gsk_teste"})
    @patch("requests.post")
    def test_16_erro_404_modelo_nao_encontrado(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_post.return_value = mock_resp

        with self.assertRaises(HTTPException) as contexto:
            analisar_documento_com_ia("Texto qualquer")
        self.assertEqual(contexto.exception.status_code, 404)
        self.assertIn("GROQ_MODEL", contexto.exception.detail)

    # 17. Tratamento de Erro HTTP 413 (Payload muito extenso)
    @patch.dict(os.environ, {"API_KEY": "gsk_teste"})
    @patch("requests.post")
    def test_17_erro_413_payload_extenso(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 413
        mock_post.return_value = mock_resp

        with self.assertRaises(HTTPException) as contexto:
            analisar_documento_com_ia("Texto qualquer")
        self.assertEqual(contexto.exception.status_code, 413)
        self.assertIn("Erro 413", contexto.exception.detail)

    # 18. Tratamento de Erro HTTP 503 (Servidores da Groq indisponíveis)
    @patch.dict(os.environ, {"API_KEY": "gsk_teste"})
    @patch("requests.post")
    def test_18_erro_503_servidor_indisponivel(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 503
        mock_post.return_value = mock_resp

        with self.assertRaises(HTTPException) as contexto:
            analisar_documento_com_ia("Texto qualquer")
        self.assertEqual(contexto.exception.status_code, 503)
        self.assertIn("temporariamente indisponíveis", contexto.exception.detail)

    # 19. Tratamento de chave de API ausente no .env
    @patch.dict(os.environ, {}, clear=True)
    def test_19_chave_api_ausente(self):
        with self.assertRaises(HTTPException) as contexto:
            analisar_documento_com_ia("Texto qualquer")
        self.assertEqual(contexto.exception.status_code, 500)
        self.assertIn("Chave de API da Groq não configurada", contexto.exception.detail)

    # 20. Tratamento de falha de conexão de rede
    @patch.dict(os.environ, {"API_KEY": "gsk_teste"})
    @patch("requests.post")
    def test_20_falha_conexao_rede(self, mock_post):
        import requests
        mock_post.side_effect = requests.exceptions.ConnectionError("Sem internet")
        with self.assertRaises(HTTPException) as contexto:
            analisar_documento_com_ia("Texto qualquer")
        self.assertEqual(contexto.exception.status_code, 502)
        self.assertIn("Falha de conexão com os servidores da Groq", contexto.exception.detail)

    # 21. Validação e formatação dos 8 campos para exibição no front-end
    def test_21_validacao_estrutura_e_formatacao(self):
        analise_mock = {
            "resumo_geral": "Contrato de prestação de serviços de TI.",
            "assunto_principal": "Desenvolvimento de Software",
            "informacoes_importantes": ["Prazo de 6 meses", "Garantia de 90 dias"],
            "datas_identificadas": ["01/06/2026"],
            "valores_monetarios": ["R$ 15.000,00"],
            "pessoas_e_empresas": ["Empresa ABC Ltda", "Dev Marcos"],
            "pendencias": ["Assinatura do fiador"],
            "pontos_de_atencao": ["Multa de 10% por atraso"]
        }

        texto_formatado = formatar_analise_para_texto(analise_mock)
        self.assertIn("📋 RESUMO GERAL:", texto_formatado)
        self.assertIn("📌 ASSUNTO PRINCIPAL:", texto_formatado)
        self.assertIn("⭐ INFORMAÇÕES IMPORTANTES:", texto_formatado)
        self.assertIn("• Prazo de 6 meses", texto_formatado)
        self.assertIn("📅 DATAS IDENTIFICADAS:", texto_formatado)
        self.assertIn("💰 VALORES MONETÁRIOS:", texto_formatado)
        self.assertIn("👥 PESSOAS E EMPRESAS:", texto_formatado)
        self.assertIn("⚠️ PENDÊNCIAS:", texto_formatado)
        self.assertIn("🔍 PONTOS DE ATENÇÃO:", texto_formatado)


if __name__ == "__main__":
    unittest.main()
