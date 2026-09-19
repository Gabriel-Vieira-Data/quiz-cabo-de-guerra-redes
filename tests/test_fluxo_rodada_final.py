from src.server.server import ServidorQuiz


def test_servidor_processa_rodada_e_acumula_pontuacao():
    servidor = ServidorQuiz()
    servidor.registrar_jogador("player-1", object())
    servidor.registrar_jogador("player-2", object())
    servidor.iniciar_partida()

    resultado = servidor.processar_resposta(
        jogador_a="player-1",
        jogador_b="player-2",
        resposta_a="TCP",
        resposta_b="UDP",
        resposta_correta="TCP",
    )

    assert resultado["vencedor"] == "player-1"
    assert resultado["delta_barra"] == 1
    assert servidor.estado_jogo["pontuacao"]["player-1"] == 1
    assert servidor.estado_jogo["posicao_barra"] == 1
