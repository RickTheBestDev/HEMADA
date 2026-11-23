// ═══════════════════════════════════════════════════════════════
// HEMADA — script.js
// Lógica Completa do Front-End (SPA)
// Módulos: Dashboard, Upload & Análise, Histórico, Chat IA, Modais
// ═══════════════════════════════════════════════════════════════

// ── 1. DEFINIÇÃO DAS 8 CATEGORIAS DOCUMENTAIS ──
const CATEGORIAS_SCHEMA = [
  { chave: "resumo_geral", titulo: "Resumo Geral", icone: "📋", classe: "cat-resumo", tipo: "texto", larga: true },
  { chave: "assunto_principal", titulo: "Assunto Principal", icone: "📌", classe: "cat-assunto", tipo: "texto", larga: true },
  { chave: "informacoes_importantes", titulo: "Informações Importantes", icone: "⭐", classe: "cat-informacoes", tipo: "lista" },
  { chave: "datas_identificadas", titulo: "Datas e Prazos", icone: "📅", classe: "cat-datas", tipo: "lista" },
  { chave: "valores_monetarios", titulo: "Valores Monetários", icone: "💰", classe: "cat-valores", tipo: "lista" },
  { chave: "pessoas_e_empresas", titulo: "Pessoas e Empresas", icone: "👥", classe: "cat-pessoas", tipo: "lista" },
  { chave: "pendencias", titulo: "Pendências Identificadas", icone: "⚠️", classe: "cat-pendencias", tipo: "lista" },
  { chave: "pontos_de_atencao", titulo: "Pontos de Atenção", icone: "🔍", classe: "cat-atencao", tipo: "lista" },
];

// Estado Global da Aplicação
const appEstado = {
  paginaAtiva: "dashboard",
  arquivoSelecionado: null,
  emProcessamentoUpload: false,
  emProcessamentoChat: false,
  documentoAtivoId: null,
  documentoAtivoNome: null,
  ultimoResultadoAnalise: null,
  cacheDocumentos: [],
  termoBuscaHistorico: "",
  ordenacaoHistorico: "recente",
  intervaloProgresso: null,
};

// ══════════════════════════════════════════════════════════════
// 2. INICIALIZAÇÃO DA APLICAÇÃO
// ══════════════════════════════════════════════════════════════
document.addEventListener("DOMContentLoaded", () => {
  configurarNavegacaoSPA();
  configurarUpload();
  configurarHistorico();
  configurarChat();
  configurarModal();

  // Define a tela inicial com base no hash ou padrão
  const hashAtual = window.location.hash.replace("#", "");
  const paginasValidas = ["dashboard", "upload", "historico", "chat"];
  const paginaInicial = paginasValidas.includes(hashAtual) ? hashAtual : "dashboard";
  navegarPara(paginaInicial);
});

// ══════════════════════════════════════════════════════════════
// 3. NAVEGAÇÃO SPA (ROUTING POR HASH)
// ══════════════════════════════════════════════════════════════
function configurarNavegacaoSPA() {
  // Itens do menu
  document.querySelectorAll(".menu-item").forEach(item => {
    item.addEventListener("click", (evento) => {
      evento.preventDefault();
      const pagina = item.dataset.pagina;
      navegarPara(pagina);
      fecharMenuMobile();
    });
  });

  // Botão mobile e overlay
  const btnMenuMobile = document.getElementById("btnMenuMobile");
  const overlayMobile = document.getElementById("overlayMobile");

  if (btnMenuMobile) {
    btnMenuMobile.addEventListener("click", () => {
      const menu = document.getElementById("menuLateral");
      const aberto = menu.classList.toggle("aberto");
      overlayMobile.classList.toggle("oculto", !aberto);
    });
  }

  if (overlayMobile) {
    overlayMobile.addEventListener("click", fecharMenuMobile);
  }

  // Suporte aos botões voltar/avançar do navegador
  window.addEventListener("hashchange", () => {
    const hash = window.location.hash.replace("#", "");
    if (hash && hash !== appEstado.paginaAtiva) {
      navegarPara(hash, false);
    }
  });
}

function fecharMenuMobile() {
  document.getElementById("menuLateral")?.classList.remove("aberto");
  document.getElementById("overlayMobile")?.classList.add("oculto");
}

function navegarPara(pagina, atualizarHash = true) {
  appEstado.paginaAtiva = pagina;

  // Atualiza links do menu lateral
  document.querySelectorAll(".menu-item").forEach(link => {
    link.classList.toggle("ativo", link.dataset.pagina === pagina);
  });

  // Alterna as seções com fade
  document.querySelectorAll(".tela").forEach(secao => secao.classList.add("oculto"));
  const telaAlvo = document.getElementById(`tela${capitalizar(pagina)}`);
  if (telaAlvo) {
    telaAlvo.classList.remove("oculto");
  }

  // Títulos e subtítulos da Topbar
  const metaPaginas = {
    dashboard: {
      titulo: "Dashboard Executivo",
      subtitulo: "Visão analítica e métricas em tempo real do sistema HEMADA",
    },
    upload: {
      titulo: "Análise Documental",
      subtitulo: "Extração textual de PDF e estruturação de inteligência artificial",
    },
    historico: {
      titulo: "Histórico de Documentos",
      subtitulo: "Repositório de análises e documentos persistidos no SQLite",
    },
    chat: {
      titulo: "Assistente de IA",
      subtitulo: "Converse com o conteúdo de qualquer documento analisado",
    },
  };

  const info = metaPaginas[pagina] || { titulo: capitalizar(pagina), subtitulo: "" };
  document.getElementById("tituloPagina").textContent = info.titulo;
  document.getElementById("subtituloPagina").textContent = info.subtitulo;

  // Dispara o carregamento de dados conforme a página
  if (pagina === "dashboard") carregarDashboard();
  if (pagina === "historico") carregarHistorico();
  if (pagina === "chat") carregarDocumentosParaChat();

  if (atualizarHash) {
    history.replaceState(null, "", `#${pagina}`);
  }

  window.scrollTo({ top: 0, behavior: "smooth" });
}

