from fastapi.testclient import TestClient

from backend import main


def configurar_ambiente_teste(monkeypatch, tmp_path):
	monkeypatch.setattr(main, "DADOS_DIR", tmp_path)
	monkeypatch.delenv("GEMINI_API_KEY", raising=False)
	return TestClient(main.app)


def test_health(monkeypatch, tmp_path):
	cliente = configurar_ambiente_teste(monkeypatch, tmp_path)
	resposta = cliente.get("/health")
	assert resposta.status_code == 200
	dados = resposta.json()
	assert dados["status"] == "ok"


def test_calcular_modificador():
	assert main.calcular_modificador(8) == -1
	assert main.calcular_modificador(10) == 0
	assert main.calcular_modificador(15) == 2
	assert main.calcular_modificador(18) == 4


def test_rolar_teste_d20_critico_e_falha_critica():
	sucesso_critico = main.rolar_teste_d20(8, 30, valor_manual=20)
	assert sucesso_critico["critico"] is True
	assert sucesso_critico["sucesso"] is True

	falha_critica = main.rolar_teste_d20(20, 5, valor_manual=1)
	assert falha_critica["falha_critica"] is True
	assert falha_critica["sucesso"] is False


def test_aplicar_deltas_estado_respeita_limites():
	campanha = {
		"local_atual": "Taverna",
		"resumo_campanha": "Resumo inicial",
		"personagem": {
			"pv_atual": 8,
			"pv_maximo": 10,
			"ouro": 5,
			"inventario": ["Adaga", "Tocha"],
		},
	}
	resposta = {
		"delta_pv": 10,
		"delta_ouro": -20,
		"itens_ganhos": ["Chave de Ferro", "   "],
		"itens_removidos": ["Tocha", "Item Inexistente"],
		"local_atual": "Beco Escuro",
		"resumo_campanha": "Entrou no beco.",
	}
	deltas = main.aplicar_deltas_estado(campanha, resposta)
	assert campanha["personagem"]["pv_atual"] == 10
	assert deltas["delta_pv"] == 2
	assert campanha["personagem"]["ouro"] == 0
	assert deltas["delta_ouro"] == -5
	assert campanha["personagem"]["inventario"] == ["Adaga", "Chave de Ferro"]
	assert deltas["itens_ganhos"] == ["Chave de Ferro"]
	assert deltas["itens_removidos"] == ["Tocha"]
	assert campanha["local_atual"] == "Beco Escuro"

	main.aplicar_deltas_estado(campanha, {"delta_pv": -50})
	assert campanha["personagem"]["pv_atual"] == 0


def test_fluxo_completo_campanha_acao_e_rolagem(monkeypatch, tmp_path):
	cliente = configurar_ambiente_teste(monkeypatch, tmp_path)

	respostas_simuladas = iter([
		{
			"narracao": "Um guarda bloqueia o portão e exige explicações.",
			"local_atual": "Portão Norte",
			"requer_teste": True,
			"teste_atributo": "carisma",
			"teste_cd": 14,
			"teste_motivo": "Convencer o guarda a liberar a passagem.",
			"delta_pv": 0,
			"delta_ouro": 0,
			"itens_ganhos": [],
			"itens_removidos": [],
			"resumo_campanha": "Diante do Portão Norte.",
		},
		{
			"narracao": "O guarda desconfia e desfere um golpe com a lança antes de recuar.",
			"local_atual": "Portão Norte",
			"requer_teste": False,
			"teste_atributo": None,
			"teste_cd": None,
			"teste_motivo": None,
			"delta_pv": -3,
			"delta_ouro": 0,
			"itens_ganhos": ["Passe Rasgado"],
			"itens_removidos": [],
			"resumo_campanha": "Ferido no Portão Norte.",
		},
	])

	def simular_mestre(prompt, permitir_teste=True):
		return next(respostas_simuladas)

	monkeypatch.setattr(main, "consultar_mestre", simular_mestre)

	criacao = cliente.post(
		"/api/campanhas",
		json={
			"nome_personagem": "Kael",
			"classe": "ladino",
			"cenario": "Cidade murada sob toque de recolher",
		},
	)
	assert criacao.status_code == 201
	campanha = criacao.json()
	campanha_id = campanha["id"]

	acao = cliente.post(
		f"/api/campanhas/{campanha_id}/acao",
		json={"texto": "Tento persuadir o guarda a me deixar passar."},
	)
	assert acao.status_code == 200
	dados_acao = acao.json()
	assert dados_acao["teste_pendente"] is not None
	assert dados_acao["teste_pendente"]["atributo"] == "carisma"

	bloqueio = cliente.post(
		f"/api/campanhas/{campanha_id}/acao",
		json={"texto": "Ignoro o teste e saio correndo."},
	)
	assert bloqueio.status_code == 400

	rolagem = cliente.post(
		f"/api/campanhas/{campanha_id}/rolar",
		json={"valor_dado": 3},
	)
	assert rolagem.status_code == 200
	dados_rolagem = rolagem.json()
	assert dados_rolagem["rolagem"]["sucesso"] is False
	assert dados_rolagem["campanha"]["teste_pendente"] is None
	assert dados_rolagem["campanha"]["personagem"]["pv_atual"] == 7
	assert "Passe Rasgado" in dados_rolagem["campanha"]["personagem"]["inventario"]

	arquivo_salvo = tmp_path / f"{campanha_id}.json"
	assert arquivo_salvo.exists()


def test_dado_livre_invalido(monkeypatch, tmp_path):
	cliente = configurar_ambiente_teste(monkeypatch, tmp_path)
	criacao = cliente.post(
		"/api/campanhas",
		json={"nome_personagem": "Lyra", "classe": "mago"},
	)
	campanha_id = criacao.json()["id"]
	resposta = cliente.post(
		f"/api/campanhas/{campanha_id}/dado",
		json={"lados": 7},
	)
	assert resposta.status_code == 422
