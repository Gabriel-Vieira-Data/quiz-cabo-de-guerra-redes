import json
import socket
import threading
import time

from src.common.protocol import TipoMensagem, codificar_mensagem, criar_mensagem
from src.server.server import ServidorQuiz

log = []

servidor = ServidorQuiz(host='127.0.0.1', porta_tcp=5010, porta_udp=5011)
servidor.iniciar_servidor_tcp()
servidor.iniciar_servidor_udp()
threading.Thread(target=servidor.aceitar_conexoes, daemon=True).start()
threading.Thread(target=servidor.escutar_ping_udp, daemon=True).start()

socks = []
for ident in ['player-1', 'player-2']:
    s = socket.create_connection(('127.0.0.1', 5010), timeout=3)
    socks.append((ident, s))
    log.append(f'CONNECTED {ident}')
    s.sendall(codificar_mensagem(criar_mensagem(TipoMensagem.ENTRAR, {'id_jogador': ident, 'apelido': ident})))
    log.append(f'ENTER_SENT {ident}')

for ident, sock in socks:
    sock.settimeout(1)
    try:
        data = sock.recv(4096)
        log.append(f'RECV {ident} {data!r}')
    except Exception as exc:
        log.append(f'RECV_ERR {ident} {type(exc).__name__}: {exc}')

log.append(f'STATE_AFTER_ENTER {servidor.salas} {servidor.partidas_ativas} {servidor.fila_espera}')

for ident, sock in socks:
    answer = 'TCP' if ident == 'player-1' else 'UDP'
    sock.sendall(codificar_mensagem(criar_mensagem(TipoMensagem.RESPOSTA, {'id_jogador': ident, 'rodada_id': 1, 'resposta': answer})))
    log.append(f'ANSWER_SENT {ident} {answer}')

for tick in range(4):
    time.sleep(0.5)
    log.append(f'TICK {tick} {servidor.salas} {servidor.partidas_ativas} {servidor.rodadas_por_sala}')
    for ident, sock in socks:
        sock.settimeout(0.5)
        try:
            data = sock.recv(4096)
            log.append(f'LATE {ident} {data!r}')
        except socket.timeout:
            log.append(f'TIMEOUT {ident}')
        except Exception as exc:
            log.append(f'LATE_ERR {ident} {type(exc).__name__}: {exc}')

for _, sock in socks:
    sock.close()
servidor.fechar_servidor()

with open('tmp_runtime_check_output.txt', 'w', encoding='utf-8') as f:
    f.write('\n'.join(log))
print('done')
