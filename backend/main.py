from contextlib import asynccontextmanager
from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import random
import re
from typing import Optional
import uuid

from dotenv import load_dotenv
from google import genai
from pydantic import BaseModel, Field, field_validator

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"
STATIC_DIR = FRONTEND_DIR / "static"
DADOS_DIR = BASE_DIR / "dados"

load_dotenv(BASE_DIR / ".env")
load_dotenv()

MODELO_GEMINI = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
LADOS_VALIDOS = (4, 6, 8, 10, 12, 20, 100)

CLASSES_BASE = {
	"guerreiro": {
		"nome_classe": "Guerreiro",
		"pv_maximo": 12,
		"ca": 16,
		"ouro": 15,
		"atributos": {
			"forca": 16,
			"destreza": 12,
			"constituicao": 14,
			"inteligencia": 10,
			"sabedoria": 11,
			"carisma": 10,
		},
		"inventario": [
			"Espada Longa",
			"Escudo de Madeira",
			"Cota de Malha",
			"Ração de Viagem (3 dias)",
		],
	},
	"mago": {
		"nome_classe": "Mago",
		"pv_maximo": 8,
		"ca": 12,
		"ouro": 20,
		"atributos": {
			"forca": 8,
			"destreza": 14,
			"constituicao": 12,
			"inteligencia": 16,
			"sabedoria": 13,
			"carisma": 10,
		},
		"inventario": [
			"Cajado Arcano",
			"Grimório de Aprendiz",
			"Adaga",
			"Bolsa de Componentes",
		],
	},
	"ladino": {
		"nome_classe": "Ladino",
		"pv_maximo": 10,
		"ca": 14,
		"ouro": 25,
		"atributos": {
			"forca": 10,
			"destreza": 16,
			"constituicao": 12,
			"inteligencia": 13,
			"sabedoria": 12,
			"carisma": 14,
		},
		"inventario": [
			"Rapieira",
			"Adaga (x2)",
			"Ferramentas de Ladrão",
			"Armadura de Couro",
		],
	},
	"clerigo": {
		"nome_classe": "Clérigo",
		"pv_maximo": 10,
		"ca": 15,
		"ouro": 15,
		"atributos": {
			"forca": 14,
			"destreza": 10,
			"constituicao": 14,
			"inteligencia": 10,
			"sabedoria": 16,
			"carisma": 12,
		},
		"inventario": [
			"Maça de Guerra",
			"Escudo com Símbolo Sagrado",
			"Brunea",
			"Poção de Cura Menor",
		],
	},
}

INSTRUCAO_MESTRE = (
	"Você é um Mestre de D&D 5ª Edição experiente, imparcial e descritivo. "
	"Regras obrigatórias: "
	"1. Nunca controle as falas, pensamentos ou decisões do personagem do jogador. "
	"2. Evite facilitar o jogo: NPCs têm interesses próprios, podem mentir, recusar pedidos ou reagir de forma hostil. "
	"3. Sempre que o jogador tentar uma ação arriscada ou de resultado incerto (combate, persuasão difícil, furtividade, escalada, investigação sob pressão), defina requer_teste=true, escolha o atributo adequado, uma CD justa entre 8 e 20 e descreva os riscos em teste_motivo sem já declarar o sucesso ou a falha. "
	"4. Quando o resultado de uma rolagem for informado a você, defina requer_teste=false e narre exatamente o desfecho coerente com o sucesso ou a falha. Em falhas, aplique consequências reais (dano via delta_pv negativo, perda de recursos, alerta de inimigos ou piora da situação). "
	"5. Só conceda itens ou ouro em delta_ouro e itens_ganhos quando houver conquista clara na cena, e remova itens em itens_removidos quando consumidos ou perdidos. "
	"6. Responda sempre em Português Brasileiro, com foco sensorial na cena imediata, encerrando a narração com a situação em aberto para o jogador agir."
)

