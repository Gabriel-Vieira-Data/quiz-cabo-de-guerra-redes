from src.server.server import ServidorQuiz


def test_servidor_organiza_fila_de_espera_e_aceita_sala_com_dois_jogadores():
    servidor = ServidorQuiz()

    servidor.adicionar_jogador_espera("player-1")
    servidor.adicionar_jogador_espera("player-2")

    sala = servidor.criar_sala_para_espera()

    assert sala["codigo"] == "sala-1"
    assert sala["jogadores"] == ["player-1", "player-2"]
    assert servidor.fila_espera == []


def test_servidor_cria_sala_automaticamente_ao_registrar_segundo_jogador():
    servidor = ServidorQuiz()

    servidor.registrar_jogador("player-1", object())
    sala = servidor.registrar_jogador("player-2", object())

    assert sala is not None
    assert sala["codigo"] == "sala-1"
    assert sala["jogadores"] == ["player-1", "player-2"]
    assert servidor.fila_espera == []
