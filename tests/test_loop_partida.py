from src.server.server import ServidorQuiz


def test_servidor_controla_pontuacao_e_rodadas_da_partida():
    servidor = ServidorQuiz()
    servidor.registrar_jogador("player-1", object())
    servidor.registrar_jogador("player-2", object())

    partida = servidor.iniciar_partida()
    assert partida["rodada"] == 1
    assert partida["maximo_rodadas"] == 10
    assert servidor.estado_jogo["pontuacao"]["player-1"] == 0

    servidor.registrar_pontuacao("player-1")
    servidor.registrar_pontuacao("player-1")

    assert servidor.estado_jogo["pontuacao"]["player-1"] == 2
    assert servidor.estado_jogo["vencedor"] == "player-1"

    assert servidor.avancar_rodada() is False
    assert servidor.estado_jogo["rodada"] == 1
