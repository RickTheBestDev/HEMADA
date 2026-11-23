# Arquivo: tests/test_rotas_app.py
"""
Testes automatizados das rotas principais e integridade do app HEMADA.
Valida status da API (/health), rotas de histórico e integração de static files.
"""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.main import app, verificar_status
from app.route.historico import listar_historico, apagar_historico
from app.model.documento import Documento


class TestRotasApp(unittest.TestCase):
    """Testa endpoints e componentes principais da aplicação FastAPI."""

    def test_01_rota_health(self):
        """A rota de health check deve retornar status ok e nome do projeto."""
        resposta = verificar_status()
        self.assertEqual(resposta.get("status"), "ok")
        self.assertEqual(resposta.get("projeto"), "HEMADA")

    def test_02_listar_historico(self):
        """A rota /historico/ deve retornar a lista de documentos do SQLite."""
        mock_doc = MagicMock()
        mock_doc.id = 1
        mock_doc.nome_arquivo = "contrato.pdf"

        with patch("app.route.historico.SessionLocal") as mock_sessao:
            mock_sessao.return_value.query.return_value.all.return_value = [mock_doc]
            documentos = listar_historico()

            self.assertEqual(len(documentos), 1)
            self.assertEqual(documentos[0].nome_arquivo, "contrato.pdf")
            mock_sessao.return_value.close.assert_called_once()

    def test_03_apagar_historico(self):
        """A rota /limpar-historico/ deve executar a limpeza no SQLite."""
        with patch("app.route.historico.SessionLocal") as mock_sessao:
            resposta = apagar_historico()

            self.assertEqual(resposta.get("status"), "Histórico apagado")
            mock_sessao.return_value.query.return_value.delete.assert_called_once()
            mock_sessao.return_value.commit.assert_called_once()
            mock_sessao.return_value.close.assert_called_once()

    def test_04_arquivos_estaticos_existem(self):
        """Garante que os arquivos do frontend estão presentes e acessíveis."""
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        static_dir = os.path.join(base_dir, "static")

        for arq in ["index.html", "style.css", "script.js"]:
            caminho = os.path.join(static_dir, arq)
            self.assertTrue(os.path.exists(caminho), f"Arquivo estático {arq} não encontrado.")
            self.assertGreater(os.path.getsize(caminho), 500, f"Arquivo {arq} parece vazio.")


if __name__ == "__main__":
    unittest.main()