// ══════════════════════════════════════════════════════════════
// 4. MÓDULO DASHBOARD
// ══════════════════════════════════════════════════════════════
async function carregarDashboard() {
  const listaAtividade = document.getElementById("listaAtividadeRecente");
  const elTotalDocs = document.getElementById("totalDocumentos");
  const elTotalPags = document.getElementById("totalPaginas");
  const elMediaPags = document.getElementById("mediaPaginas");

  listaAtividade.innerHTML = `
    <div class="estado-carregando">
      <span class="spinner-inline"></span> Carregando indicadores reais do SQLite...
    </div>`;

  try {
    const docs = await apiRequisicao("/historico/");
    appEstado.cacheDocumentos = docs;

    const totalDocs = docs.length;
    const somaPags = docs.reduce((acc, d) => acc + (d.total_paginas || 0), 0);
    const mediaPags = totalDocs > 0 ? (somaPags / totalDocs).toFixed(1) : "0";

    elTotalDocs.textContent = totalDocs;
    elTotalPags.textContent = somaPags;
    elMediaPags.textContent = mediaPags;

    // Atualiza o gráfico de distribuição
    atualizarGraficoDistribuicao(docs);

    // Renderiza lista de atividades recentes
    renderizarAtividadesRecentes(docs);

  } catch (erro) {
    listaAtividade.innerHTML = `
      <div class="alerta-box alerta-erro">
        ⚠️ Não foi possível carregar os dados do dashboard. Verifique se o servidor FastAPI está ativo.
      </div>`;
    elTotalDocs.textContent = "—";
    elTotalPags.textContent = "—";
    elMediaPags.textContent = "—";
  }
}

function atualizarGraficoDistribuicao(docs) {
  const total = docs.length;
  let curtos = 0;  // 1-5
  let medios = 0;  // 6-15
  let longos = 0;  // > 15

  docs.forEach(d => {
    const p = d.total_paginas || 1;
    if (p <= 5) curtos++;
    else if (p <= 15) medios++;
    else longos++;
  });

  const pctCurtos = total > 0 ? Math.round((curtos / total) * 100) : 0;
  const pctMedios = total > 0 ? Math.round((medios / total) * 100) : 0;
  const pctLongos = total > 0 ? Math.round((longos / total) * 100) : 0;

  document.getElementById("barraDocsCurtos").style.width = `${pctCurtos}%`;
  document.getElementById("labelDocsCurtos").textContent = `${curtos} docs (${pctCurtos}%)`;

  document.getElementById("barraDocsMedios").style.width = `${pctMedios}%`;
  document.getElementById("labelDocsMedios").textContent = `${medios} docs (${pctMedios}%)`;

  document.getElementById("barraDocsLongos").style.width = `${pctLongos}%`;
  document.getElementById("labelDocsLongos").textContent = `${longos} docs (${pctLongos}%)`;
}

function renderizarAtividadesRecentes(docs) {
  const listaAtividade = document.getElementById("listaAtividadeRecente");
  listaAtividade.innerHTML = "";

  if (docs.length === 0) {
    listaAtividade.innerHTML = `
      <div class="estado-vazio">
        <span class="estado-vazio-icone">📂</span>
        <p>Nenhum documento processado até o momento.</p>
        <button class="btn-primario" style="margin-top:12px;" onclick="navegarPara('upload')">
          ⚡ Analisar Primeiro Documento
        </button>
      </div>`;
    return;
  }

  // 5 mais recentes
  const recentes = [...docs].reverse().slice(0, 5);

  recentes.forEach(doc => {
    const item = document.createElement("div");
    item.className = "item-atividade";

    // Extrai prévia do assunto
    const previa = extrairPreviaAssunto(doc.resposta_ia);

    item.innerHTML = `
      <div class="ativ-esquerda">
        <div class="ativ-icone-badge">PDF</div>
        <div class="ativ-textos">
          <div class="ativ-nome" title="${escaparHtml(doc.nome_arquivo)}">${escaparHtml(doc.nome_arquivo)}</div>
          <div class="ativ-meta">
            ${doc.total_paginas} página${doc.total_paginas !== 1 ? "s" : ""} · ${escaparHtml(previa)}
          </div>
        </div>
      </div>
      <div class="ativ-acoes">
        <button class="btn-secundario btn-pequeno btn-ver-ativ">Ver Análise</button>
        <button class="btn-secundario btn-pequeno btn-chat-ativ">💬 Chat</button>
      </div>
    `;

    item.querySelector(".btn-ver-ativ").addEventListener("click", () => abrirModalDocumento(doc));
    item.querySelector(".btn-chat-ativ").addEventListener("click", () => iniciarChatComDocumento(doc.id, doc.nome_arquivo));

    listaAtividade.appendChild(item);
  });
}