ESQUEMA_RESPOSTA_MESTRE = {
	"type": "object",
	"properties": {
		"narracao": {"type": "string"},
		"local_atual": {"type": "string"},
		"requer_teste": {"type": "boolean"},
		"teste_atributo": {
			"type": ["string", "null"],
			"enum": [
				"forca",
				"destreza",
				"constituicao",
				"inteligencia",
				"sabedoria",
				"carisma",
				None,
			],
		},
		"teste_cd": {"type": ["integer", "null"], "minimum": 5, "maximum": 30},
		"teste_motivo": {"type": ["string", "null"]},
		"delta_pv": {"type": "integer"},
		"delta_ouro": {"type": "integer"},
		"itens_ganhos": {"type": "array", "items": {"type": "string"}},
		"itens_removidos": {"type": "array", "items": {"type": "string"}},
		"resumo_campanha": {"type": "string"},
	},
	"required": [
		"narracao",
		"local_atual",
		"requer_teste",
		"teste_atributo",
		"teste_cd",
		"teste_motivo",
		"delta_pv",
		"delta_ouro",
		"itens_ganhos",
		"itens_removidos",
		"resumo_campanha",
	],
}


class NovaCampanhaEntrada(BaseModel):
	nome_personagem: str = Field(min_length=1, max_length=60)
	classe: str
	cenario: str = Field(
		default="Fantasia clássica em uma vila de fronteira",
		min_length=3,
		max_length=300,
	)
	titulo: Optional[str] = Field(default=None, max_length=100)


class AcaoEntrada(BaseModel):
	texto: str = Field(min_length=1, max_length=1000)


class RolagemEntrada(BaseModel):
	valor_dado: Optional[int] = Field(default=None, ge=1, le=20)


class DadoLivreEntrada(BaseModel):
	lados: int

	@field_validator("lados")
	@classmethod
	def validar_lados(cls, valor: int) -> int:
		if valor not in LADOS_VALIDOS:
			raise ValueError("Tipo de dado inválido.")
		return valor


@asynccontextmanager
async def lifespan(app: FastAPI):
	DADOS_DIR.mkdir(parents=True, exist_ok=True)
	yield


app = FastAPI(title="Mestre de D&D", lifespan=lifespan)


@app.middleware("http")
async def adicionar_cabecalhos_seguranca(request: Request, call_next):
	resposta = await call_next(request)
	resposta.headers["Content-Security-Policy"] = (
		"default-src 'self'; "
		"script-src 'self'; "
		"style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
		"font-src 'self' https://fonts.gstatic.com; "
		"img-src 'self' data:"
	)
	resposta.headers["X-Content-Type-Options"] = "nosniff"
	resposta.headers["X-Frame-Options"] = "DENY"
	resposta.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
	return resposta


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


def agora_iso() -> str:
	return datetime.now(timezone.utc).isoformat()


def calcular_modificador(valor: int) -> int:
	return (valor - 10) // 2


def rolar_teste_d20(valor_atributo: int, cd: int, valor_manual: Optional[int] = None) -> dict:
	dado = valor_manual if valor_manual is not None else random.randint(1, 20)
	modificador = calcular_modificador(valor_atributo)
	total = dado + modificador
	critico = dado == 20
	falha_critica = dado == 1
	sucesso = critico or (not falha_critica and total >= cd)
	return {
		"dado": dado,
		"modificador": modificador,
		"total": total,
		"cd": cd,
		"critico": critico,
		"falha_critica": falha_critica,
		"sucesso": sucesso,
	}


def aplicar_deltas_estado(campanha: dict, resposta: dict) -> dict:
	personagem = campanha["personagem"]
	pv_anterior = personagem["pv_atual"]
	delta_pv_solicitado = int(resposta.get("delta_pv") or 0)
	pv_novo = max(0, min(personagem["pv_maximo"], pv_anterior + delta_pv_solicitado))
	personagem["pv_atual"] = pv_novo

	ouro_anterior = personagem["ouro"]
	delta_ouro_solicitado = int(resposta.get("delta_ouro") or 0)
	ouro_novo = max(0, ouro_anterior + delta_ouro_solicitado)
	personagem["ouro"] = ouro_novo

	itens_ganhos_aplicados = []
	for item in resposta.get("itens_ganhos") or []:
		item_limpo = str(item).strip()
		if item_limpo:
			personagem["inventario"].append(item_limpo)
			itens_ganhos_aplicados.append(item_limpo)

	itens_removidos_aplicados = []
	for item in resposta.get("itens_removidos") or []:
		item_limpo = str(item).strip()
		if item_limpo in personagem["inventario"]:
			personagem["inventario"].remove(item_limpo)
			itens_removidos_aplicados.append(item_limpo)

	local_novo = str(resposta.get("local_atual") or "").strip()
	if local_novo:
		campanha["local_atual"] = local_novo

	resumo_novo = str(resposta.get("resumo_campanha") or "").strip()
	if resumo_novo:
		campanha["resumo_campanha"] = resumo_novo

	return {
		"delta_pv": pv_novo - pv_anterior,
		"delta_ouro": ouro_novo - ouro_anterior,
		"itens_ganhos": itens_ganhos_aplicados,
		"itens_removidos": itens_removidos_aplicados,
	}


