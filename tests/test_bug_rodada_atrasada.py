# [Origem: IA] Medido com git blame (ver USO_DE_IA.md).
"""
Regressão: uma RESPOSTA com rodada_id diferente da rodada atual deve ser
ignorada. Isso evita que uma resposta atrasada (por latência) da rodada
anterior seja contada na rodada nova, roubando a vitória.
"""
import json

from src.server.server import ServidorQuiz


class SoqueteFake:
    def __init__(self):
        self.mensagens = []

    def sendall(self, dados):
        self.mensagens.append(json.loads(dados.decode("utf-8")))

    def close(self):
        pass


def _iniciar_partida():
    servidor = ServidorQuiz()
    s1, s2 = SoqueteFake(), SoqueteFake()
    servidor.processar_mensagem({"tipo": "ENTRAR", "id_jogador": "player-1", "apelido": "Alice"}, s1)
    servidor.processar_mensagem({"tipo": "ENTRAR", "id_jogador": "player-2", "apelido": "Bob"}, s2)
    return servidor, s1, s2


def test_resposta_de_rodada_antiga_e_ignorada():
    servidor, s1, s2 = _iniciar_partida()

    # A rodada atual é a 1. Uma resposta marcada como rodada_id=0 (antiga)
    # deve ser ignorada — não registra nada.
    resultado = servidor.registrar_resposta_jogador("sala-1", 0, "player-1", "TCP")
    assert resultado is None

    estado_rodada = servidor.rodadas_por_sala["sala-1"]
    assert "player-1" not in estado_rodada["respostas"]


def test_resposta_da_rodada_atual_e_aceita():
    servidor, s1, s2 = _iniciar_partida()

    pergunta = servidor.perguntas_rodada.get("sala-1", {})
    correta = pergunta.get("resposta_correta", "TCP")

    # rodada_id correto (1) → resposta é registrada normalmente
    resultado = servidor.registrar_resposta_jogador("sala-1", 1, "player-1", correta)
    assert resultado is None  # aguardando o 2º jogador
    estado_rodada = servidor.rodadas_por_sala["sala-1"]
    assert "player-1" in estado_rodada["respostas"]


def test_rodada_id_do_estado_bate_com_rodada_do_jogo():
    servidor, s1, s2 = _iniciar_partida()
    estado_rodada = servidor.rodadas_por_sala["sala-1"]
    estado_jogo = servidor.estado_por_sala["sala-1"]
    assert estado_rodada["rodada_id"] == estado_jogo.rodada_atual
