# HEMADA — Sistema de Inteligência Documental

Sistema web para upload, extração de texto de documentos PDF, processamento por inteligência artificial (Groq API) e persistência de dados. Projeto desenvolvido para o Trabalho de Conclusão de Curso (TCC) de Análise e Desenvolvimento de Sistemas (ADS).

## Integrantes
- Mario Oliveira
- Henrique Smomcovitz
- Davi Joaquim

## Tecnologias
- **Linguagem:** Python 3.12+
- **Back-end:** FastAPI, Uvicorn
- **Extração de Texto:** PyMuPDF
- **Inteligência Artificial:** Groq API (LLaMA 3.1)
- **Banco de Dados:** SQLite com SQLAlchemy ORM
- **Front-end:** HTML5, CSS3, JavaScript (Vanilla)

## Configuração do Ambiente

1. **Ative o ambiente virtual:**
   ```powershell
   .\.venv\Scripts\Activate.ps1
   ```

2. **Instale as dependências:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure as variáveis de ambiente:**
   Copie o arquivo `.env.example` para `.env` e insira sua chave da Groq:
   ```env
   API_KEY=sua_chave_groq_aqui
   ```

## Como Executar

Inicie o servidor localmente com o comando:
```bash
uvicorn app.main:app --reload
```

Acesse no navegador:
- **Aplicação Web:** [http://127.0.0.1:8000](http://127.0.0.1:8000)
- **Documentação da API (Swagger):** [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