def validar_campanha_id(campanha_id: str) -> Path:
	if not re.fullmatch(r"[a-zA-Z0-9_-]+", campanha_id):
		raise HTTPException(status_code=400, detail="Identificador de campanha inválido.")
	return DADOS_DIR / f"{campanha_id}.json"


def salvar_campanha(campanha: dict) -> None:
	DADOS_DIR.mkdir(parents=True, exist_ok=True)
	campanha["atualizado_em"] = agora_iso()
	caminho = validar_campanha_id(campanha["id"])
	caminho.write_text(json.dumps(campanha, ensure_ascii=False, indent="\t"), encoding="utf-8")


def carregar_campanha(campanha_id: str) -> dict:
	caminho = validar_campanha_id(campanha_id)
	if not caminho.exists():
		raise HTTPException(status_code=404, detail="Campanha não encontrada.")
	return json.loads(caminho.read_text(encoding="utf-8"))


def listar_campanhas_salvas() -> list[dict]:
	if not DADOS_DIR.exists():
		return []
	resumos = []
	for arquivo in DADOS_DIR.glob("*.json"):
		dados = json.loads(arquivo.read_text(encoding="utf-8"))
		personagem = dados["personagem"]
		resumos.append({
			"id": dados["id"],
			"titulo": dados["titulo"],
			"local_atual": dados["local_atual"],
			"nome_personagem": personagem["nome"],
			"classe": personagem["nome_classe"],
			"pv_atual": personagem["pv_atual"],
			"pv_maximo": personagem["pv_maximo"],
			"turnos": len(dados["historico"]),
			"atualizado_em": dados["atualizado_em"],
		})
	resumos.sort(key=lambda item: item["atualizado_em"], reverse=True)
	return resumos


def excluir_campanha_arquivo(campanha_id: str) -> None:
	caminho = validar_campanha_id(campanha_id)
	if not caminho.exists():
		raise HTTPException(status_code=404, detail="Campanha não encontrada.")
	caminho.unlink()


def montar_contexto_prompt(campanha: dict, instrucao_turno: str) -> str:
	ultimos_turnos = campanha["historico"][-10:]
	linhas_historico = []
	for turno in ultimos_turnos:
		linhas_historico.append(f"[{turno['autor'].upper()}] {turno['texto']}")
	texto_historico = "\n".join(linhas_historico) if linhas_historico else "Início da aventura."
	estado = {
		"cenario": campanha["cenario"],
		"local_atual": campanha["local_atual"],
		"resumo_campanha": campanha["resumo_campanha"],
		"personagem": campanha["personagem"],
	}
	return (
		f"Estado atual da campanha:\n{json.dumps(estado, ensure_ascii=False)}\n\n"
		f"Histórico recente:\n{texto_historico}\n\n"
		f"Instrução do turno atual:\n{instrucao_turno}"
	)


def consultar_mestre(prompt: str, permitir_teste: bool = True) -> dict:
	chave_api = os.getenv("GEMINI_API_KEY", "").strip()
	if not chave_api:
		raise HTTPException(
			status_code=503,
			detail="GEMINI_API_KEY não configurada. Adicione a chave no arquivo .env para narrar turnos.",
		)
	regra_teste = (
		"Você pode solicitar um teste (requer_teste=true) se a ação tiver risco real."
		if permitir_teste
		else "Não solicite novo teste neste turno: defina requer_teste=false, teste_atributo=null, teste_cd=null e teste_motivo=null."
	)
	entrada_completa = f"{prompt}\n\nRestrição mecânica: {regra_teste}"
	try:
		cliente = genai.Client(api_key=chave_api)
		interacao = cliente.interactions.create(
			model=MODELO_GEMINI,
			system_instruction=INSTRUCAO_MESTRE,
			input=entrada_completa,
			response_format={
				"type": "text",
				"mime_type": "application/json",
				"schema": ESQUEMA_RESPOSTA_MESTRE,
			},
		)
		conteudo = interacao.output_text
	except Exception as erro:
		raise HTTPException(status_code=502, detail=f"Erro ao consultar Gemini API: {erro}")

	if not conteudo:
		raise HTTPException(status_code=502, detail="Resposta vazia recebida da Gemini API.")
	try:
		dados = json.loads(conteudo)
	except json.JSONDecodeError as erro:
		raise HTTPException(status_code=502, detail=f"Resposta JSON inválida do modelo: {erro}")

	if not permitir_teste:
		dados["requer_teste"] = False
		dados["teste_atributo"] = None
		dados["teste_cd"] = None
		dados["teste_motivo"] = None
	return dados


