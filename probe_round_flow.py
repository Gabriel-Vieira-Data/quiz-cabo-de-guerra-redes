import json
import socket
import threading
import time

from src.common.protocol import TipoMensagem, codificar_mensagem, criar_mensagem
from src.server.server import ServidorQuiz

log = []

servidor = ServidorQuiz(host='127.0.0.1', porta_tcp=5100, porta_udp=5101)
servidor.iniciar_servidor_tcp()
servidor.iniciar_servidor_udp()
threading.Thread(target=servidor.aceitar_conexoes, daemon=True).start()
threading.Thread(target=servidor.escutar_ping_udp, daemon=True).start()
log.append('server started')

conexoes = []
for ident in ['player-1', 'player-2']:
    conn = socket.create_connection(('127.0.0.1', 5100), timeout=3)
    conexoes.append((ident, conn))
    conn.sendall(codificar_mensagem(criar_mensagem(TipoMensagem.ENTRAR, {'id_jogador': ident, 'apelido': ident})))
    log.append(f'enter sent {ident}')

for _ in range(5):
    time.sleep(0.2)
    log.append(f'state {_} {servidor.salas} {servidor.partidas_ativas} {servidor.fila_espera} {servidor.rodadas_por_sala}')
    for ident, conn in conexoes:
        conn.settimeout(1)
        try:
            data = conn.recv(4096)
            log.append(f'recv {ident} {data!r}')
        except Exception as exc:
            log.append(f'recv err {ident} {type(exc).__name__}: {exc}')

for ident, conn in conexoes:
    resposta = 'TCP' if ident == 'player-1' else 'UDP'
    conn.sendall(codificar_mensagem(criar_mensagem(TipoMensagem.RESPOSTA, {'id_jogador': ident, 'rodada_id': 1, 'resposta': resposta})))
    log.append(f'answer sent {ident} {resposta}')

for _ in range(10):
    time.sleep(0.5)
    log.append(f'after answer state {_} {servidor.salas} {servidor.partidas_ativas} {servidor.rodadas_por_sala}')
    for ident, conn in conexoes:
        conn.settimeout(0.8)
        try:
            data = conn.recv(4096)
            log.append(f'late {ident} {data!r}')
        except Exception as exc:
            log.append(f'late err {ident} {type(exc).__name__}: {exc}')

for _, conn in conexoes:
    conn.close()
servidor.fechar_servidor()

with open('probe_round_flow_log.txt', 'w', encoding='utf-8') as f:
    f.write('\n'.join(log))
print('probe finished')
