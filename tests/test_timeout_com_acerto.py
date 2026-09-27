# [Origem: IA] Medido com git blame.
"""
Regressão: se um jogador acerta e o outro NÃO responde, ao estourar o tempo
da rodada quem acertou deve pontuar (o timeout não pode zerar a rodada).
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


def test_timeout_da_ponto_a_quem_acertou_sozinho():
    """player-1 acerta, player-2 não responde → no timeout, player-1 pontua."""
    servidor, s1, s2 = _iniciar_partida()

    pergunta = servidor.perguntas_rodada.get("sala-1", {})
    correta = pergunta.get("resposta_correta", "TCP")

    # player-1 responde certo; player-2 fica em silêncio
    servidor.registrar_resposta_jogador("sala-1", 1, "player-1", correta)

    # Dispara o timeout manualmente (simula o tempo da rodada estourar)
    servidor._timeout_rodada("sala-1")

    estado = servidor.estado_por_sala["sala-1"]
    assert estado.pontuacao_jogadores["player-1"] == 1, "quem acertou sozinho deve pontuar no timeout"
    assert estado.pontuacao_jogadores["player-2"] == 0
    assert estado.posicao_barra == 1  # corda puxou 1 para o lado de player-1


def test_timeout_sem_acertos_nao_da_ponto():
    """Se ninguém que respondeu acertou (ou ninguém respondeu), não há vencedor."""
    servidor, s1, s2 = _iniciar_partida()

    pergunta = servidor.perguntas_rodada.get("sala-1", {})
    correta = pergunta.get("resposta_correta", "TCP")
    opcoes = pergunta.get("opcoes", [])
    errada = next((o for o in opcoes if o != correta), "ERRADA")

    # player-1 responde ERRADO; player-2 não responde
    servidor.registrar_resposta_jogador("sala-1", 1, "player-1", errada)
    servidor._timeout_rodada("sala-1")

    estado = servidor.estado_por_sala["sala-1"]
    assert estado.pontuacao_jogadores["player-1"] == 0
    assert estado.pontuacao_jogadores["player-2"] == 0
    assert estado.posicao_barra == 0


def test_timeout_da_ponto_a_quem_acertou_primeiro():
    """Se os dois acertaram mas o timeout resolve, vence quem respondeu antes."""
    servidor, s1, s2 = _iniciar_partida()

    pergunta = servidor.perguntas_rodada.get("sala-1", {})
    correta = pergunta.get("resposta_correta", "TCP")

    # Força o modo de espera dupla continuar aberto marcando só 1 resposta por vez
    # não é possível aqui (ambos resolveriam), então testamos via timeout direto:
    estado_rodada = servidor.rodadas_por_sala["sala-1"]
    import time
    estado_rodada["respostas"]["player-2"] = {"resposta": correta.strip().upper(), "tempo": time.time()}
    estado_rodada["respostas"]["player-1"] = {"resposta": correta.strip().upper(), "tempo": time.time() + 0.5}

    servidor._timeout_rodada("sala-1")

    estado = servidor.estado_por_sala["sala-1"]
    # player-2 respondeu antes (tempo menor) → vence
    assert estado.pontuacao_jogadores["player-2"] == 1
    assert estado.pontuacao_jogadores["player-1"] == 0
