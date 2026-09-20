import json
import socket
import threading
import time

from src.common.protocol import TipoMensagem, codificar_mensagem, criar_mensagem
from src.server.server import ServidorQuiz


print('START')
servidor = ServidorQuiz(host='127.0.0.1', porta_tcp=5000, porta_udp=5001)
servidor.iniciar_servidor_tcp()
servidor.iniciar_servidor_udp()
threading.Thread(target=servidor.aceitar_conexoes, daemon=True).start()
threading.Thread(target=servidor.escutar_ping_udp, daemon=True).start()
print('SERVER STARTED')

s1 = socket.create_connection(('127.0.0.1', 5000), timeout=2)
s2 = socket.create_connection(('127.0.0.1', 5000), timeout=2)
print('CLIENTS CONNECTED')

for ident, sock in [('player-1', s1), ('player-2', s2)]:
    msg = criar_mensagem(TipoMensagem.ENTRAR, {'id_jogador': ident, 'apelido': ident})
    sock.sendall(codificar_mensagem(msg))
    print('SENT ENTER', ident)


def recv_one(sock, label):
    sock.settimeout(2)
    try:
        data = sock.recv(4096)
        print(label, 'RAW', data)
        if not data:
            return None
        if len(data) >= 4:
            tamanho = int.from_bytes(data[:4], byteorder='big', signed=False)
            if len(data) >= 4 + tamanho:
                payload = data[4:4+tamanho]
                print(label, 'PAYLOAD', payload)
                return json.loads(payload)
        return json.loads(data.decode('utf-8'))
    except Exception as exc:
        print(label, 'ERROR', repr(exc))
        return None

for i in range(2):
    m1 = recv_one(s1, 'S1')
    m2 = recv_one(s2, 'S2')
    print('ROUND0', i, 'M1=', m1, 'M2=', m2)
    time.sleep(0.2)

print('SENDING ANSWERS')
s1.sendall(codificar_mensagem(criar_mensagem(TipoMensagem.RESPOSTA, {'id_jogador': 'player-1', 'rodada_id': 1, 'resposta': 'TCP'})))
s2.sendall(codificar_mensagem(criar_mensagem(TipoMensagem.RESPOSTA, {'id_jogador': 'player-2', 'rodada_id': 1, 'resposta': 'UDP'})))

for i in range(5):
    print('AFTER', i, 'S1', recv_one(s1, 'S1'))
    print('AFTER', i, 'S2', recv_one(s2, 'S2'))
    time.sleep(0.5)

print('FINAL SALAS', servidor.salas)
print('FINAL PONTOS', servidor.estado_jogo['pontuacao'])
print('FINAL PARTIDAS', servidor.partidas_ativas)
print('FINAL RODADAS', servidor.rodadas_por_sala)
servidor.fechar_servidor()
s1.close(); s2.close();
