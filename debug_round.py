import json
from src.server.server import ServidorQuiz

class FakeSocket:
    def __init__(self):
        self.mensagens=[]
    def sendall(self, dados):
        try:
            payload = json.loads(dados[4:].decode('utf-8')) if len(dados) >= 4 else json.loads(dados.decode('utf-8'))
        except Exception:
            payload = {'raw': dados[:40]}
        self.mensagens.append(payload)
    def close(self):
        pass

s = ServidorQuiz()
q1=FakeSocket(); q2=FakeSocket()
s.registrar_jogador('player-1', q1)
s.registrar_jogador('player-2', q2)
print('after register', s.salas, s.partidas_ativas)
print('msg counts', len(q1.mensagens), len(q2.mensagens))
print('last j1', q1.mensagens[-1])
print('last j2', q2.mensagens[-1])
print('res1', s.registrar_resposta_jogador('sala-1', 1, 'player-1', 'TCP'))
print('res2', s.registrar_resposta_jogador('sala-1', 1, 'player-2', 'UDP'))
print('after answers', s.rodadas_por_sala)
print('counts after', len(q1.mensagens), len(q2.mensagens))
for i,m in enumerate(q1.mensagens):
    print('Q1', i, m.get('tipo'), m.get('rodada_id'))
for i,m in enumerate(q2.mensagens):
    print('Q2', i, m.get('tipo'), m.get('rodada_id'))
