import json
import socket
import threading
import time

from src.server.server import ServidorQuiz

servidor = ServidorQuiz()
servidor.iniciar_servidor_tcp()
threading.Thread(target=servidor.aceitar_conexoes, daemon=True).start()

def connect_player(name, port):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(2)
    s.connect(('127.0.0.1', 5000))
    s.sendall(json.dumps({'tipo': 'ENTRAR', 'id_jogador': name, 'apelido': name}).encode())
    print('enviei entrar', name)
    return s

s1 = connect_player('player-1', 5002)
s2 = connect_player('player-2', 5003)

time.sleep(0.5)
for idx, sock in enumerate((s1, s2), 1):
    try:
        msg = sock.recv(4096)
        print('msg inicial', idx, msg.decode())
    except Exception as e:
        print('erro inicial', idx, type(e).__name__, e)

s1.sendall(json.dumps({'tipo': 'RESPOSTA', 'id_jogador': 'player-1', 'rodada_id': 1, 'resposta': 'UDP'}).encode())
s2.sendall(json.dumps({'tipo': 'RESPOSTA', 'id_jogador': 'player-2', 'rodada_id': 1, 'resposta': 'ICMP'}).encode())
print('respostas enviadas')

time.sleep(1.0)
for idx, sock in enumerate((s1, s2), 1):
    try:
        data = sock.recv(4096)
        print('msg apos resposta', idx, data.decode())
    except Exception as e:
        print('erro apos resposta', idx, type(e).__name__, e)

for sock in (s1, s2):
    sock.close()
servidor.fechar_servidor()
print('fim')
