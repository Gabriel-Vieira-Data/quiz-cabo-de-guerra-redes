# [Origem: IA 88% · autoral 12%] Medido com git blame (ver USO_DE_IA.md).
import json
import socket
import threading

from src.client.client import ClienteQuiz
from src.server.server import ServidorQuiz


def _iniciar_servidor_udp(porta_udp):
    servidor = ServidorQuiz(porta_tcp=porta_udp - 1, porta_udp=porta_udp)
    servidor.iniciar_servidor_udp()
    threading.Thread(target=servidor.escutar_ping_udp, daemon=True).start()
    return servidor


def test_cliente_envia_ping_udp_e_servidor_responde_pong():
    servidor = _iniciar_servidor_udp(5031)
    cliente = ClienteQuiz(porta_tcp=5030, porta_udp=5031)
    try:
        latencia = cliente.medir_latencia("player-1", timeout=1.0)
        assert latencia is not None
        assert latencia >= 0
        assert cliente.latencia_ms == latencia
    finally:
        cliente.fechar()
        servidor.fechar_servidor()


def test_pong_ecoa_o_horario_do_ping():
    """O servidor devolve no PONG o mesmo "ts" do PING (é com ele que se calcula o RTT)."""
    servidor = _iniciar_servidor_udp(5033)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.settimeout(1.0)
        ping = {"tipo": "PING", "id_jogador": "player-1", "ts": 123.456}
        sock.sendto(json.dumps(ping).encode("utf-8"), ("127.0.0.1", 5033))
        dados, _ = sock.recvfrom(4096)
        pong = json.loads(dados.decode("utf-8"))
        assert pong["tipo"] == "PONG"
        assert pong["ts"] == 123.456
        assert pong["id_jogador"] == "player-1"
    finally:
        sock.close()
        servidor.fechar_servidor()


def test_cliente_ignora_pong_de_um_ping_antigo():
    """Um PONG atrasado (ts diferente) não pode ser usado para calcular a latência."""
    cliente = ClienteQuiz()
    falso_servidor = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        falso_servidor.bind(("127.0.0.1", 0))
        cliente.porta_udp = falso_servidor.getsockname()[1]
        ts = cliente.enviar_ping_udp("player-1")
        _, endereco_cliente = falso_servidor.recvfrom(4096)
        pong_antigo = {"tipo": "PONG", "id_jogador": "player-1", "ts": ts - 5}
        falso_servidor.sendto(json.dumps(pong_antigo).encode("utf-8"), endereco_cliente)

        assert cliente.receber_pong_udp(ts, timeout=0.3) is None
    finally:
        falso_servidor.close()
        cliente.fechar()
