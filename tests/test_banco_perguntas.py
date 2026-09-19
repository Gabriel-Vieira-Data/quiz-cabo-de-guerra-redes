from src.common.banco_perguntas import BancoPerguntas
from src.server.server import ServidorQuiz


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
    servidor = ServidorQuiz()
    servidor.registrar_jogador("player-1", object())
    servidor.registrar_jogador("player-2", object())

    pergunta = servidor.selecionar_pergunta_para_sala("sala-1")

    assert pergunta is not None
    assert "pergunta" in pergunta
    assert len(pergunta["opcoes"]) == 4
    assert pergunta["resposta_correta"] in pergunta["opcoes"]


def test_servidor_usa_tempo_limite_e_uma_resposta_por_jogador_por_rodada():
    servidor = ServidorQuiz()
    servidor.registrar_jogador("player-1", object())
    servidor.registrar_jogador("player-2", object())
    sala = servidor.criar_sala_para_espera()
    assert sala is not None

    pergunta = servidor.selecionar_pergunta_para_sala("sala-1")
    assert pergunta is not None
    assert pergunta["resposta_correta"] in pergunta["opcoes"]

    primeiro_resultado = servidor.registrar_resposta_jogador("sala-1", 1, "player-1", pergunta["resposta_correta"])
    assert primeiro_resultado["vencedor"] == "player-1"

    segundo_tentativa = servidor.registrar_resposta_jogador("sala-1", 1, "player-1", "UDP")
    assert segundo_tentativa is None

    resultado_timeout = servidor.registrar_resposta_jogador("sala-1", 1, "player-2", "UDP")
    assert resultado_timeout is None

    assert servidor.tempo_limite_rodada == 30


def test_servidor_vence_no_primeiro_acerto_dentro_do_tempo_limite():
    servidor = ServidorQuiz()
    servidor.registrar_jogador("player-1", object())
    servidor.registrar_jogador("player-2", object())
    servidor.criar_sala_para_espera()

    pergunta = servidor.selecionar_pergunta_para_sala("sala-1")
    resposta_correta = pergunta["resposta_correta"]

    resultado = servidor.registrar_resposta_jogador("sala-1", 1, "player-1", resposta_correta)

    assert resultado is not None
    assert resultado["vencedor"] == "player-1"
    assert servidor.estado_jogo["pontuacao"]["player-1"] == 1
