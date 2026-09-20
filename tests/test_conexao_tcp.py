import threading
import time

from src.client.client import ClienteQuiz
from src.server.server import ServidorQuiz


def test_servidor_aceita_conexao_e_recebe_entrada_do_cliente():
    import time as _time
    servidor = ServidorQuiz(porta_tcp=5012, porta_udp=5013)
    servidor.iniciar_servidor_tcp()

    thread_servidor = threading.Thread(target=servidor.aceitar_conexoes, daemon=True)
    thread_servidor.start()

    # Aguarda o servidor estar pronto
    _time.sleep(0.1)

    cliente = ClienteQuiz(porta_tcp=5012, porta_udp=5013)
    cliente.conectar()
    cliente.enviar_entrada("player-1", "Alice")

    # Polling: aguarda até 2s para o registro aparecer
    for _ in range(20):
        _time.sleep(0.1)
        if "player-1" in servidor.jogadores_conectados:
            break

    assert "player-1" in servidor.jogadores_conectados

    cliente.socket_tcp.close()
    servidor.fechar_servidor()
