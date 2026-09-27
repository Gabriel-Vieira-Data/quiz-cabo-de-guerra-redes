# [Origem: IA 89% · autoral 11%] Medido com git blame (ver USO_DE_IA.md).
import threading

from src.client.client import ClienteQuiz
from src.server.server import ServidorQuiz


def _esperar_tipo(cliente, tipo):
    """Lê mensagens até chegar uma do tipo pedido (ou a conexão fechar/dar timeout)."""
    mensagem = cliente.receber_mensagem()
    while mensagem is not None and mensagem.get("tipo") != tipo:
        mensagem = cliente.receber_mensagem()
    return mensagem


def test_dois_clientes_recebem_pergunta_respondem_e_recebem_resultado():
    """Fluxo real por TCP: ENTRAR → PERGUNTA → RESPOSTA → FIM_RODADA."""
    servidor = ServidorQuiz(porta_tcp=5020, porta_udp=5021)
    servidor.iniciar_servidor_tcp()
    threading.Thread(target=servidor.aceitar_conexoes, daemon=True).start()

    alice = ClienteQuiz(porta_tcp=5020, porta_udp=5021)
    bob = ClienteQuiz(porta_tcp=5020, porta_udp=5021)
    try:
        for cliente, id_jogador, apelido in ((alice, "player-1", "Alice"), (bob, "player-2", "Bob")):
            cliente.conectar()
            cliente.socket_tcp.settimeout(3)   # não trava o teste se algo der errado
            cliente.enviar_entrada(id_jogador, apelido)

        pergunta_alice = _esperar_tipo(alice, "PERGUNTA")
        pergunta_bob = _esperar_tipo(bob, "PERGUNTA")
        assert pergunta_alice is not None and pergunta_bob is not None
        assert pergunta_alice["pergunta"] == pergunta_bob["pergunta"]
        assert "resposta_correta" not in pergunta_alice   # gabarito não vai ao cliente

        certa = servidor.perguntas_rodada["sala-1"]["resposta_correta"]
        errada = next(op for op in pergunta_alice["opcoes"] if op != certa)
        alice.enviar_resposta("player-1", pergunta_alice["rodada_id"], certa)
        bob.enviar_resposta("player-2", pergunta_bob["rodada_id"], errada)

        fim_rodada = _esperar_tipo(alice, "FIM_RODADA")
        assert fim_rodada is not None
        assert fim_rodada["vencedor"] == "player-1"
        assert fim_rodada["resposta_correta"] == certa
    finally:
        alice.fechar()
        bob.fechar()
        servidor.fechar_servidor()
