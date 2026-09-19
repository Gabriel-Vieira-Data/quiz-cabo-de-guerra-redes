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
        self.fila_espera: list[str] = []
        self.salas: dict[str, dict] = {}
        self.partidas_ativas: dict[str, dict] = {}
        self.estado_jogo = {
            "posicao_barra": 0,
            "rodada": 1,
            "maximo_rodadas": 10,
            "pontuacao": {"player-1": 0, "player-2": 0},
            "vencedor": None,
        }
        self.ultimo_ping = None
        self._servidor_ativo = False

    def registrar_jogador(self, identificador_jogador: str, socket_jogador: socket.socket):
        self.jogadores_conectados[identificador_jogador] = socket_jogador
        if identificador_jogador not in self.estado_jogo["pontuacao"]:
            self.estado_jogo["pontuacao"][identificador_jogador] = 0

        self.adicionar_jogador_espera(identificador_jogador)
        return self.criar_sala_para_espera()

    def adicionar_jogador_espera(self, id_jogador: str):
        if id_jogador not in self.fila_espera:
            self.fila_espera.append(id_jogador)

    def criar_sala(self, codigo_sala: str):
        jogadores_da_sala = [jogador for jogador in self.jogadores_conectados if jogador in {"player-1", "player-2"}]
        self.salas[codigo_sala] = {
            "codigo": codigo_sala,
            "jogadores": jogadores_da_sala,
            "estado": "esperando",
        }
        return self.salas[codigo_sala]

    def criar_sala_para_espera(self):
        if len(self.fila_espera) < 2:
            return None

        jogadores = self.fila_espera[:2]
        codigo_sala = f"sala-{len(self.salas) + 1}"
        self.fila_espera = self.fila_espera[2:]
        self.salas[codigo_sala] = {
            "codigo": codigo_sala,
            "jogadores": jogadores,
            "estado": "esperando",
        }
        return self.salas[codigo_sala]

    def iniciar_partida_em_sala(self, codigo_sala: str):
        sala = self.salas.get(codigo_sala)
        if not sala:
            raise ValueError(f"Sala {codigo_sala} não existe.")

        jogadores = sala["jogadores"]
        if len(jogadores) < 2:
            raise ValueError(f"Sala {codigo_sala} precisa de 2 jogadores para iniciar.")

        partida = {
            "codigo": codigo_sala,
            "rodada": 1,
            "estado": "em_andamento",
            "jogadores": jogadores,
        }
        self.partidas_ativas[codigo_sala] = partida
        sala["estado"] = "em_andamento"
        return partida

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

    def iniciar_partida(self):
        self.estado_jogo["rodada"] = 1
        self.estado_jogo["posicao_barra"] = 0
        self.estado_jogo["vencedor"] = None
        for jogador in self.jogadores_conectados:
            self.estado_jogo["pontuacao"].setdefault(jogador, 0)
        return {
            "rodada": self.estado_jogo["rodada"],
            "maximo_rodadas": self.estado_jogo["maximo_rodadas"],
            "pontuacao": self.estado_jogo["pontuacao"],
        }

    def registrar_pontuacao(self, jogador: str):
        if jogador not in self.estado_jogo["pontuacao"]:
            self.estado_jogo["pontuacao"][jogador] = 0

        self.estado_jogo["pontuacao"][jogador] += 1
        if self.estado_jogo["pontuacao"][jogador] >= 2:
            self.estado_jogo["vencedor"] = jogador

    def avancar_rodada(self):
        if self.estado_jogo["vencedor"] is not None:
            return False

        if self.estado_jogo["rodada"] < self.estado_jogo["maximo_rodadas"]:
            self.estado_jogo["rodada"] += 1
            self.estado_jogo["posicao_barra"] = 0
            return True

        return False

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

        vencedor_rodada = resultado["vencedor"]
        if vencedor_rodada in self.estado_jogo["pontuacao"]:
            self.estado_jogo["pontuacao"][vencedor_rodada] += 1
            if self.estado_jogo["pontuacao"][vencedor_rodada] >= 2:
                self.estado_jogo["vencedor"] = vencedor_rodada

        if vencedor_rodada == jogador_a:
            self.estado_jogo["posicao_barra"] += resultado["delta_barra"] * resultado["direcao_barra"]
        elif vencedor_rodada == jogador_b:
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