@app.get("/")
def pagina_inicial():
	return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/health")
def verificar_saude():
	return {
		"status": "ok",
		"gemini_configurado": bool(os.getenv("GEMINI_API_KEY", "").strip()),
	}


@app.get("/api/classes")
def listar_classes():
	return CLASSES_BASE


@app.get("/api/campanhas")
def listar_campanhas():
	return listar_campanhas_salvas()


@app.post("/api/campanhas", status_code=201)
def criar_campanha(entrada: NovaCampanhaEntrada):
	chave_classe = entrada.classe.strip().lower()
	if chave_classe not in CLASSES_BASE:
		raise HTTPException(status_code=400, detail="Classe inválida.")
	molde = deepcopy(CLASSES_BASE[chave_classe])
	nome_limpo = entrada.nome_personagem.strip()
	titulo_final = (
		entrada.titulo.strip()
		if entrada.titulo and entrada.titulo.strip()
		else f"Crônica de {nome_limpo}"
	)
	campanha = {
		"id": uuid.uuid4().hex[:12],
		"titulo": titulo_final,
		"cenario": entrada.cenario.strip(),
		"local_atual": "Ponto de Partida",
		"resumo_campanha": f"{nome_limpo}, um {molde['nome_classe']} nível 1, inicia sua jornada.",
		"personagem": {
			"nome": nome_limpo,
			"classe": chave_classe,
			"nome_classe": molde["nome_classe"],
			"nivel": 1,
			"pv_atual": molde["pv_maximo"],
			"pv_maximo": molde["pv_maximo"],
			"ca": molde["ca"],
			"ouro": molde["ouro"],
			"atributos": molde["atributos"],
			"inventario": molde["inventario"],
		},
		"teste_pendente": None,
		"historico": [],
		"atualizado_em": agora_iso(),
	}

	if os.getenv("GEMINI_API_KEY", "").strip():
		prompt_abertura = montar_contexto_prompt(
			campanha,
			"Crie a cena de abertura da aventura no cenário informado. Apresente o ambiente imediato, um gancho inicial claro e termine perguntando o que o personagem faz.",
		)
		resposta = consultar_mestre(prompt_abertura, permitir_teste=False)
		aplicar_deltas_estado(campanha, resposta)
		texto_abertura = resposta["narracao"]
	else:
		texto_abertura = (
			f"Você inicia sua jornada em '{campanha['cenario']}' como {nome_limpo} ({molde['nome_classe']}). "
			"Configure GEMINI_API_KEY no arquivo .env para ativar a narração do Mestre."
		)

	campanha["historico"].append({
		"autor": "mestre",
		"texto": texto_abertura,
		"timestamp": agora_iso(),
	})
	salvar_campanha(campanha)
	return campanha


@app.get("/api/campanhas/{campanha_id}")
def obter_campanha(campanha_id: str):
	return carregar_campanha(campanha_id)


@app.delete("/api/campanhas/{campanha_id}")
def remover_campanha(campanha_id: str):
	excluir_campanha_arquivo(campanha_id)
	return {"removido": True, "id": campanha_id}


