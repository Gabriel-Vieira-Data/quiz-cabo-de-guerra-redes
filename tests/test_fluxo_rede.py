import socket

from src.common.game_logic import resolverResultadoRodada
from src.server.server import ServidorQuiz


def test_servidor_registra_jogadores_e_processa_respostas():
    servidor = ServidorQuiz()
    socket1, socket2 = socket.socketpair()

    servidor.registrar_jogador("player-1", socket1)
    servidor.registrar_jogador("player-2", socket2)

    resultado = servidor.processar_resposta(
        jogador_a="player-1",
        jogador_b="player-2",
        resposta_a="TCP",
        resposta_b="UDP",
        resposta_correta="TCP",
    )

    assert resultado["vencedor"] == "player-1"
    assert resultado["delta_barra"] == 1
    assert servidor.estado_jogo["posicao_barra"] == 1


def test_logica_de_resultado_e_servidor_convergem_na_mesma_regra():
    resultado_servidor = resolverResultadoRodada(
        jogador_a="player-1",
        jogador_b="player-2",
        resposta_a="TCP",
        resposta_b="UDP",
        resposta_correta="TCP",
    )

    servidor = ServidorQuiz()
    resultado = servidor.processar_resposta(
        jogador_a="player-1",
        jogador_b="player-2",
        resposta_a="TCP",
        resposta_b="UDP",
        resposta_correta="TCP",
    )

    assert resultado == resultado_servidor
