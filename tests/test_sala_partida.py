# [Origem: autoral 57% · IA 43%] Medido com git blame.
from src.server.server import ServidorQuiz


def test_servidor_cria_sala_e_inicia_partida_ao_ter_dois_jogadores():
    servidor = ServidorQuiz()

    for id_jogador in ("player-1", "player-2"):
        servidor.processar_mensagem(
            {"tipo": "ENTRAR", "id_jogador": id_jogador, "apelido": id_jogador}, object()
        )

    sala = servidor.salas["sala-1"]
    assert sala["codigo"] == "sala-1"
    assert sala["jogadores"] == ["player-1", "player-2"]

    partida = servidor.partidas_ativas["sala-1"]
    assert partida["codigo"] == "sala-1"
    assert partida["rodada"] == 1
    assert partida["estado"] == "em_andamento"
