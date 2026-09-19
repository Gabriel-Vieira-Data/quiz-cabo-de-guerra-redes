from src.server.server import ServidorQuiz


def test_servidor_cria_sala_e_inicia_partida_ao_ter_dois_jogadores():
    servidor = ServidorQuiz()

    servidor.registrar_jogador("player-1", object())
    servidor.registrar_jogador("player-2", object())

    sala = servidor.criar_sala("sala-1")
    assert sala["codigo"] == "sala-1"
    assert sala["jogadores"] == ["player-1", "player-2"]

    partida = servidor.iniciar_partida_em_sala("sala-1")
    assert partida["codigo"] == "sala-1"
    assert partida["rodada"] == 1
    assert partida["estado"] == "em_andamento"
