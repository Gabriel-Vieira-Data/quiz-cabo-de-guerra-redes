from src.common.game_logic import RodadaJogo, EstadoJogo, resolverResultadoRodada


def test_rodada_inicia_com_barra_zero_e_pergunta_nao_respondida():
    rodada = RodadaJogo(rodada_id=1, pergunta="Qual protocolo é orientado à conexão?", resposta_correta="TCP")

    assert rodada.posicao_barra == 0
    assert rodada.pergunta == "Qual protocolo é orientado à conexão?"
    assert rodada.resposta_correta == "TCP"
    assert rodada.respondida is False


def test_resolver_resultado_rodada_da_vantagem_ao_primeiro_jogador_correto():
    resultado = resolverResultadoRodada(jogador_a="player-1", jogador_b="player-2", resposta_a="TCP", resposta_b="UDP")

    assert resultado["vencedor"] == "player-1"
    assert resultado["delta_barra"] == 1
    assert resultado["direcao_barra"] == 1


def test_estado_jogo_acompanha_rodadas_e_condicao_vitoria():
    jogo = EstadoJogo(maximo_rodadas=10)

    assert jogo.rodada_atual == 1
    assert jogo.maximo_rodadas == 10
    assert jogo.posicao_barra == 0

    jogo.avancar_rodada()

    assert jogo.rodada_atual == 2
    assert jogo.posicao_barra == 0

    jogo.atualizar_barra(1)
    assert jogo.posicao_barra == 1

    assert jogo.terminou() is False


def test_resolver_resultado_rodada_usa_resposta_correta_da_pergunta():
    resultado = resolverResultadoRodada(
        jogador_a="player-1",
        jogador_b="player-2",
        resposta_a="Paris",
        resposta_b="Roma",
        resposta_correta="Paris",
    )

    assert resultado == {"vencedor": "player-1", "delta_barra": 1, "direcao_barra": 1}


def test_estado_jogo_para_no_maximo_de_rodadas():
    jogo = EstadoJogo(maximo_rodadas=2)

    assert jogo.avancar_rodada() is True
    assert jogo.rodada_atual == 2
    assert jogo.avancar_rodada() is False
    assert jogo.rodada_atual == 2


def test_estado_jogo_acompanha_pontuacao_e_fim_do_jogo():
    jogo = EstadoJogo(maximo_rodadas=5, pontos_para_vencer=2)

    jogo.registrarResultadoRodada("player-1")
    assert jogo.pontuacao_jogadores["player-1"] == 1
    assert jogo.terminou() is False

    jogo.registrarResultadoRodada("player-1")
    assert jogo.pontuacao_jogadores["player-1"] == 2
    assert jogo.terminou() is True

    jogo.registrarResultadoRodada("empate")
    assert jogo.pontuacao_jogadores["player-1"] == 2
