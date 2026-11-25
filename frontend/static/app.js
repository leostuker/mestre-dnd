const estadoApp = {
	classes: {},
	campanhaAtual: null,
	ocupado: false,
};

const ROTULOS_ATRIBUTOS = {
	forca: "FOR",
	destreza: "DES",
	constituicao: "CON",
	inteligencia: "INT",
	sabedoria: "SAB",
	carisma: "CAR",
};

const NOMES_ATRIBUTOS = {
	forca: "Força",
	destreza: "Destreza",
	constituicao: "Constituição",
	inteligencia: "Inteligência",
	sabedoria: "Sabedoria",
	carisma: "Carisma",
};

const telaInicio = document.getElementById("tela-inicio");
const telaMesa = document.getElementById("tela-mesa");
const alertaApi = document.getElementById("alerta-api");
const selectClasse = document.getElementById("select-classe");
const previaClasse = document.getElementById("previa-classe");
const listaCampanhas = document.getElementById("lista-campanhas");
const formNovaCampanha = document.getElementById("form-nova-campanha");
const formAcao = document.getElementById("form-acao");
const inputAcao = document.getElementById("input-acao");
const statusEnvio = document.getElementById("status-envio");
const historicoTurnos = document.getElementById("historico-turnos");
const caixaTeste = document.getElementById("caixa-teste");
const inputDadoManual = document.getElementById("input-dado-manual");
const resultadoDadoLivre = document.getElementById("resultado-dado-livre");

function calcularModificador(valor) {
	const mod = Math.floor((valor - 10) / 2);
	return mod >= 0 ? `+${mod}` : `${mod}`;
}

async function requisicaoJson(url, opcoes = {}) {
	const resposta = await fetch(url, {
		headers: { "Content-Type": "application/json" },
		...opcoes,
	});
	const dados = await resposta.json();
	if (!resposta.ok) {
		throw new Error(dados.detail || "Falha na requisição.");
	}
	return dados;
}

function mostrarTelaInicio() {
	telaMesa.classList.add("oculto");
	telaInicio.classList.remove("oculto");
	carregarListaCampanhas();
}

function mostrarTelaMesa() {
	telaInicio.classList.add("oculto");
	telaMesa.classList.remove("oculto");
}

function definirOcupado(ocupado, mensagem = "") {
	estadoApp.ocupado = ocupado;
	document.getElementById("btn-enviar-acao").disabled = ocupado;
	document.getElementById("btn-rolar-d20").disabled = ocupado;
	document.getElementById("btn-enviar-manual").disabled = ocupado;
	document.getElementById("btn-criar-campanha").disabled = ocupado;
	statusEnvio.textContent = mensagem;
}

function atualizarPreviaClasse() {
	const classe = estadoApp.classes[selectClasse.value];
	if (!classe) {
		previaClasse.textContent = "";
		return;
	}
	const resumoAtributos = Object.entries(classe.atributos)
		.map(([chave, valor]) => `${ROTULOS_ATRIBUTOS[chave]} ${valor}`)
		.join(" | ");
	previaClasse.textContent = `PV: ${classe.pv_maximo} | CA: ${classe.ca} | Ouro: ${classe.ouro} PO — ${resumoAtributos}`;
}

function renderizarClasses() {
	selectClasse.innerHTML = "";
	for (const [chave, classe] of Object.entries(estadoApp.classes)) {
		const opcao = document.createElement("option");
		opcao.value = chave;
		opcao.textContent = classe.nome_classe;
		selectClasse.appendChild(opcao);
	}
	atualizarPreviaClasse();
}

async function carregarListaCampanhas() {
	const campanhas = await requisicaoJson("/api/campanhas");
	listaCampanhas.innerHTML = "";
	if (campanhas.length === 0) {
		const vazio = document.createElement("p");
		vazio.textContent = "Nenhuma campanha salva ainda.";
		listaCampanhas.appendChild(vazio);
		return;
	}

	for (const item of campanhas) {
		const card = document.createElement("div");
		card.className = "card-campanha";

		const info = document.createElement("div");
		const titulo = document.createElement("h3");
		titulo.textContent = item.titulo;
		const detalhes = document.createElement("p");
		detalhes.textContent = `${item.nome_personagem} (${item.classe}) — PV ${item.pv_atual}/${item.pv_maximo} — ${item.local_atual}`;
		info.appendChild(titulo);
		info.appendChild(detalhes);

		const acoes = document.createElement("div");
		acoes.className = "acoes-card";

		const btnAbrir = document.createElement("button");
		btnAbrir.type = "button";
		btnAbrir.className = "btn-secundario";
		btnAbrir.textContent = "Continuar";
		btnAbrir.addEventListener("click", () => abrirCampanha(item.id));

		const btnExcluir = document.createElement("button");
		btnExcluir.type = "button";
		btnExcluir.className = "btn-perigo";
		btnExcluir.textContent = "Excluir";
		btnExcluir.addEventListener("click", () => excluirCampanha(item.id));

		acoes.appendChild(btnAbrir);
		acoes.appendChild(btnExcluir);
		card.appendChild(info);
		card.appendChild(acoes);
		listaCampanhas.appendChild(card);
	}
}

