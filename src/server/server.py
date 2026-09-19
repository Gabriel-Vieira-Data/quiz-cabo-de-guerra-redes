import json
import socket
import time
from typing import Dict

from src.common.banco_perguntas import BancoPerguntas
from src.common.game_logic import resolverResultadoRodada
from src.common.protocol import TipoMensagem, criar_mensagem, codificar_mensagem


class ServidorQuiz:
    def __init__(self, host: str = "0.0.0.0", porta_tcp: int = 5000, porta_udp: int = 5001):
        self.host = host
        self.porta_tcp = porta_tcp
        self.porta_udp = porta_udp
        self.jogadores_conectados: Dict[str, socket.socket] = {}
        self.fila_espera: list[str] = []
        self.salas: dict[str, dict] = {}
        self.partidas_ativas: dict[str, dict] = {}
        self.respostas_por_sala: dict[str, dict[str, dict[str, str]]] = {}
        self.tempo_resposta_por_sala: dict[str, dict[str, float]] = {}
        self.rodadas_por_sala: dict[str, dict] = {}
        self.banco_perguntas = BancoPerguntas()
        self.perguntas_rodada: dict[str, dict] = {}
        self.tempo_limite_rodada = 30
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
        sala = self.criar_sala_para_espera()
        if sala is not None:
            self.respostas_por_sala.setdefault(sala["codigo"], {})
            self.iniciar_partida_em_sala(sala["codigo"])
            pergunta = self.selecionar_pergunta_para_sala(sala["codigo"])
            self.enviar_pergunta_para_sala(
                sala["codigo"],
                {
                    "rodada_id": 1,
                    "pergunta": pergunta["pergunta"],
                    "opcoes": pergunta["opcoes"],
                    "resposta_correta": pergunta["resposta_correta"],
                    "tempo_limite": self.tempo_limite_rodada,
                },
            )
        return sala

    def processar_mensagem(self, mensagem: dict, socket_remetente: socket.socket | None = None):
        if not mensagem:
            return None

        tipo_mensagem = str(mensagem.get("tipo", "")).upper()

        if tipo_mensagem == TipoMensagem.ENTRAR.value:
            id_jogador = mensagem.get("id_jogador")
            apelido = mensagem.get("apelido")
            if not id_jogador:
                return None

            if socket_remetente is not None:
                self.jogadores_conectados[id_jogador] = socket_remetente
                if id_jogador not in self.estado_jogo["pontuacao"]:
                    self.estado_jogo["pontuacao"][id_jogador] = 0

            self.adicionar_jogador_espera(id_jogador)
            sala = self.criar_sala_para_espera()
            if sala is not None:
                self.respostas_por_sala.setdefault(sala["codigo"], {})
                self.iniciar_partida_em_sala(sala["codigo"])
                pergunta = self.selecionar_pergunta_para_sala(sala["codigo"])
                self.enviar_pergunta_para_sala(
                    sala["codigo"],
                    {
                        "rodada_id": 1,
                        "pergunta": pergunta["pergunta"],
                        "opcoes": pergunta["opcoes"],
                        "resposta_correta": pergunta["resposta_correta"],
                        "tempo_limite": self.tempo_limite_rodada,
                    },
                )
            return {
                "tipo": TipoMensagem.ENTRAR.value,
                "id_jogador": id_jogador,
                "apelido": apelido,
                "sala": sala,
            }

        if tipo_mensagem == TipoMensagem.RESPOSTA.value:
            id_jogador = mensagem.get("id_jogador")
            rodada_id = mensagem.get("rodada_id", 1)
            resposta = mensagem.get("resposta", "")

            if not id_jogador:
                return None

            codigo_sala = self._obter_codigo_sala_do_jogador(id_jogador)
            if codigo_sala is None:
                return None

            return self.registrar_resposta_jogador(codigo_sala, rodada_id, id_jogador, resposta)

        return mensagem

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
        while self._servidor_ativo:
            try:
                conexao, endereco = self.socket_tcp.accept()
            except socket.timeout:
                continue
            except OSError:
                break

            try:
                dados = conexao.recv(4096)
            except OSError:
                continue

            if not dados:
                conexao.close()
                continue

            mensagem = json.loads(dados.decode("utf-8"))
            tipo = str(mensagem.get("tipo", "")).upper()
            identificador_jogador = mensagem.get("id_jogador")
            if not identificador_jogador:
                identificador_jogador = f"player-{len(self.jogadores_conectados) + 1}"

            self.processar_mensagem(mensagem, conexao)
            print(f"Cliente conectado: {identificador_jogador} em {endereco}")

            if tipo == TipoMensagem.ENTRAR.value:
                self.jogadores_conectados[identificador_jogador] = conexao

    def enviar_mensagem(self, socket_cliente: socket.socket, tipo_mensagem: TipoMensagem, dados: dict):
        mensagem = criar_mensagem(tipo_mensagem, dados)
        socket_cliente.sendall(codificar_mensagem(mensagem))

    def _obter_codigo_sala_do_jogador(self, id_jogador: str):
        for codigo_sala, sala in self.salas.items():
            if id_jogador in sala.get("jogadores", []):
                return codigo_sala
        return None

    def receber_mensagem(self, identificador_jogador: str):
        socket_jogador = self.jogadores_conectados[identificador_jogador]
        dados = socket_jogador.recv(4096)
        if not dados:
            return None
        return __import__("json").loads(dados.decode("utf-8"))

    def transmitir(self, tipo_mensagem: TipoMensagem, dados: dict):
        for cliente in self.jogadores_conectados.values():
            self.enviar_mensagem(cliente, tipo_mensagem, dados)

    def selecionar_pergunta_para_sala(self, codigo_sala: str):
        sala = self.salas.get(codigo_sala)
        if not sala:
            raise ValueError(f"Sala {codigo_sala} não existe.")

        perguntas = self.banco_perguntas.obter_perguntas()
        if not perguntas:
            raise ValueError("Banco de perguntas vazio.")

        pergunta = __import__("random").choice(perguntas)
        self.perguntas_rodada[codigo_sala] = pergunta
        self.tempo_resposta_por_sala.setdefault(codigo_sala, {})
        self.respostas_por_sala.setdefault(codigo_sala, {})
        self.tempo_resposta_por_sala[codigo_sala].clear()
        self.respostas_por_sala[codigo_sala].clear()
        self.rodadas_por_sala[codigo_sala] = {
            "inicio": time.time(),
            "respostas": {},
            "vencedor": None,
            "concluida": False,
        }
        self.tempo_rodada_por_sala = getattr(self, "tempo_rodada_por_sala", {})
        self.tempo_rodada_por_sala[codigo_sala] = time.time()
        return pergunta

    def enviar_pergunta_para_sala(self, codigo_sala: str, pergunta: dict):
        sala = self.salas.get(codigo_sala)
        if not sala:
            raise ValueError(f"Sala {codigo_sala} não existe.")

        mensagem = criar_mensagem(TipoMensagem.PERGUNTA, pergunta)
        for id_jogador in sala["jogadores"]:
            socket_jogador = self.jogadores_conectados.get(id_jogador)
            if socket_jogador is not None:
                socket_jogador.sendall(codificar_mensagem(mensagem))

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

    def registrar_resposta_jogador(self, codigo_sala: str, rodada_id: int, id_jogador: str, resposta: str):
        sala = self.salas.get(codigo_sala)
        if not sala:
            raise ValueError(f"Sala {codigo_sala} não existe.")

        estado_rodada = self.rodadas_por_sala.setdefault(
            codigo_sala,
            {"inicio": time.time(), "respostas": {}, "vencedor": None, "concluida": False},
        )
        if estado_rodada["concluida"]:
            return None

        if id_jogador in estado_rodada["respostas"]:
            return None

        if time.time() - estado_rodada["inicio"] > self.tempo_limite_rodada:
            estado_rodada["concluida"] = True
            return None

        resposta_normalizada = str(resposta).strip().upper()
        pergunta = self.perguntas_rodada.get(codigo_sala, {})
        resposta_correta = str(pergunta.get("resposta_correta", "")).strip().upper()

        estado_rodada["respostas"][id_jogador] = {
            "resposta": resposta_normalizada,
            "tempo": time.time(),
        }
        self.tempo_resposta_por_sala.setdefault(codigo_sala, {}).setdefault(str(rodada_id), {})
        self.tempo_resposta_por_sala[codigo_sala][str(rodada_id)][id_jogador] = time.time()

        if resposta_normalizada != resposta_correta:
            if len(estado_rodada["respostas"]) >= len(sala["jogadores"]):
                estado_rodada["concluida"] = True
                return {"vencedor": "nenhum", "delta_barra": 0, "direcao_barra": 0}
            return None

        estado_rodada["concluida"] = True
        estado_rodada["vencedor"] = id_jogador
        self.estado_jogo["pontuacao"][id_jogador] = self.estado_jogo["pontuacao"].get(id_jogador, 0) + 1
        resultado = {"vencedor": id_jogador, "delta_barra": 1, "direcao_barra": 1}
        self.finalizar_rodada(vencedor=id_jogador)
        return resultado

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

    def iniciar_loop_principal(self):
        self.iniciar_servidor_tcp()
        self.iniciar_servidor_udp()

        thread_tcp = __import__("threading").Thread(target=self.aceitar_conexoes, daemon=True)
        thread_tcp.start()
        thread_udp = __import__("threading").Thread(target=self.escutar_ping_udp, daemon=True)
        thread_udp.start()

        print(f"Servidor pronto em {self.host}:{self.porta_tcp}")
        while self._servidor_ativo:
            time.sleep(0.2)


QuizServer = ServidorQuiz


if __name__ == "__main__":
    servidor = ServidorQuiz()
    servidor.iniciar_loop_principal()