function extrairPreviaAssunto(respostaIa) {
  if (!respostaIa) return "Análise estruturada disponível";
  const match = respostaIa.match(/ASSUNTO PRINCIPAL:\s*\n([^\n]+)/i);
  if (match && match[1]) {
    const assunto = match[1].trim();
    return assunto.length > 55 ? assunto.slice(0, 55) + "..." : assunto;
  }
  return "Documento processado com sucesso";
}

// ══════════════════════════════════════════════════════════════
// 5. MÓDULO ANÁLISE DOCUMENTAL (UPLOAD)
// ══════════════════════════════════════════════════════════════
function configurarUpload() {
  const zonaDrop = document.getElementById("zonaDrop");
  const inputArquivo = document.getElementById("inputArquivo");
  const btnRemover = document.getElementById("btnRemoverArquivo");
  const btnEnviar = document.getElementById("btnEnviar");

  // Clique na zona abre seletor nativo
  zonaDrop.addEventListener("click", () => {
    if (!appEstado.emProcessamentoUpload) {
      inputArquivo.click();
    }
  });

  // Drag and Drop com feedbacks visuais
  zonaDrop.addEventListener("dragover", (e) => {
    e.preventDefault();
    zonaDrop.classList.add("arrastando");
  });

  zonaDrop.addEventListener("dragleave", () => {
    zonaDrop.classList.remove("arrastando");
  });

  zonaDrop.addEventListener("drop", (e) => {
    e.preventDefault();
    zonaDrop.classList.remove("arrastando");
    const arquivos = e.dataTransfer.files;
    if (arquivos && arquivos.length > 0) {
      processarSelecaoArquivo(arquivos[0]);
    }
  });

  // Seleção via input file
  inputArquivo.addEventListener("change", () => {
    if (inputArquivo.files && inputArquivo.files.length > 0) {
      processarSelecaoArquivo(inputArquivo.files[0]);
    }
  });

  // Remover arquivo selecionado
  btnRemover.addEventListener("click", (e) => {
    e.stopPropagation();
    limparArquivoUpload();
  });

  // Clique no botão Enviar
  btnEnviar.addEventListener("click", () => {
    if (!appEstado.emProcessamentoUpload && appEstado.arquivoSelecionado) {
      executarUploadDocumento();
    }
  });
}

function processarSelecaoArquivo(arquivo) {
  // Validação no front-end
  if (!arquivo.name.toLowerCase().endsWith(".pdf")) {
    exibirAlerta("msgStatus", "Formato inválido. Por favor, selecione exclusivamente arquivos com extensão .pdf", "erro");
    return;
  }

  const limiteBytes = 10 * 1024 * 1024;
  if (arquivo.size > limiteBytes) {
    exibirAlerta("msgStatus", "Arquivo excede o limite máximo permitido de 10 MB.", "erro");
    return;
  }

  if (arquivo.size === 0) {
    exibirAlerta("msgStatus", "O arquivo selecionado está vazio (0 bytes).", "erro");
    return;
  }

  appEstado.arquivoSelecionado = arquivo;

  // Atualiza preview visual
  document.getElementById("previewNome").textContent = arquivo.name;
  document.getElementById("previewTamanho").textContent = formatarTamanhoBytes(arquivo.size);
  document.getElementById("previewArquivo").classList.remove("oculto");
  document.getElementById("zonaDrop").classList.add("oculto");
  document.getElementById("btnEnviar").disabled = false;

  // Limpa alertas e fecha resultados anteriores
  ocultarElemento("msgStatus");
  ocultarElemento("secaoResultado");
}

function limparArquivoUpload() {
  appEstado.arquivoSelecionado = null;
  document.getElementById("inputArquivo").value = "";
  document.getElementById("previewArquivo").classList.add("oculto");
  document.getElementById("zonaDrop").classList.remove("oculto");
  document.getElementById("btnEnviar").disabled = true;
  ocultarElemento("msgStatus");
  ocultarElemento("progressoProcessamento");
}

