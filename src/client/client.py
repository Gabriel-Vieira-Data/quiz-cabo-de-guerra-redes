import socket

from src.common.protocol import TipoMensagem, criar_mensagem, decodificar_mensagem, codificar_mensagem


class ClienteQuiz:
    def __init__(self, host: str = "127.0.0.1", porta_tcp: int = 5000, porta_udp: int = 5001):
        self.host = host
        self.porta_tcp = porta_tcp
        self.porta_udp = porta_udp
        self.socket_tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket_udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def conectar(self):
        self.socket_tcp.connect((self.host, self.porta_tcp))
        self.socket_udp.bind(("0.0.0.0", 0))

    def enviar_entrada(self, id_jogador: str, apelido: str):
        mensagem = criar_mensagem(TipoMensagem.ENTRAR, {"id_jogador": id_jogador, "apelido": apelido})
        self.socket_tcp.sendall(codificar_mensagem(mensagem))

    def enviar_resposta(self, id_jogador: str, rodada_id: int, resposta: str):
        mensagem = criar_mensagem(
            TipoMensagem.RESPOSTA,
            {"id_jogador": id_jogador, "rodada_id": rodada_id, "resposta": resposta},
        )
        self.socket_tcp.sendall(codificar_mensagem(mensagem))

    def receber_mensagem(self):
        dados = self.socket_tcp.recv(4096)
        if not dados:
            return None
        return decodificar_mensagem(dados)

    def enviar_ping_udp(self):
        ping = criar_mensagem(TipoMensagem.PING, {"id_jogador": "cliente"})
        self.socket_udp.sendto(codificar_mensagem(ping), (self.host, self.porta_udp))


QuizClient = ClienteQuiz
