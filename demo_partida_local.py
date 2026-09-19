import threading
import time

from src.client.client import ClienteQuiz
from src.server.server import ServidorQuiz


def iniciar_servidor():
    servidor = ServidorQuiz(host="127.0.0.1", porta_tcp=5000, porta_udp=5001)
    servidor.iniciar_servidor_tcp()
    servidor.iniciar_servidor_udp()

    thread_aceita = threading.Thread(target=servidor.aceitar_conexoes, daemon=True)
    thread_aceita.start()

    print("[servidor] ouvindo em 127.0.0.1:5000")
    return servidor


def simular_jogador(id_jogador: str, apelido: str, porta_udp: int):
    cliente = ClienteQuiz(host="127.0.0.1", porta_tcp=5000, porta_udp=porta_udp)
    cliente.conectar()
    cliente.enviar_entrada(id_jogador, apelido)
    print(f"[{apelido}] entrou na partida")

    mensagem = cliente.receber_mensagem()
    print(f"[{apelido}] recebeu: {mensagem}")

    resposta = "TCP" if apelido == "Alice" else "UDP"
    cliente.enviar_resposta(id_jogador, mensagem["rodada_id"], resposta)
    print(f"[{apelido}] enviou resposta: {resposta}")

    time.sleep(0.2)
    cliente.socket_tcp.close()
    cliente.socket_udp.close()
    return mensagem


if __name__ == "__main__":
    servidor = iniciar_servidor()

    thread_alice = threading.Thread(target=simular_jogador, args=("player-1", "Alice", 5002), daemon=True)
    thread_bob = threading.Thread(target=simular_jogador, args=("player-2", "Bob", 5003), daemon=True)

    thread_alice.start()
    time.sleep(0.2)
    thread_bob.start()

    thread_alice.join(timeout=5)
    thread_bob.join(timeout=5)

    print("[estado do servidor] salas:", servidor.salas)
    print("[estado do servidor] partidas:", servidor.partidas_ativas)
    print("[estado do servidor] pontuacao:", servidor.estado_jogo["pontuacao"])

    servidor.fechar_servidor()