function formatarDeltas(deltas) {
	if (!deltas) {
		return "";
	}
	const partes = [];
	if (deltas.delta_pv) {
		partes.push(`PV ${deltas.delta_pv > 0 ? "+" : ""}${deltas.delta_pv}`);
	}
	if (deltas.delta_ouro) {
		partes.push(`Ouro ${deltas.delta_ouro > 0 ? "+" : ""}${deltas.delta_ouro} PO`);
	}
	if (deltas.itens_ganhos && deltas.itens_ganhos.length > 0) {
		partes.push(`Ganhou: ${deltas.itens_ganhos.join(", ")}`);
	}
	if (deltas.itens_removidos && deltas.itens_removidos.length > 0) {
		partes.push(`Removeu: ${deltas.itens_removidos.join(", ")}`);
	}
	return partes.join(" | ");
}

function renderizarMesa() {
	const campanha = estadoApp.campanhaAtual;
	if (!campanha) {
		return;
	}
	const p = campanha.personagem;

	document.getElementById("mesa-titulo").textContent = campanha.titulo;
	document.getElementById("mesa-local").textContent = `Local: ${campanha.local_atual}`;
	document.getElementById("ficha-nome").textContent = p.nome;
	document.getElementById("ficha-subtitulo").textContent = `${p.nome_classe} — Nível ${p.nivel}`;
	document.getElementById("ficha-pv").textContent = `${p.pv_atual} / ${p.pv_maximo}`;
	document.getElementById("ficha-ca").textContent = p.ca;
	document.getElementById("ficha-ouro").textContent = p.ouro;

	const percentualPv = p.pv_maximo > 0 ? Math.round((p.pv_atual / p.pv_maximo) * 100) : 0;
	document.getElementById("barra-pv-preenchimento").style.width = `${percentualPv}%`;

	const gradeAtributos = document.getElementById("grade-atributos");
	gradeAtributos.innerHTML = "";
	for (const [chave, valor] of Object.entries(p.atributos)) {
		const card = document.createElement("div");
		card.className = "card-atributo";
		const rotulo = document.createElement("span");
		rotulo.textContent = ROTULOS_ATRIBUTOS[chave] || chave;
		const mod = document.createElement("strong");
		mod.textContent = calcularModificador(valor);
		const bruto = document.createElement("small");
		bruto.textContent = `${valor}`;
		card.appendChild(rotulo);
		card.appendChild(mod);
		card.appendChild(bruto);
		gradeAtributos.appendChild(card);
	}

	const listaInv = document.getElementById("lista-inventario");
	listaInv.innerHTML = "";
	if (p.inventario.length === 0) {
		const vazio = document.createElement("li");
		vazio.textContent = "Mochila vazia";
		listaInv.appendChild(vazio);
	} else {
		for (const item of p.inventario) {
			const li = document.createElement("li");
			li.textContent = item;
			listaInv.appendChild(li);
		}
	}

	historicoTurnos.innerHTML = "";
	for (const turno of campanha.historico) {
		const bloco = document.createElement("div");
		bloco.className = `turno turno-${turno.autor}`;

		const autor = document.createElement("div");
		autor.className = "turno-autor";
		autor.textContent = turno.autor === "mestre" ? "Mestre" : turno.autor === "jogador" ? p.nome : "Dados";

		const texto = document.createElement("p");
		texto.textContent = turno.texto;

		bloco.appendChild(autor);
		bloco.appendChild(texto);

		const textoDeltas = formatarDeltas(turno.deltas);
		if (textoDeltas) {
			const divDeltas = document.createElement("div");
			divDeltas.className = "deltas-turno";
			divDeltas.textContent = textoDeltas;
			bloco.appendChild(divDeltas);
		}

		historicoTurnos.appendChild(bloco);
	}
	historicoTurnos.scrollTop = historicoTurnos.scrollHeight;

	const teste = campanha.teste_pendente;
	if (teste) {
		const mod = calcularModificador(p.atributos[teste.atributo]);
		document.getElementById("teste-motivo").textContent = teste.motivo;
		document.getElementById("teste-detalhes").textContent = `${NOMES_ATRIBUTOS[teste.atributo]} (${mod}) | CD ${teste.cd}`;
		caixaTeste.classList.remove("oculto");
		formAcao.classList.add("oculto");
	} else {
		caixaTeste.classList.add("oculto");
		formAcao.classList.remove("oculto");
	}
}