async function executarUploadDocumento() {
  if (appEstado.emProcessamentoUpload) return;

  const arquivo = appEstado.arquivoSelecionado;
  const perguntaOpcional = document.getElementById("inputPergunta").value.trim();

  // Trava a interface contra cliques duplos
  appEstado.emProcessamentoUpload = true;
  alternarSpinnerBotao("btnEnviar", "spinnerEnvio", "btnEnviarTexto", true, "Processando com IA...");
  ocultarElemento("msgStatus");
  ocultarElemento("secaoResultado");

  // Inicia o stepper de progresso visual
  iniciarStepperProgresso();

  const formData = new FormData();
  formData.append("arquivo", arquivo);
  if (perguntaOpcional) {
    formData.append("pergunta", perguntaOpcional);
  }

  try {
    const resposta = await fetch("/uploads/", {
      method: "POST",
      body: formData,
    });

    const dados = await resposta.json();

    if (!resposta.ok) {
      throw new Error(dados.detail || `Erro HTTP ${resposta.status}`);
    }

    finalizarStepperProgresso(true);

    // Sucesso!
    appEstado.ultimoResultadoAnalise = dados;
    appEstado.documentoAtivoId = dados.documento_id;
    appEstado.documentoAtivoNome = dados.arquivo;

    exibirAlerta("msgStatus", `Documento processado com êxito! ${dados.total_paginas} página(s) analisada(s) e persistida(s).`, "sucesso");
    exibirToast("Análise documental concluída com sucesso!", "✓");

    // Renderiza o resultado na tela
    renderizarResultadoAnalise(dados);

    // Invalida o cache para recarregar histórico e dashboard
    appEstado.cacheDocumentos = [];

  } catch (erro) {
    finalizarStepperProgresso(false);
    exibirAlerta("msgStatus", `Falha no processamento: ${erro.message}`, "erro");
  } finally {
    appEstado.emProcessamentoUpload = false;
    alternarSpinnerBotao("btnEnviar", "spinnerEnvio", "btnEnviarTexto", false, "Iniciar Inteligência Documental");
  }
}

function iniciarStepperProgresso() {
  const container = document.getElementById("progressoProcessamento");
  const textoStatus = document.getElementById("textoStatusProgresso");
  container.classList.remove("oculto");

  const etapas = [
    { id: "etapa1", texto: "Validando integridade e formato PDF..." },
    { id: "etapa2", texto: "Extraindo texto de todas as páginas com PyMuPDF..." },
    { id: "etapa3", texto: "Processando análise cognitiva via Groq API..." },
    { id: "etapa4", texto: "Estruturando categorias e persistindo no SQLite..." },
  ];

  let indice = 0;
  textoStatus.textContent = etapas[0].texto;

  // Atualiza as etapas a cada intervalo
  appEstado.intervaloProgresso = setInterval(() => {
    if (indice < etapas.length - 1) {
      indice++;
      document.querySelectorAll(".etapa-item").forEach((el, idx) => {
        el.classList.toggle("ativa", idx <= indice);
      });
      textoStatus.textContent = etapas[indice].texto;
    }
  }, 2200);
}

function finalizarStepperProgresso(sucesso) {
  if (appEstado.intervaloProgresso) {
    clearInterval(appEstado.intervaloProgresso);
    appEstado.intervaloProgresso = null;
  }

  const container = document.getElementById("progressoProcessamento");
  if (sucesso) {
    document.querySelectorAll(".etapa-item").forEach(el => el.classList.add("ativa"));
    setTimeout(() => {
      container.classList.add("oculto");
    }, 800);
  } else {
    container.classList.add("oculto");
  }
}

function renderizarResultadoAnalise(dados) {
  const analise = dados.analise_estruturada || {};

  document.getElementById("resultadoNomeArquivo").textContent = dados.arquivo || "Documento";
  document.getElementById("resultadoPaginas").textContent = `${dados.total_paginas} página${dados.total_paginas !== 1 ? "s" : ""}`;
  document.getElementById("resultadoHora").textContent = `Processado em ${new Date().toLocaleTimeString("pt-BR")}`;

  // Preenche texto completo
  document.getElementById("relatorioTextoConteudo").textContent = dados.resposta_ia || "Sem análise textual.";

  // Preenche os 8 cards
  const grade = document.getElementById("gradeCategorias");
  grade.innerHTML = "";

  CATEGORIAS_SCHEMA.forEach(cat => {
    const valor = analise[cat.chave];
    grade.appendChild(montarCardCategoria(cat, valor));
  });

  const secaoResultado = document.getElementById("secaoResultado");
  secaoResultado.classList.remove("oculto");
  secaoResultado.scrollIntoView({ behavior: "smooth", block: "start" });
}

function montarCardCategoria(cat, valor) {
  const card = document.createElement("div");
  card.className = `card-categoria ${cat.classe}${cat.larga ? " larga" : ""}`;

  const cabecalho = document.createElement("div");
  cabecalho.className = "cat-cabecalho";

  // Conta itens se for lista
  let contagemItens = "";
  if (cat.tipo === "lista") {
    const listaNormalizada = normalizarListaItens(valor);
    contagemItens = `<span class="cat-badge-qtd">${listaNormalizada.length} item(s)</span>`;
  }

  cabecalho.innerHTML = `
    <div class="cat-titulo-wrapper">
      <span class="cat-icone">${cat.icone}</span>
      <h3 class="cat-titulo">${cat.titulo}</h3>
    </div>
    ${contagemItens}
  `;
  card.appendChild(cabecalho);

  const corpo = document.createElement("div");

  if (cat.tipo === "texto") {
    corpo.className = "cat-conteudo";
    const textoLimpo = normalizarTextoSimples(valor);
    if (!textoLimpo) {
      corpo.classList.add("vazio");
      corpo.textContent = "Não identificado explicitamente no documento.";
    } else {
      corpo.textContent = textoLimpo;
    }
  } else {
    // Tipo lista
    const itens = normalizarListaItens(valor);
    if (itens.length === 0) {
      corpo.className = "cat-conteudo vazio";
      corpo.textContent = "Nenhum item identificado nesta categoria.";
    } else {
      corpo.className = "cat-lista";
      itens.forEach(item => {
        const linha = document.createElement("div");
        linha.className = "cat-lista-item";
        linha.textContent = item;
        corpo.appendChild(linha);
      });
    }
  }

  card.appendChild(corpo);
  return card;
}

