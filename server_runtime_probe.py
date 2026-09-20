import json
import os
import socket
import threading
import time

from src.common.protocol import TipoMensagem, codificar_mensagem, criar_mensagem
from src.server.server import ServidorQuiz

log_path = os.path.join(os.getcwd(), 'server_runtime_probe_log.txt')

with open(log_path, 'w', encoding='utf-8') as log_file:
    log_file.write('START\n')
    servidor = ServidorQuiz(host='127.0.0.1', porta_tcp=5040, porta_udp=5041)
    servidor.iniciar_servidor_tcp()
    servidor.iniciar_servidor_udp()
    threading.Thread(target=servidor.aceitar_conexoes, daemon=True).start()
    threading.Thread(target=servidor.escutar_ping_udp, daemon=True).start()
    log_file.write('SERVER READY\n')

    c1 = socket.create_connection(('127.0.0.1', 5040), timeout=3)
    c2 = socket.create_connection(('127.0.0.1', 5040), timeout=3)
    log_file.write('CLIENTS CONNECTED\n')

    for ident, conn in [('player-1', c1), ('player-2', c2)]:
        msg = criar_mensagem(TipoMensagem.ENTRAR, {'id_jogador': ident, 'apelido': ident})
        conn.sendall(codificar_mensagem(msg))
        log_file.write(f'ENTER SENT {ident}\n')

    time.sleep(0.5)
    log_file.write(f'STATE A {servidor.salas}\n')
    log_file.write(f'STATE B {servidor.partidas_ativas}\n')
    log_file.write(f'STATE C {servidor.fila_espera}\n')

    for ident, conn in [('player-1', c1), ('player-2', c2)]:
        conn.settimeout(2)
        try:
            data = conn.recv(4096)
            log_file.write(f'RECV {ident} {data!r}\n')
        except Exception as exc:
            log_file.write(f'RECV ERROR {ident} {type(exc).__name__}: {exc}\n')

    for ident, conn in [('player-1', c1), ('player-2', c2)]:
        resposta = 'TCP' if ident == 'player-1' else 'UDP'
        msg = criar_mensagem(TipoMensagem.RESPOSTA, {'id_jogador': ident, 'rodada_id': 1, 'resposta': resposta})
        conn.sendall(codificar_mensagem(msg))
        log_file.write(f'ANSWER SENT {ident} {resposta}\n')

    for i in range(3):
        time.sleep(0.5)
        log_file.write(f'TICK {i} {servidor.salas} {servidor.partidas_ativas} {servidor.rodadas_por_sala}\n')
        for ident, conn in [('player-1', c1), ('player-2', c2)]:
            conn.settimeout(0.5)
            try:
                data = conn.recv(4096)
                log_file.write(f'LATE {ident} {data!r}\n')
            except socket.timeout:
                log_file.write(f'TIMEOUT {ident}\n')
            except Exception as exc:
                log_file.write(f'LATE ERROR {ident} {type(exc).__name__}: {exc}\n')

    c1.close(); c2.close(); servidor.fechar_servidor();
    log_file.write('DONE\n')
