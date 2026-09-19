import json
import socket
from typing import Dict

from src.common.game_logic import resolverResultadoRodada
from src.common.protocol import TipoMensagem, criar_mensagem, codificar_mensagem


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
        self.ultimo_ping = None
        self._servidor_ativo = False

    def registrar_jogador(self, identificador_jogador: str, socket_jogador: socket.socket):
        self.jogadores_conectados[identificador_jogador] = socket_jogador

    def iniciar_servidor_tcp(self):
        self._servidor_ativo = True
        self.socket_tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket_tcp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket_tcp.bind((self.host, self.porta_tcp))
        self.socket_tcp.listen()
        self.socket_tcp.settimeout(0.2)
        print(f"Servidor TCP ouvindo em {self.host}:{self.porta_tcp}")

    def iniciar_servidor_udp(self):
        self._servidor_ativo = True
        self.socket_udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket_udp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket_udp.bind((self.host, self.porta_udp))
        self.socket_udp.settimeout(0.2)
        print(f"Servidor UDP ouvindo em {self.host}:{self.porta_udp}")

    def aceitar_conexoes(self):
        while self._servidor_ativo and len(self.jogadores_conectados) < 2:
            try:
                conexao, endereco = self.socket_tcp.accept()
            except socket.timeout:
                continue
            except OSError:
                break

            identificador_jogador = f"player-{len(self.jogadores_conectados) + 1}"
            self.registrar_jogador(identificador_jogador, conexao)
            print(f"Cliente conectado: {identificador_jogador} em {endereco}")

    def enviar_mensagem(self, socket_cliente: socket.socket, tipo_mensagem: TipoMensagem, dados: dict):
        mensagem = criar_mensagem(tipo_mensagem, dados)
        socket_cliente.sendall(codificar_mensagem(mensagem))

    def receber_mensagem(self, identificador_jogador: str):
        socket_jogador = self.jogadores_conectados[identificador_jogador]
        dados = socket_jogador.recv(4096)
        if not dados:
            return None
        return __import__("json").loads(dados.decode("utf-8"))

    def transmitir(self, tipo_mensagem: TipoMensagem, dados: dict):
        for cliente in self.jogadores_conectados.values():
            self.enviar_mensagem(cliente, tipo_mensagem, dados)

    def lidar_com_pergunta(self, pergunta: dict):
        self.transmitir(TipoMensagem.PERGUNTA, pergunta)

    def atualizar_barra(self, direcao: int):
        self.estado_jogo["posicao_barra"] += direcao
        self.transmitir(TipoMensagem.ATUALIZAR_BARRA, {"posicao": self.estado_jogo["posicao_barra"]})

    def processar_resposta(
        self,
        jogador_a: str,
        jogador_b: str,
        resposta_a: str,
        resposta_b: str,
        resposta_correta: str = "TCP",
    ):
        resultado = resolverResultadoRodada(
            jogador_a=jogador_a,
            jogador_b=jogador_b,
            resposta_a=resposta_a,
            resposta_b=resposta_b,
            resposta_correta=resposta_correta,
        )

        if resultado["vencedor"] == "empate":
            return resultado

        if resultado["vencedor"] == jogador_a:
            self.estado_jogo["posicao_barra"] += resultado["delta_barra"] * resultado["direcao_barra"]
        elif resultado["vencedor"] == jogador_b:
            self.estado_jogo["posicao_barra"] += resultado["delta_barra"] * resultado["direcao_barra"]

        return resultado

    def escutar_ping_udp(self):
        while self._servidor_ativo:
            try:
                dados, endereco = self.socket_udp.recvfrom(4096)
            except socket.timeout:
                continue
            except OSError:
                break

            if not dados:
                continue

            mensagem = json.loads(dados.decode("utf-8"))
            self.ultimo_ping = mensagem
            resposta = criar_mensagem(TipoMensagem.PONG, {"id_jogador": mensagem.get("id_jogador", "cliente")})
            self.socket_udp.sendto(codificar_mensagem(resposta), endereco)

    def fechar_servidor(self):
        self._servidor_ativo = False
        for socket_jogador in self.jogadores_conectados.values():
            try:
                socket_jogador.close()
            except OSError:
                pass
        self.jogadores_conectados.clear()

        for atributo in ("socket_tcp", "socket_udp"):
            socket_servidor = getattr(self, atributo, None)
            if socket_servidor is not None:
                try:
                    socket_servidor.close()
                except OSError:
                    pass

    def finalizar_rodada(self, vencedor: str | None = None):
        self.transmitir(TipoMensagem.FIM_RODADA, {"vencedor": vencedor, "rodada": self.estado_jogo["rodada"]})

    def finalizar_jogo(self, vencedor: str):
        self.transmitir(TipoMensagem.FIM_JOGO, {"vencedor": vencedor})


QuizServer = ServidorQuiz