function alternarModoVisualizacao(modo) {
  const tabCards = document.getElementById("tabCards");
  const tabTexto = document.getElementById("tabTexto");
  const gradeCards = document.getElementById("gradeCategorias");
  const boxTexto = document.getElementById("relatorioTextoBox");

  if (modo === "cards") {
    tabCards.classList.add("ativo");
    tabTexto.classList.remove("ativo");
    gradeCards.classList.remove("oculto");
    boxTexto.classList.add("oculto");
  } else {
    tabTexto.classList.add("ativo");
    tabCards.classList.remove("ativo");
    boxTexto.classList.remove("oculto");
    gradeCards.classList.add("oculto");
  }
}

function copiarResumoGeral() {
  if (!appEstado.ultimoResultadoAnalise) return;
  const resumo = appEstado.ultimoResultadoAnalise.analise_estruturada?.resumo_geral || "";
  copiarParaClipboard(resumo, "Resumo copiado para a área de transferência!");
}

function exportarRelatorioTxt() {
  if (!appEstado.ultimoResultadoAnalise) return;
  const dados = appEstado.ultimoResultadoAnalise;
  const conteudo = `HEMADA — RELATÓRIO DE INTELIGÊNCIA DOCUMENTAL\n` +
    `Arquivo: ${dados.arquivo}\n` +
    `Total de páginas: ${dados.total_paginas}\n` +
    `Data: ${new Date().toLocaleString("pt-BR")}\n` +
    `------------------------------------------------------------\n\n` +
    `${dados.resposta_ia}\n`;

  const blob = new Blob([conteudo], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `Relatorio_HEMADA_${dados.arquivo.replace(/\.[^/.]+$/, "")}.txt`;
  a.click();
  URL.revokeObjectURL(url);
  exibirToast("Download do relatório iniciado!", "⬇");
}

function abrirChatDocumento() {
  if (appEstado.documentoAtivoId) {
    iniciarChatComDocumento(appEstado.documentoAtivoId, appEstado.documentoAtivoNome);
  } else {
    navegarPara("chat");
  }
}

// ══════════════════════════════════════════════════════════════
// 6. MÓDULO HISTÓRICO DE DOCUMENTOS
// ══════════════════════════════════════════════════════════════
function configurarHistorico() {
  const inputBusca = document.getElementById("inputBuscaHistorico");
  const selectOrdenacao = document.getElementById("selectOrdenacaoHistorico");
  const btnLimpar = document.getElementById("btnLimparHistorico");

  // Filtro de busca em tempo real
  inputBusca.addEventListener("input", (e) => {
    appEstado.termoBuscaHistorico = e.target.value.toLowerCase().trim();
    aplicarFiltrosEExibirHistorico();
  });

  // Ordenação
  selectOrdenacao.addEventListener("change", (e) => {
    appEstado.ordenacaoHistorico = e.target.value;
    aplicarFiltrosEExibirHistorico();
  });

  // Botão Limpar Histórico
  btnLimpar.addEventListener("click", async () => {
    if (!confirm("Tem certeza que deseja apagar todos os registros do histórico? Esta operação excluirá permanentemente os dados do SQLite.")) {
      return;
    }
    try {
      await apiRequisicao("/limpar-historico/");
      appEstado.cacheDocumentos = [];
      exibirToast("Histórico apagado com sucesso!", "✓");
      aplicarFiltrosEExibirHistorico();
    } catch (erro) {
      alert(`Falha ao limpar histórico: ${erro.message}`);
    }
  });
}

async function carregarHistorico() {
  const container = document.getElementById("conteudoHistorico");
  container.innerHTML = `
    <div class="estado-carregando">
      <span class="spinner-inline"></span> Carregando documentos do repositório SQLite...
    </div>`;

  try {
    const docs = await apiRequisicao("/historico/");
    appEstado.cacheDocumentos = docs;
    aplicarFiltrosEExibirHistorico();
  } catch (erro) {
    container.innerHTML = `
      <div class="alerta-box alerta-erro">
        ⚠️ Não foi possível carregar os documentos do histórico. Verifique a conexão com o servidor backend.
      </div>`;
  }
}

function aplicarFiltrosEExibirHistorico() {
  const container = document.getElementById("conteudoHistorico");
  let docs = [...appEstado.cacheDocumentos];

  // Filtro de busca por nome
  if (appEstado.termoBuscaHistorico) {
    docs = docs.filter(d => (d.nome_arquivo || "").toLowerCase().includes(appEstado.termoBuscaHistorico));
  }

  // Ordenação
  if (appEstado.ordenacaoHistorico === "recente") {
    docs.reverse(); // ID descendente
  } else if (appEstado.ordenacaoHistorico === "antigo") {
    // ID ascendente natural
  } else if (appEstado.ordenacaoHistorico === "paginas_desc") {
    docs.sort((a, b) => (b.total_paginas || 0) - (a.total_paginas || 0));
  } else if (appEstado.ordenacaoHistorico === "paginas_asc") {
    docs.sort((a, b) => (a.total_paginas || 0) - (b.total_paginas || 0));
  }

  container.innerHTML = "";

  if (docs.length === 0) {
    const msg = appEstado.termoBuscaHistorico
      ? `Nenhum documento encontrado com o termo "${escaparHtml(appEstado.termoBuscaHistorico)}".`
      : "Nenhum documento persistido no SQLite ainda.";
    container.innerHTML = `
      <div class="estado-vazio">
        <span class="estado-vazio-icone">📂</span>
        <p>${msg}</p>
        ${!appEstado.termoBuscaHistorico ? `
        <button class="btn-primario" style="margin-top:12px;" onclick="navegarPara('upload')">
          ⚡ Enviar Novo Documento
        </button>` : ""}
      </div>`;
    return;
  }

  docs.forEach(doc => {
    const item = document.createElement("div");
    item.className = "item-historico-completo";

    item.innerHTML = `
      <div class="hist-col-info">
        <span class="hist-badge-id">#${doc.id}</span>
        <div class="hist-detalhes">
          <span class="hist-nome-doc" title="${escaparHtml(doc.nome_arquivo)}">${escaparHtml(doc.nome_arquivo)}</span>
          <div class="hist-badges-linha">
            <span class="badge-paginas">${doc.total_paginas} página${doc.total_paginas !== 1 ? "s" : ""}</span>
            <span class="badge-tamanho-p">ID persistido: ${doc.id}</span>
          </div>
        </div>
      </div>
      <div class="hist-col-acoes">
        <button class="btn-secundario btn-pequeno btn-ver-doc">📋 Ver Análise</button>
        <button class="btn-primario btn-pequeno btn-chat-doc">💬 Chat IA</button>
      </div>
    `;

    item.querySelector(".btn-ver-doc").addEventListener("click", () => abrirModalDocumento(doc));
    item.querySelector(".btn-chat-doc").addEventListener("click", () => iniciarChatComDocumento(doc.id, doc.nome_arquivo));

    container.appendChild(item);
  });
}

// ══════════════════════════════════════════════════════════════
// 7. MÓDULO ASSISTENTE DE IA (CHAT)
// ══════════════════════════════════════════════════════════════
function configurarChat() {
  const seletor = document.getElementById("seletorDocumentoChat");
  const textarea = document.getElementById("inputChatMensagem");
  const btnEnviar = document.getElementById("btnChatEnviar");

  // Mudança do documento selecionado
  seletor.addEventListener("change", () => {
    const docId = seletor.value;
    const habilitado = docId !== "";
    textarea.disabled = !habilitado;
    btnEnviar.disabled = !habilitado;

    if (habilitado) {
      const docSelecionado = appEstado.cacheDocumentos.find(d => String(d.id) === String(docId));
      const nomeDoc = docSelecionado ? docSelecionado.nome_arquivo : "Documento selecionado";
      document.getElementById("chatDocSubtitulo").textContent = `Contexto ativo: ${nomeDoc}`;
      textarea.focus();
    } else {
      document.getElementById("chatDocSubtitulo").textContent = "Selecione um documento para iniciar a interação contextualizada";
    }
  });

  // Envio por clique
  btnEnviar.addEventListener("click", () => {
    if (!appEstado.emProcessamentoChat) {
      executarEnvioMensagemChat();
    }
  });

  // Envio por tecla Enter (Shift+Enter pula linha)
  textarea.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (!appEstado.emProcessamentoChat && seletor.value) {
        executarEnvioMensagemChat();
      }
    }
  });
}

