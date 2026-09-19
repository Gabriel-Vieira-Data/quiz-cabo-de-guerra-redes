import threading
import time

from src.client.client import ClienteQuiz
from src.server.server import ServidorQuiz


def test_servidor_aceita_conexao_e_recebe_entrada_do_cliente():
    servidor = ServidorQuiz(porta_tcp=5010, porta_udp=5011)
    servidor.iniciar_servidor_tcp()

    thread_servidor = threading.Thread(target=servidor.aceitar_conexoes, daemon=True)
    thread_servidor.start()

    cliente = ClienteQuiz(porta_tcp=5010, porta_udp=5011)
    cliente.conectar()
    cliente.enviar_entrada("player-1", "Alice")

    time.sleep(0.2)

    assert "player-1" in servidor.jogadores_conectados
    mensagem = servidor.receber_mensagem("player-1")
    assert mensagem["tipo"] == "ENTRAR"
    assert mensagem["id_jogador"] == "player-1"
    assert mensagem["apelido"] == "Alice"

    cliente.socket_tcp.close()
    servidor.fechar_servidor()
