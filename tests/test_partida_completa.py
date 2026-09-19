from src.common.game_logic import EstadoJogo, resolverResultadoRodada
from src.server.server import ServidorQuiz


def test_servidor_controla_estado_da_partida_ate_a_vitoria():
    servidor = ServidorQuiz()
    servidor.estado_jogo = {
        "posicao_barra": 0,
        "rodada": 1,
        "maximo_rodadas": 5,
    }

    jogo = EstadoJogo(maximo_rodadas=5, pontos_para_vencer=2)
    jogo.registrarResultadoRodada("player-1")
    jogo.registrarResultadoRodada("player-1")

    assert jogo.terminou() is True
    assert jogo.vencedor == "player-1"

    resultado = resolverResultadoRodada(
        jogador_a="player-1",
        jogador_b="player-2",
        resposta_a="TCP",
        resposta_b="UDP",
        resposta_correta="TCP",
    )

    assert resultado["vencedor"] == "player-1"
    assert servidor.estado_jogo["rodada"] == 1
