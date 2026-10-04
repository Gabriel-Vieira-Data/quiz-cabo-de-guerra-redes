# [Origem: IA] Medido com git blame (ver USO_DE_IA.md).
"""
Várias partidas ao mesmo tempo:
  - cada dupla que entra ganha a sua própria sala;
  - uma sala nova não apaga nem interfere nas que já estão em andamento;
  - o número de uma sala encerrada volta a ficar livre.
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

    def tipos(self):
        return [m["tipo"] for m in self.mensagens]


def _entrar(servidor, id_jogador, sock):
    return servidor.processar_mensagem(
        {"tipo": "ENTRAR", "id_jogador": id_jogador, "apelido": id_jogador}, sock
    )


def _quatro_jogadores():
    servidor = ServidorQuiz()
    socks = {jid: SoqueteFake() for jid in ("player-1", "player-2", "player-3", "player-4")}
    for jid, sock in socks.items():
        _entrar(servidor, jid, sock)
    return servidor, socks


def test_terceiro_e_quarto_jogador_ganham_outra_sala():
    servidor, socks = _quatro_jogadores()

    assert servidor.salas["sala-1"]["jogadores"] == ["player-1", "player-2"]
    assert servidor.salas["sala-2"]["jogadores"] == ["player-3", "player-4"]
    assert set(servidor.partidas_ativas) == {"sala-1", "sala-2"}
    # Os quatro receberam a primeira pergunta da sua sala.
    for sock in socks.values():
        assert "PERGUNTA" in sock.tipos()
    servidor.fechar_servidor()


def test_resposta_numa_sala_nao_afeta_a_outra():
    servidor, socks = _quatro_jogadores()
    certa = servidor.perguntas_rodada["sala-1"]["resposta_correta"]

    servidor.processar_mensagem(
        {"tipo": "RESPOSTA", "id_jogador": "player-1", "rodada_id": 1, "resposta": certa},
        socks["player-1"],
    )
    servidor.processar_mensagem(
        {"tipo": "RESPOSTA", "id_jogador": "player-2", "rodada_id": 1, "resposta": "errada"},
        socks["player-2"],
    )

    assert servidor.estado_por_sala["sala-1"].pontuacao_jogadores["player-1"] == 1
    # A sala-2 continua na rodada 1, sem pontos e sem FIM_RODADA.
    assert servidor.estado_por_sala["sala-2"].pontuacao_jogadores == {"player-3": 0, "player-4": 0}
    assert "FIM_RODADA" not in socks["player-3"].tipos()
    assert "FIM_RODADA" not in socks["player-4"].tipos()
    servidor.fechar_servidor()


def test_fim_de_jogo_numa_sala_mantem_a_outra():
    servidor, socks = _quatro_jogadores()
    estado = servidor.estado_por_sala["sala-1"]
    servidor._enviar_fim_jogo("sala-1", "player-1", estado)

    assert "sala-1" not in servidor.salas
    assert servidor.salas["sala-2"]["jogadores"] == ["player-3", "player-4"]
    assert "FIM_JOGO" not in socks["player-3"].tipos()
    servidor.fechar_servidor()


def test_codigo_de_sala_encerrada_volta_a_ficar_livre():
    servidor, socks = _quatro_jogadores()
    servidor._enviar_fim_jogo("sala-1", "player-1", servidor.estado_por_sala["sala-1"])

    # A dupla da sala-1 joga de novo e recebe o número livre (sala-1).
    _entrar(servidor, "player-1", socks["player-1"])
    sala = _entrar(servidor, "player-2", socks["player-2"])

    assert sala["codigo"] == "sala-1"
    assert set(servidor.salas) == {"sala-1", "sala-2"}
    servidor.fechar_servidor()


def test_entrar_de_novo_durante_a_partida_nao_coloca_em_duas_salas():
    servidor, socks = _quatro_jogadores()

    # player-1 reenvia ENTRAR no mesmo socket com a partida em andamento.
    sala = _entrar(servidor, "player-1", socks["player-1"])

    assert sala["codigo"] == "sala-1"
    assert "player-1" not in servidor.fila_espera
    bem_vindo = [m for m in socks["player-1"].mensagens if m["tipo"] == "BEM_VINDO"][-1]
    assert bem_vindo["em_partida"] is True
    assert bem_vindo["codigo_sala"] == "sala-1"
    servidor.fechar_servidor()


def test_queda_numa_sala_so_avisa_o_adversario_dela():
    servidor, socks = _quatro_jogadores()
    servidor._tratar_desconexao_de_socket(socks["player-3"])

    assert servidor.rodadas_por_sala["sala-2"]["pausada"] is True
    assert not servidor.rodadas_por_sala["sala-1"].get("pausada")
    assert "DESCONEXAO" in socks["player-4"].tipos()
    assert "DESCONEXAO" not in socks["player-1"].tipos()
    assert "DESCONEXAO" not in socks["player-2"].tipos()
    servidor.fechar_servidor()