async function abrirCampanha(campanhaId) {
	const campanha = await requisicaoJson(`/api/campanhas/${campanhaId}`);
	estadoApp.campanhaAtual = campanha;
	resultadoDadoLivre.textContent = "";
	renderizarMesa();
	mostrarTelaMesa();
}

async function excluirCampanha(campanhaId) {
	await requisicaoJson(`/api/campanhas/${campanhaId}`, { method: "DELETE" });
	await carregarListaCampanhas();
}

async function enviarRolagem(valorManual = null) {
	if (!estadoApp.campanhaAtual || estadoApp.ocupado) {
		return;
	}
	definirOcupado(true, "Resolvendo rolagem com o Mestre...");
	try {
		const corpo = valorManual !== null ? { valor_dado: valorManual } : {};
		const resposta = await requisicaoJson(
			`/api/campanhas/${estadoApp.campanhaAtual.id}/rolar`,
			{
				method: "POST",
				body: JSON.stringify(corpo),
			}
		);
		estadoApp.campanhaAtual = resposta.campanha;
		inputDadoManual.value = "";
		renderizarMesa();
		statusEnvio.textContent = "";
	} catch (erro) {
		statusEnvio.textContent = erro.message;
	} finally {
		definirOcupado(false, statusEnvio.textContent);
	}
}

formNovaCampanha.addEventListener("submit", async (evento) => {
	evento.preventDefault();
	if (estadoApp.ocupado) {
		return;
	}
	definirOcupado(true, "Criando campanha...");
	try {
		const dados = await requisicaoJson("/api/campanhas", {
			method: "POST",
			body: JSON.stringify({
				nome_personagem: document.getElementById("input-nome").value,
				titulo: document.getElementById("input-titulo").value || null,
				classe: selectClasse.value,
				cenario: document.getElementById("input-cenario").value,
			}),
		});
		estadoApp.campanhaAtual = dados;
		formNovaCampanha.reset();
		atualizarPreviaClasse();
		renderizarMesa();
		mostrarTelaMesa();
		statusEnvio.textContent = "";
	} catch (erro) {
		alert(erro.message);
	} finally {
		definirOcupado(false, "");
	}
});

formAcao.addEventListener("submit", async (evento) => {
	evento.preventDefault();
	if (!estadoApp.campanhaAtual || estadoApp.ocupado) {
		return;
	}
	const texto = inputAcao.value.trim();
	if (!texto) {
		return;
	}
	definirOcupado(true, "Mestre processando turno...");
	try {
		const campanhaAtualizada = await requisicaoJson(
			`/api/campanhas/${estadoApp.campanhaAtual.id}/acao`,
			{
				method: "POST",
				body: JSON.stringify({ texto }),
			}
		);
		estadoApp.campanhaAtual = campanhaAtualizada;
		inputAcao.value = "";
		renderizarMesa();
		statusEnvio.textContent = "";
	} catch (erro) {
		statusEnvio.textContent = erro.message;
	} finally {
		definirOcupado(false, statusEnvio.textContent);
	}
});

document.getElementById("btn-rolar-d20").addEventListener("click", () => {
	enviarRolagem(null);
});

document.getElementById("btn-enviar-manual").addEventListener("click", () => {
	const valor = Number(inputDadoManual.value);
	if (!Number.isInteger(valor) || valor < 1 || valor > 20) {
		statusEnvio.textContent = "Informe um valor inteiro de 1 a 20.";
		return;
	}
	enviarRolagem(valor);
});

for (const botao of document.querySelectorAll(".btn-dado")) {
	botao.addEventListener("click", async () => {
		if (!estadoApp.campanhaAtual) {
			return;
		}
		const lados = Number(botao.dataset.lados);
		const resposta = await requisicaoJson(
			`/api/campanhas/${estadoApp.campanhaAtual.id}/dado`,
			{
				method: "POST",
				body: JSON.stringify({ lados }),
			}
		);
		resultadoDadoLivre.textContent = `1d${resposta.lados} -> ${resposta.resultado}`;
	});
}

selectClasse.addEventListener("change", atualizarPreviaClasse);
document.getElementById("btn-nav-campanhas").addEventListener("click", mostrarTelaInicio);
document.getElementById("btn-nav-nova").addEventListener("click", () => {
	mostrarTelaInicio();
	document.getElementById("input-nome").focus();
});

async function inicializar() {
	const [saude, classes] = await Promise.all([
		requisicaoJson("/health"),
		requisicaoJson("/api/classes"),
	]);
	if (!saude.gemini_configurado) {
		alertaApi.classList.remove("oculto");
	}
	estadoApp.classes = classes;
	renderizarClasses();
	await carregarListaCampanhas();
}

inicializar();