async function carregarDocumentosParaChat() {
  const seletor = document.getElementById("seletorDocumentoChat");
  seletor.innerHTML = '<option value="">— Carregando documentos do SQLite... —</option>';

  try {
    const docs = appEstado.cacheDocumentos.length > 0
      ? appEstado.cacheDocumentos
      : await apiRequisicao("/historico/");

    appEstado.cacheDocumentos = docs;

    if (docs.length === 0) {
      seletor.innerHTML = '<option value="">— Nenhum documento disponível no banco —</option>';
      document.getElementById("inputChatMensagem").disabled = true;
      document.getElementById("btnChatEnviar").disabled = true;
      exibirAlerta("msgStatusChat", "Ainda não há documentos cadastrados. Analise um PDF na aba «Análise Documental» primeiro.", "info");
      return;
    }

    ocultarElemento("msgStatusChat");
    seletor.innerHTML = '<option value="">— Escolha o documento PDF para a conversa —</option>';

    // Adiciona documentos em ordem recente
    [...docs].reverse().forEach(d => {
      const opt = document.createElement("option");
      opt.value = d.id;
      opt.textContent = `#${d.id} · ${d.nome_arquivo} (${d.total_paginas} págs)`;
      seletor.appendChild(opt);
    });

    // Se houver um documento pré-selecionado na navegação
    if (appEstado.documentoAtivoId) {
      seletor.value = String(appEstado.documentoAtivoId);
      document.getElementById("inputChatMensagem").disabled = false;
      document.getElementById("btnChatEnviar").disabled = false;

      const docEncontrado = docs.find(d => String(d.id) === String(appEstado.documentoAtivoId));
      if (docEncontrado) {
        document.getElementById("chatDocSubtitulo").textContent = `Contexto ativo: ${docEncontrado.nome_arquivo}`;
      }
      appEstado.documentoAtivoId = null; // Consome o valor
    }

  } catch (erro) {
    seletor.innerHTML = '<option value="">— Erro ao carregar documentos —</option>';
    exibirAlerta("msgStatusChat", `Falha ao carregar lista de documentos: ${erro.message}`, "erro");
  }
}

