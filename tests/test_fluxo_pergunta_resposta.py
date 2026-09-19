import threading
import time

from src.client.client import ClienteQuiz
from src.server.server import ServidorQuiz


def test_cliente_recebe_pergunta_e_envia_resposta():
    servidor = ServidorQuiz(porta_tcp=5020, porta_udp=5021)
    servidor.iniciar_servidor_tcp()

    thread_servidor = threading.Thread(target=servidor.aceitar_conexoes, daemon=True)
    thread_servidor.start()

    cliente = ClienteQuiz(porta_tcp=5020, porta_udp=5021)
    cliente.conectar()
    cliente.enviar_entrada("player-1", "Alice")

    time.sleep(0.2)

    servidor.lidar_com_pergunta({
        "rodada_id": 1,
        "pergunta": "Qual protocolo é orientado à conexão?",
        "opcoes": ["TCP", "UDP", "ICMP", "ARP"],
        "tempo_limite": 10,
    })

    mensagem = cliente.receber_mensagem()
    assert mensagem["tipo"] == "PERGUNTA"
    assert mensagem["pergunta"] == "Qual protocolo é orientado à conexão?"

    cliente.enviar_resposta("player-1", 1, "TCP")
    resultado = servidor.processar_resposta(
        jogador_a="player-1",
        jogador_b="player-2",
        resposta_a="TCP",
        resposta_b="UDP",
        resposta_correta="TCP",
    )

    assert resultado["vencedor"] == "player-1"

    cliente.socket_tcp.close()
    servidor.fechar_servidor()
