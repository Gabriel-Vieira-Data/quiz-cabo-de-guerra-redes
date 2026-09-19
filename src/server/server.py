import socket
from typing import Dict

from src.common.protocol import TipoMensagem, criar_mensagem, decodificar_mensagem, codificar_mensagem


class ServidorQuiz:
    def __init__(self, host: str = "127.0.0.1", porta_tcp: int = 5000, porta_udp: int = 5001):
        self.host = host
        self.porta_tcp = porta_tcp
        self.porta_udp = porta_udp
        self.jogadores_conectados: Dict[str, socket.socket] = {}
        self.estado_jogo = {
            "posicao_barra": 0,
            "rodada": 1,
            "maximo_rodadas": 10,
        }

    def iniciar_servidor_tcp(self):
        self.socket_tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket_tcp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket_tcp.bind((self.host, self.porta_tcp))
        self.socket_tcp.listen()
        print(f"Servidor TCP ouvindo em {self.host}:{self.porta_tcp}")

    def iniciar_servidor_udp(self):
        self.socket_udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket_udp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket_udp.bind((self.host, self.porta_udp))
        print(f"Servidor UDP ouvindo em {self.host}:{self.porta_udp}")

    def aceitar_conexoes(self):
        while len(self.jogadores_conectados) < 2:
            conexao, endereco = self.socket_tcp.accept()
            identificador_jogador = f"player-{len(self.jogadores_conectados) + 1}"
            self.jogadores_conectados[identificador_jogador] = conexao
            print(f"Cliente conectado: {identificador_jogador} em {endereco}")

    def enviar_mensagem(self, socket_cliente: socket.socket, tipo_mensagem: TipoMensagem, dados: dict):
        mensagem = criar_mensagem(tipo_mensagem, dados)
        socket_cliente.sendall(codificar_mensagem(mensagem))

    def transmitir(self, tipo_mensagem: TipoMensagem, dados: dict):
        for cliente in self.jogadores_conectados.values():
            self.enviar_mensagem(cliente, tipo_mensagem, dados)

    def lidar_com_pergunta(self, pergunta: dict):
        self.transmitir(TipoMensagem.PERGUNTA, pergunta)

    def atualizar_barra(self, direcao: int):
        self.estado_jogo["posicao_barra"] += direcao
        self.transmitir(TipoMensagem.ATUALIZAR_BARRA, {"posicao": self.estado_jogo["posicao_barra"]})

    def finalizar_rodada(self, vencedor: str | None = None):
        self.transmitir(TipoMensagem.FIM_RODADA, {"vencedor": vencedor, "rodada": self.estado_jogo["rodada"]})

    def finalizar_jogo(self, vencedor: str):
        self.transmitir(TipoMensagem.FIM_JOGO, {"vencedor": vencedor})


QuizServer = ServidorQuiz