function iniciarChatComDocumento(id, nome) {
  appEstado.documentoAtivoId = id;
  appEstado.documentoAtivoNome = nome;
  navegarPara("chat");
}

function usarSugestaoChat(textoPergunta) {
  const textarea = document.getElementById("inputChatMensagem");
  const seletor = document.getElementById("seletorDocumentoChat");

  if (!seletor.value) {
    exibirToast("Por favor, selecione um documento antes de fazer perguntas.", "⚠️");
    seletor.focus();
    return;
  }

  textarea.value = textoPergunta;
  textarea.focus();
}

async function executarEnvioMensagemChat() {
  const seletor = document.getElementById("seletorDocumentoChat");
  const textarea = document.getElementById("inputChatMensagem");
  const docId = parseInt(seletor.value, 10);
  const pergunta = textarea.value.trim();

  if (!docId || !pergunta) return;

  // Renderiza a mensagem do usuário no chat
  adicionarBalaoMensagem("usuario", pergunta);
  textarea.value = "";
  textarea.style.height = "auto";

  // Trava envio e exibe digitação
  appEstado.emProcessamentoChat = true;
  alternarSpinnerBotao("btnChatEnviar", "spinnerChat", "btnChatTexto", true, "");
  document.getElementById("chatDigitando").classList.remove("oculto");
  ocultarElemento("msgStatusChat");

  try {
    const resposta = await fetch("/chat/", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ documento_id: docId, pergunta: pergunta }),
    });

    const dados = await resposta.json();

    if (!resposta.ok) {
      throw new Error(dados.detail || `Erro HTTP ${resposta.status}`);
    }

    adicionarBalaoMensagem("ia", dados.resposta || "Sem resposta retornada pela IA.", dados.contexto_truncado);

  } catch (erro) {
    adicionarBalaoMensagem("ia", `⚠️ Falha ao obter resposta: ${erro.message}`);
  } finally {
    appEstado.emProcessamentoChat = false;
    alternarSpinnerBotao("btnChatEnviar", "spinnerChat", "btnChatTexto", false, "Enviar");
    document.getElementById("chatDigitando").classList.add("oculto");
  }
}

function adicionarBalaoMensagem(autor, texto, contextoTruncado = false) {
  const container = document.getElementById("chatMensagens");
  document.getElementById("chatEstadoVazio")?.remove();

  const linha = document.createElement("div");
  linha.className = `balao-linha balao-${autor}-wrapper`;

  const avatar = document.createElement("div");
  avatar.className = "balao-avatar";
  avatar.textContent = autor === "usuario" ? "👤" : "⬡";

  const corpo = document.createElement("div");
  corpo.className = "balao-corpo";

  const conteudo = document.createElement("div");
  conteudo.className = "balao-conteudo";
  conteudo.textContent = texto;

  const meta = document.createElement("div");
  meta.className = "balao-meta";

  const hora = new Date().toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
  let badgeTruncado = "";
  if (contextoTruncado) {
    badgeTruncado = `<span style="color:var(--warning);">· Texto extenso truncado</span>`;
  }

  meta.innerHTML = `
    <span>${hora} ${badgeTruncado}</span>
    ${autor === "ia" ? `<button class="btn-copiar-balao" title="Copiar resposta">Copiar</button>` : ""}
  `;

  if (autor === "ia") {
    meta.querySelector(".btn-copiar-balao")?.addEventListener("click", () => {
      copiarParaClipboard(texto, "Resposta copiada!");
    });
  }

  corpo.appendChild(conteudo);
  corpo.appendChild(meta);

  linha.appendChild(avatar);
  linha.appendChild(corpo);

  container.appendChild(linha);
  container.scrollTop = container.scrollHeight;
}

// ══════════════════════════════════════════════════════════════
// 8. MÓDULO MODAL DE DETALHES DO DOCUMENTO
// ══════════════════════════════════════════════════════════════
function configurarModal() {
  const modalOverlay = document.getElementById("modalOverlay");
  const btnFechar = document.getElementById("btnFecharModal");

  btnFechar.addEventListener("click", fecharModal);

  modalOverlay.addEventListener("click", (e) => {
    if (e.target === modalOverlay) fecharModal();
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !modalOverlay.classList.contains("oculto")) {
      fecharModal();
    }
  });
}

