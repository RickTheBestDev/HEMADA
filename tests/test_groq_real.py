"""
HEMADA - Teste de Integração Real com a API da Groq (Etapa 2)
Este teste realiza requisições reais à API da Groq para validar:
1. Documento padrão (chamada direta).
2. Documento extenso (processamento em partes com consolidação e síntese).
"""

import os
import unittest
import pymupdf
from dotenv import load_dotenv

# Carrega variáveis do arquivo .env
load_dotenv()

from app.route.upload import (
    validar_arquivo_pdf,
    extrair_texto_pdf,
    analisar_documento_com_ia,
    formatar_analise_para_texto
)


class TestGroqIntegracaoReal(unittest.TestCase):

    def setUp(self):
        self.chave_api = os.getenv("API_KEY")
        if not self.chave_api:
            self.skipTest("Chave API_KEY não configurada no .env. Teste real pulado.")

        # Verifica conectividade de rede com a API da Groq
        import socket
        try:
            socket.getaddrinfo("api.groq.com", 443)
        except OSError:
            self.skipTest("Sem acesso à internet ou api.groq.com inacessível. Teste de integração real pulado.")

    def test_01_integracao_real_groq_documento_padrao(self):
        """Testa o processamento direto de um PDF padrão de uma página."""
        doc = pymupdf.open()
        pagina = doc.new_page()
        texto_documento = (
            "CONTRATO DE PRESTAÇÃO DE SERVIÇOS Nº 102/2026\n"
            "Contratante: Escola Técnica Futuro Digital Ltda.\n"
            "Contratada: Softwares e Redes Brasil S.A.\n"
            "Data de assinatura: 20 de fevereiro de 2026.\n"
            "Objeto: Manutenção preventiva e suporte aos servidores de banco de dados.\n"
            "Valor do contrato: R$ 36.000,00 divididos em 12 parcelas mensais de R$ 3.000,00.\n"
            "Pendências: A Contratada deve apresentar a apólice de seguro até 10 de março de 2026.\n"
            "Ponto de atenção: Multa rescisória de 20% em caso de rescisão imotivada antes de 6 meses.\n"
            "Representante legal: Juliana Martins Pereira."
        )
        pagina.insert_text((50, 72), texto_documento)
        pdf_bytes = doc.tobytes()
        doc.close()

        validar_arquivo_pdf("contrato_teste.pdf", pdf_bytes)
        texto_extraido, total_paginas = extrair_texto_pdf(pdf_bytes)
        self.assertEqual(total_paginas, 1)

        analise = analisar_documento_com_ia(texto_extraido)

        campos_obrigatorios = [
            "resumo_geral",
            "assunto_principal",
            "informacoes_importantes",
            "datas_identificadas",
            "valores_monetarios",
            "pessoas_e_empresas",
            "pendencias",
            "pontos_de_atencao"
        ]
        for campo in campos_obrigatorios:
            self.assertIn(campo, analise, f"Campo obrigatório '{campo}' ausente!")

        self.assertTrue(len(analise["resumo_geral"]) > 20)
        self.assertTrue(len(analise["assunto_principal"]) > 5)

        texto_formatado = formatar_analise_para_texto(analise)
        self.assertIn("📋 RESUMO GERAL:", texto_formatado)
        self.assertIn("📌 ASSUNTO PRINCIPAL:", texto_formatado)

    def test_02_integracao_real_documento_extenso_com_partes(self):
        """Testa o processamento em partes e consolidação de um documento com mais de 12.000 caracteres."""
        doc = pymupdf.open()

        # Páginas 1 a 4: Seção de locação e dados contratuais
        for i in range(1, 5):
            p = doc.new_page()
            p.insert_text((50, 50), f"CONTRATO DE LOCAÇÃO COMERCIAL - PÁGINA {i}")
            p.insert_text((50, 80), "Locador: Empreendimentos Comerciais Paulista S.A.")
            p.insert_text((50, 110), "Locatário: Padaria e Confeitaria Estrela do Bairro Ltda.")
            p.insert_text((50, 140), "Data da celebração: 15 de janeiro de 2026.")
            p.insert_text((50, 170), "Valor do aluguel: R$ 12.000,00 por mês.")
            for y in range(200, 750, 25):
                p.insert_text((50, y), "Cláusula detalhada sobre conservação, manutenções periódicas e vistorias comerciais.")

        # Páginas 5 a 8: Seção de garantias, fiador e multas
        for i in range(5, 9):
            p = doc.new_page()
            p.insert_text((50, 50), f"CONTRATO DE LOCAÇÃO COMERCIAL - GARANTIAS - PÁGINA {i}")
            p.insert_text((50, 80), "Garantia locatícia: Seguro fiança no valor de R$ 36.000,00.")
            p.insert_text((50, 110), "Fiador solidário: Roberto Carlos de Oliveira.")
            p.insert_text((50, 140), "Pendência: Apresentar a renovação anual da apólice até 15 de dezembro de cada ano.")
            p.insert_text((50, 170), "Ponto de atenção: Multa penal de 3 aluguéis vigentes em caso de rescisão antecipada.")
            for y in range(200, 750, 25):
                p.insert_text((50, y), "Disposições finais regulatórias, foro de eleição da Comarca de São Paulo e normas condominiais.")

        pdf_bytes = doc.tobytes()
        doc.close()

        validar_arquivo_pdf("documento_extenso.pdf", pdf_bytes)
        texto_extraido, total_paginas = extrair_texto_pdf(pdf_bytes)
        self.assertEqual(total_paginas, 8)
        self.assertTrue(len(texto_extraido) > 12000, f"Texto com {len(texto_extraido)} chars deveria ser > 12.000.")

        # Executa análise (disparará divisão em partes e consolidação automática)
        analise = analisar_documento_com_ia(texto_extraido)

        campos_obrigatorios = [
            "resumo_geral",
            "assunto_principal",
            "informacoes_importantes",
            "datas_identificadas",
            "valores_monetarios",
            "pessoas_e_empresas",
            "pendencias",
            "pontos_de_atencao"
        ]
        for campo in campos_obrigatorios:
            self.assertIn(campo, analise)

        self.assertTrue(len(analise["resumo_geral"]) > 20)
        self.assertTrue(any("12.000" in str(v) or "36.000" in str(v) for v in analise["valores_monetarios"]))
        self.assertTrue(any("Paulista" in str(p) or "Estrela" in str(p) or "Roberto" in str(p) for p in analise["pessoas_e_empresas"]))


if __name__ == "__main__":
    unittest.main()