@app.post("/api/campanhas/{campanha_id}/acao")
def executar_acao(campanha_id: str, entrada: AcaoEntrada):
	campanha = carregar_campanha(campanha_id)
	if campanha["teste_pendente"] is not None:
		raise HTTPException(
			status_code=400,
			detail="Existe um teste pendente. Role o dado antes de enviar outra ação.",
		)

	texto_acao = entrada.texto.strip()
	if not texto_acao:
		raise HTTPException(status_code=400, detail="A ação não pode estar vazia.")

	prompt = montar_contexto_prompt(
		campanha,
		f"O jogador declarou a seguinte ação: {texto_acao}",
	)
	resposta = consultar_mestre(prompt, permitir_teste=True)

	campanha["historico"].append({
		"autor": "jogador",
		"texto": texto_acao,
		"timestamp": agora_iso(),
	})

	atributo_teste = resposta.get("teste_atributo")
	atributos_validos = campanha["personagem"]["atributos"]
	if resposta.get("requer_teste") and atributo_teste in atributos_validos:
		cd_bruto = int(resposta.get("teste_cd") or 12)
		cd_ajustado = max(5, min(30, cd_bruto))
		campanha["teste_pendente"] = {
			"atributo": atributo_teste,
			"cd": cd_ajustado,
			"motivo": str(resposta.get("teste_motivo") or "Teste de habilidade"),
			"acao_origem": texto_acao,
		}
		local_novo = str(resposta.get("local_atual") or "").strip()
		if local_novo:
			campanha["local_atual"] = local_novo
		resumo_novo = str(resposta.get("resumo_campanha") or "").strip()
		if resumo_novo:
			campanha["resumo_campanha"] = resumo_novo
		campanha["historico"].append({
			"autor": "mestre",
			"texto": resposta["narracao"],
			"timestamp": agora_iso(),
		})
	else:
		deltas = aplicar_deltas_estado(campanha, resposta)
		campanha["historico"].append({
			"autor": "mestre",
			"texto": resposta["narracao"],
			"deltas": deltas,
			"timestamp": agora_iso(),
		})

	salvar_campanha(campanha)
	return campanha


@app.post("/api/campanhas/{campanha_id}/rolar")
def resolver_rolagem(campanha_id: str, entrada: RolagemEntrada):
	campanha = carregar_campanha(campanha_id)
	teste = campanha.get("teste_pendente")
	if teste is None:
		raise HTTPException(status_code=400, detail="Não há teste pendente nesta campanha.")

	atributo = teste["atributo"]
	valor_atributo = campanha["personagem"]["atributos"][atributo]
	rolagem = rolar_teste_d20(valor_atributo, teste["cd"], entrada.valor_dado)

	desfecho = "SUCESSO" if rolagem["sucesso"] else "FALHA"
	detalhe_critico = ""
	if rolagem["critico"]:
		detalhe_critico = " (ACERTO CRÍTICO - 20 natural)"
	elif rolagem["falha_critica"]:
		detalhe_critico = " (FALHA CRÍTICA - 1 natural)"

	sinal = "+" if rolagem["modificador"] >= 0 else ""
	instrucao_pos_rolagem = (
		f"Ação original do jogador: {teste['acao_origem']}\n"
		f"Motivo do teste: {teste['motivo']}\n"
		f"Resultado da rolagem de {atributo} contra CD {teste['cd']}: "
		f"d20={rolagem['dado']} {sinal}{rolagem['modificador']} = {rolagem['total']} -> {desfecho}{detalhe_critico}.\n"
		"Narre as consequências desse resultado exato e aplique os deltas de estado cabíveis."
	)
	prompt = montar_contexto_prompt(campanha, instrucao_pos_rolagem)
	resposta = consultar_mestre(prompt, permitir_teste=False)

	deltas = aplicar_deltas_estado(campanha, resposta)
	campanha["teste_pendente"] = None

	texto_sistema = (
		f"Teste de {atributo.capitalize()} (CD {teste['cd']}): "
		f"d20={rolagem['dado']} {sinal}{rolagem['modificador']} = {rolagem['total']} — {desfecho}{detalhe_critico}"
	)
	campanha["historico"].append({
		"autor": "sistema",
		"texto": texto_sistema,
		"rolagem": rolagem,
		"timestamp": agora_iso(),
	})
	campanha["historico"].append({
		"autor": "mestre",
		"texto": resposta["narracao"],
		"deltas": deltas,
		"timestamp": agora_iso(),
	})
	salvar_campanha(campanha)
	return {
		"campanha": campanha,
		"rolagem": rolagem,
		"deltas": deltas,
	}


@app.post("/api/campanhas/{campanha_id}/dado")
def rolar_dado_livre(campanha_id: str, entrada: DadoLivreEntrada):
	carregar_campanha(campanha_id)
	resultado = random.randint(1, entrada.lados)
	return {"lados": entrada.lados, "resultado": resultado}