function abrirModalDocumento(doc) {
  document.getElementById("modalTitulo").textContent = doc.nome_arquivo || "Documento";
  document.getElementById("modalPaginas").textContent = `${doc.total_paginas} página${doc.total_paginas !== 1 ? "s" : ""}`;

  const corpo = document.getElementById("modalCorpo");
  corpo.innerHTML = "";

  if (doc.resposta_ia) {
    // Renderiza a análise estruturada com destaque visual
    const bloco = document.createElement("div");
    bloco.className = "relatorio-texto-box";
    const pre = document.createElement("pre");
    pre.className = "relatorio-pre";
    pre.textContent = doc.resposta_ia;
    bloco.appendChild(pre);
    corpo.appendChild(bloco);
  } else {
    corpo.innerHTML = `
      <div class="estado-vazio">
        <p>Não há análise registrada para este documento no SQLite.</p>
      </div>`;
  }

  document.getElementById("modalOverlay").classList.remove("oculto");
  document.body.style.overflow = "hidden";
}

function fecharModal() {
  document.getElementById("modalOverlay").classList.add("oculto");
  document.body.style.overflow = "";
}

function copiarConteudoModal() {
  const pre = document.querySelector("#modalCorpo .relatorio-pre");
  if (pre && pre.textContent) {
    copiarParaClipboard(pre.textContent, "Análise copiada para a área de transferência!");
  }
}

// ══════════════════════════════════════════════════════════════
// 9. UTILITÁRIOS, REQUISIÇÕES E TOASTS
// ══════════════════════════════════════════════════════════════

/** Wrapper de fetch GET com captura segura de erros */
async function apiRequisicao(url) {
  const res = await fetch(url);
  if (!res.ok) {
    const jsonErro = await res.json().catch(() => ({}));
    throw new Error(jsonErro.detail || `Erro HTTP ${res.status}`);
  }
  return await res.json();
}

/** Exibe alerta visual dentro de um container com classes semânticas */
function exibirAlerta(idElemento, texto, tipo) {
  const el = document.getElementById(idElemento);
  if (!el) return;
  el.textContent = texto;
  el.className = `alerta-box alerta-${tipo}`;
  el.classList.remove("oculto");
}

function ocultarElemento(idElemento) {
  document.getElementById(idElemento)?.classList.add("oculto");
}

/** Alterna estado visual de carregamento em botões */
function alternarSpinnerBotao(idBotao, idSpinner, idTexto, emProcessamento, textoAlternativo) {
  const btn = document.getElementById(idBotao);
  const spinner = document.getElementById(idSpinner);
  const texto = document.getElementById(idTexto);

  if (btn) btn.disabled = emProcessamento;
  if (spinner) spinner.classList.toggle("oculto", !emProcessamento);
  if (texto && textoAlternativo !== undefined) texto.textContent = textoAlternativo;
}

/** Notificação Toast Flutuante */
function exibirToast(mensagem, icone = "✓") {
  const toast = document.getElementById("toastNotificacao");
  const elIcone = document.getElementById("toastIcone");
  const elMensagem = document.getElementById("toastMensagem");

  if (!toast) return;

  elIcone.textContent = icone;
  elMensagem.textContent = mensagem;
  toast.classList.remove("oculto");

  clearTimeout(toast.timerToast);
  toast.timerToast = setTimeout(() => {
    toast.classList.add("oculto");
  }, 3200);
}

/** Copia texto para a área de transferência com fallback */
function copiarParaClipboard(texto, mensagemSucesso = "Copiado!") {
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(texto)
      .then(() => exibirToast(mensagemSucesso, "📋"))
      .catch(() => fallbackCopiarClipboard(texto, mensagemSucesso));
  } else {
    fallbackCopiarClipboard(texto, mensagemSucesso);
  }
}

function fallbackCopiarClipboard(texto, mensagemSucesso) {
  const area = document.createElement("textarea");
  area.value = texto;
  area.style.position = "fixed";
  area.style.left = "-9999px";
  document.body.appendChild(area);
  area.select();
  try {
    document.execCommand("copy");
    exibirToast(mensagemSucesso, "📋");
  } catch (e) {
    exibirToast("Não foi possível copiar automaticamente.", "⚠️");
  }
  document.body.removeChild(area);
}

/** Normalização de listas de análise */
function normalizarListaItens(valor) {
  if (!valor) return [];

  let itens = [];
  if (Array.isArray(valor)) itens = valor;
  else if (typeof valor === "string") itens = [valor];

  const ignorar = new Set([
    "não identificado no documento",
    "não identificado",
    "não informado",
    "nenhum",
    "nenhuma",
    "n/a",
    ""
  ]);

  return itens
    .map(i => String(i).trim())
    .filter(i => i && !ignorar.has(i.toLowerCase()));
}

/** Normalização de campos de texto */
function normalizarTextoSimples(valor) {
  if (!valor) return "";
  const s = String(valor).trim();
  const ignorar = ["não identificado no documento.", "não identificado no documento", "não informado", "não identificado", "nenhum", "nenhuma", "n/a"];
  if (ignorar.includes(s.toLowerCase())) return "";
  return s;
}

/** Formata bytes para KB ou MB */
function formatarTamanhoBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

/** Capitaliza a primeira letra */
function capitalizar(texto) {
  return texto ? texto.charAt(0).toUpperCase() + texto.slice(1) : "";
}

/** Escapa caracteres HTML para segurança */
function escaparHtml(texto) {
  const div = document.createElement("div");
  div.textContent = String(texto || "");
  return div.innerHTML;
}
