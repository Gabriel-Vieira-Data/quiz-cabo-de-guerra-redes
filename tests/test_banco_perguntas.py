# [Origem: IA 55% · autoral 45%] Medido com git blame (ver USO_DE_IA.md).
from src.common.banco_perguntas import BancoPerguntas
from src.server.server import ServidorQuiz


def _iniciar_partida():
    """Dois jogadores enviam ENTRAR (mesmo caminho da rede real) e a partida começa."""
    servidor = ServidorQuiz()
    for id_jogador in ("player-1", "player-2"):
        servidor.processar_mensagem(
            {"tipo": "ENTRAR", "id_jogador": id_jogador, "apelido": id_jogador}, object()
        )
    return servidor


def test_banco_tem_30_perguntas_relacionadas_a_redes():
    banco = BancoPerguntas()
    perguntas = banco.obter_perguntas()

    assert len(perguntas) >= 30
    assert all(
        set(pergunta.keys()) >= {"pergunta", "opcoes", "resposta_correta"}
        for pergunta in perguntas
    )
    assert all(len(pergunta["opcoes"]) == 4 for pergunta in perguntas)


def test_servidor_seleciona_pergunta_do_banco_para_a_sala():
    servidor = _iniciar_partida()

    pergunta = servidor.selecionar_pergunta_para_sala("sala-1")

    assert pergunta is not None
    assert "pergunta" in pergunta
    assert len(pergunta["opcoes"]) == 4
    assert pergunta["resposta_correta"] in pergunta["opcoes"]


def test_servidor_usa_tempo_limite_e_uma_resposta_por_jogador_por_rodada():
    servidor = _iniciar_partida()

    # Pergunta já foi selecionada pelo _iniciar_primeira_rodada
    pergunta = servidor.perguntas_rodada.get("sala-1", {})
    assert pergunta is not None
    assert pergunta.get("resposta_correta") in pergunta.get("opcoes", [])

    resposta_certa = pergunta["resposta_correta"]
    opcoes = pergunta.get("opcoes", [])
    resposta_errada = next((op for op in opcoes if op != resposta_certa), "ERRADA")

    # Primeiro jogador responde certo — deve aguardar o segundo
    primeiro_resultado = servidor.registrar_resposta_jogador("sala-1", 1, "player-1", resposta_certa)
    assert primeiro_resultado is None

    # Mesmo jogador tenta responder de novo — bloqueado
    segundo_tentativa = servidor.registrar_resposta_jogador("sala-1", 1, "player-1", resposta_errada)
    assert segundo_tentativa is None

    # Segundo jogador responde errado — fecha a rodada com player-1 vencendo
    resultado_final = servidor.registrar_resposta_jogador("sala-1", 1, "player-2", resposta_errada)
    assert resultado_final is not None
    assert resultado_final["vencedor"] == "player-1"

    assert servidor.tempo_limite_rodada == 30


def test_servidor_vence_no_primeiro_acerto_dentro_do_tempo_limite():
    servidor = _iniciar_partida()

    pergunta = servidor.perguntas_rodada.get("sala-1", {})
    resposta_correta = pergunta.get("resposta_correta", "TCP")
    opcoes = pergunta.get("opcoes", [])
    resposta_errada = next((op for op in opcoes if op != resposta_correta), "ERRADA")

    # Ambos respondem — player-1 acerta, player-2 erra
    servidor.registrar_resposta_jogador("sala-1", 1, "player-1", resposta_correta)
    resultado = servidor.registrar_resposta_jogador("sala-1", 1, "player-2", resposta_errada)

    assert resultado is not None
    assert resultado["vencedor"] == "player-1"
    assert servidor.estado_por_sala["sala-1"].pontuacao_jogadores["player-1"] == 1
