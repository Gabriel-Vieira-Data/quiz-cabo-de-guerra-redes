import socket
import threading
import time

from src.client.client import ClienteQuiz
from src.server.server import ServidorQuiz


def test_cliente_envia_ping_udp_e_servidor_responde_pong():
    servidor = ServidorQuiz(porta_tcp=5030, porta_udp=5031)
    servidor.iniciar_servidor_udp()

    thread_servidor = threading.Thread(target=servidor.escutar_ping_udp, daemon=True)
    thread_servidor.start()

    cliente = ClienteQuiz(porta_tcp=5030, porta_udp=5031)
    cliente.enviar_ping_udp()

    time.sleep(0.2)

    assert servidor.ultimo_ping is not None
    assert servidor.ultimo_ping["id_jogador"] == "cliente"

    cliente.socket_udp.close()
    servidor.fechar_servidor()
