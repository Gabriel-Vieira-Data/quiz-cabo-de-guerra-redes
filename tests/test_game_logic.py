# [Origem: IA 62% · autoral 38%] Medido com git blame.
from src.common.game_logic import EstadoJogo


def test_estado_jogo_acompanha_rodadas_e_condicao_vitoria():
    jogo = EstadoJogo(maximo_rodadas=10)

    assert jogo.rodada_atual == 1
    assert jogo.maximo_rodadas == 10
    assert jogo.posicao_barra == 0

    jogo.avancar_rodada()

    assert jogo.rodada_atual == 2
    assert jogo.posicao_barra == 0

    jogo.registrarResultadoRodada("player-1")
    assert jogo.posicao_barra == 1

    assert jogo.vencedor is None


def test_estado_jogo_para_no_maximo_de_rodadas():
    jogo = EstadoJogo(maximo_rodadas=2)

    assert jogo.avancar_rodada() is True
    assert jogo.rodada_atual == 2
    assert jogo.avancar_rodada() is False
    assert jogo.rodada_atual == 2


def test_estado_jogo_acompanha_pontuacao_e_fim_do_jogo():
    # vantagem_para_vencer=2 → o jogo acaba quando a diferença de vitórias for 2
    jogo = EstadoJogo(maximo_rodadas=5, vantagem_para_vencer=2)

    jogo.registrarResultadoRodada("player-1")
    assert jogo.pontuacao_jogadores["player-1"] == 1
    assert jogo.posicao_barra == 1
    assert jogo.vencedor is None  # diferença de 1, ainda não acabou

    jogo.registrarResultadoRodada("player-1")
    assert jogo.pontuacao_jogadores["player-1"] == 2
    assert jogo.posicao_barra == 2   # corda na ponta (diferença de 2)
    assert jogo.vencedor == "player-1"

    jogo.registrarResultadoRodada("empate")
    assert jogo.pontuacao_jogadores["player-1"] == 2


# ---------------------------------------------------------------------------
# Regra de cabo de guerra: vitória por DIFERENÇA de 3 (não por pontos absolutos)
# ---------------------------------------------------------------------------

def test_cabo_de_guerra_nao_acaba_com_placar_3x2():
    """Placar 3x2 (diferença de 1) NÃO encerra o jogo: vale a diferença, não o total."""
    jogo = EstadoJogo()  # vantagem_para_vencer padrão = 3
    # A vence, B vence, A vence, B vence, A vence  → placar A=3, B=2, barra=+1
    for vencedor in ["player-1", "player-2", "player-1", "player-2", "player-1"]:
        jogo.registrarResultadoRodada(vencedor)

    assert jogo.pontuacao_jogadores["player-1"] == 3
    assert jogo.pontuacao_jogadores["player-2"] == 2
    assert jogo.posicao_barra == 1          # diferença real de vitórias
    assert jogo.vencedor is None            # jogo NÃO acabou (diferença é só 1)


def test_cabo_de_guerra_acaba_com_diferenca_de_3():
    """Vitória por knockout: quando um lado abre 3 de vantagem, a corda chega na ponta."""
    jogo = EstadoJogo()  # vantagem_para_vencer = 3
    # A vence 3 rodadas seguidas → barra vai a +3 → knockout
    jogo.registrarResultadoRodada("player-1")
    assert jogo.vencedor is None            # diferença 1
    jogo.registrarResultadoRodada("player-1")
    assert jogo.vencedor is None            # diferença 2
    jogo.registrarResultadoRodada("player-1")
    assert jogo.posicao_barra == 3
    assert jogo.vencedor == "player-1"      # diferença 3 → vitória


def test_cabo_de_guerra_corda_volta_ao_centro():
    """A corda deve voltar quando o adversário vence — é a essência do cabo de guerra."""
    jogo = EstadoJogo()
    jogo.registrarResultadoRodada("player-1")   # +1
    jogo.registrarResultadoRodada("player-1")   # +2
    jogo.registrarResultadoRodada("player-2")   # +1 (B puxou de volta)
    jogo.registrarResultadoRodada("player-2")   #  0 (centro)
    assert jogo.posicao_barra == 0
    assert jogo.vencedor is None
