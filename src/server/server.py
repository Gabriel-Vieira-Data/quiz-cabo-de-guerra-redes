import json
import re
import socket
import threading
import time
from typing import Dict

from src.common.banco_perguntas import BancoPerguntas
from src.common.game_logic import resolverResultadoRodada
from src.common.protocol import TipoMensagem, codificar_mensagem, criar_mensagem, decodificar_mensagem


class ServidorQuiz:
    def __init__(self, host: str = "0.0.0.0", porta_tcp: int = 5000, porta_udp: int = 5001):
        self.host = host
        self.porta_tcp = porta_tcp
        self.porta_udp = porta_udp
        self._lock = threading.RLock()
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

    def _gerar_id_jogador_disponivel(self, identificador_jogador: str | None):
        base = str(identificador_jogador).strip() if identificador_jogador else "player"
        if not base:
            base = "player"

        if base not in self.jogadores_conectados and base not in self.fila_espera:
            return base

        match = re.fullmatch(r"(.+?)-?(\d+)?", base)
        nome_base = match.group(1) if match else base
        numero_inicial = int(match.group(2)) if match and match.group(2) else 1

        for numero in range(numero_inicial, numero_inicial + 1000):
            candidato = f"{nome_base}-{numero}"
            if candidato not in self.jogadores_conectados and candidato not in self.fila_espera:
                return candidato

        return f"{nome_base}-{int(time.time() * 1000)}"

    def registrar_jogador(self, identificador_jogador: str, socket_jogador: socket.socket):
        with self._lock:
            identificador_jogador = self._gerar_id_jogador_disponivel(identificador_jogador)
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
        with self._lock:
            if not mensagem:
                return None

            tipo_mensagem = str(mensagem.get("tipo", "")).upper()

            if tipo_mensagem == TipoMensagem.ENTRAR.value:
                id_jogador = mensagem.get("id_jogador")
                apelido = mensagem.get("apelido")
                if not id_jogador:
                    return None

                id_jogador = self._gerar_id_jogador_disponivel(id_jogador)
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

    def _resetar_salas_ativas(self):
        for codigo_sala in list(self.salas.keys()):
            if codigo_sala != "sala-1":
                self.salas.pop(codigo_sala, None)
                self.partidas_ativas.pop(codigo_sala, None)
                self.perguntas_rodada.pop(codigo_sala, None)
                self.rodadas_por_sala.pop(codigo_sala, None)
                self.tempo_resposta_por_sala.pop(codigo_sala, None)
                self.respostas_por_sala.pop(codigo_sala, None)

    def adicionar_jogador_espera(self, id_jogador: str):
        with self._lock:
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
        with self._lock:
            if len(self.fila_espera) < 2:
                return None

            if self.salas:
                for codigo_sala in list(self.salas.keys()):
                    sala_atual = self.salas.pop(codigo_sala, None)
                    if sala_atual is not None:
                        for jogador in sala_atual.get("jogadores", []):
                            self.jogadores_conectados.pop(jogador, None)
                        self.partidas_ativas.pop(codigo_sala, None)
                        self.perguntas_rodada.pop(codigo_sala, None)
                        self.rodadas_por_sala.pop(codigo_sala, None)
                        self.tempo_resposta_por_sala.pop(codigo_sala, None)
                        self.respostas_por_sala.pop(codigo_sala, None)

            jogadores = self.fila_espera[:2]
            codigo_sala = "sala-1"
            self.fila_espera = self.fila_espera[2:]
            self.salas[codigo_sala] = {
                "codigo": codigo_sala,
                "jogadores": jogadores,
                "estado": "esperando",
            }
            return self.salas[codigo_sala]

    def iniciar_partida_em_sala(self, codigo_sala: str):
        with self._lock:
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
                "respostas": {},
            }
            self.partidas_ativas[codigo_sala] = partida
            sala["estado"] = "em_andamento"
            sala.setdefault("rodada_atual", 1)
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

    def _processar_buffer_cliente(self, buffer: bytes):
        if not buffer:
            return [], b""

        texto = buffer.lstrip()
        if texto.startswith(b"{"):
            try:
                mensagem = decodificar_mensagem(texto)
                return [mensagem], b""
            except Exception:
                return [], buffer

        if len(buffer) >= 4:
            try:
                tamanho = int.from_bytes(buffer[:4], byteorder="big", signed=False)
            except ValueError:
                tamanho = 0
            if tamanho > 0 and len(buffer) >= 4 + tamanho:
                payload = buffer[4:4 + tamanho]
                resto = buffer[4 + tamanho:]
                try:
                    return [decodificar_mensagem(payload)], resto
                except Exception:
                    pass

        return [], buffer

    def processar_mensagens_de_conexao(self, conexao: socket.socket):
        buffer = b""
        while self._servidor_ativo:
            try:
                dados = conexao.recv(4096)
            except socket.timeout:
                continue
            except OSError:
                break

            if not dados:
                break

            buffer += dados
            while True:
                mensagens, buffer = self._processar_buffer_cliente(buffer)
                if not mensagens:
                    break
                for mensagem in mensagens:
                    if not mensagem:
                        continue

                    tipo = str(mensagem.get("tipo", "")).upper()
                    identificador_jogador = mensagem.get("id_jogador")
                    if tipo == TipoMensagem.ENTRAR.value:
                        if not identificador_jogador:
                            identificador_jogador = f"player-{len(self.jogadores_conectados) + 1}"
                        self.jogadores_conectados[identificador_jogador] = conexao
                        print(f"Cliente conectado: {identificador_jogador}")

                    self.processar_mensagem(mensagem, conexao)

        try:
            if hasattr(conexao, "close"):
                conexao.close()
        except OSError:
            pass

    def escutar_cliente(self, conexao: socket.socket):
        self.processar_mensagens_de_conexao(conexao)

    def aceitar_conexoes(self):
        while self._servidor_ativo:
            try:
                conexao, endereco = self.socket_tcp.accept()
            except socket.timeout:
                continue
            except OSError:
                break

            thread_cliente = threading.Thread(target=self.escutar_cliente, args=(conexao,), daemon=True)
            thread_cliente.start()

    def _enviar_mensagem_socket(self, socket_cliente, tipo_mensagem: TipoMensagem, dados: dict):
        if socket_cliente is None or not hasattr(socket_cliente, "sendall"):
            return False

        mensagem = criar_mensagem(tipo_mensagem, dados)
        try:
            if isinstance(socket_cliente, socket.socket):
                payload = codificar_mensagem(mensagem)
            else:
                payload = json.dumps(mensagem, ensure_ascii=False).encode("utf-8")
            socket_cliente.sendall(payload)
            return True
        except (AttributeError, OSError, TypeError, ValueError):
            return False

    def enviar_mensagem(self, socket_cliente: socket.socket, tipo_mensagem: TipoMensagem, dados: dict):
        return self._enviar_mensagem_socket(socket_cliente, tipo_mensagem, dados)

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

        if len(dados) >= 4:
            tamanho = int.from_bytes(dados[:4], byteorder="big", signed=False)
            if len(dados) >= 4 + tamanho:
                dados = dados[4:4 + tamanho]

        return __import__("json").loads(dados.decode("utf-8"))

    def transmitir(self, tipo_mensagem: TipoMensagem, dados: dict):
        for cliente in list(self.jogadores_conectados.values()):
            self.enviar_mensagem(cliente, tipo_mensagem, dados)

    def transmitir_para_sala(self, codigo_sala: str, tipo_mensagem: TipoMensagem, dados: dict):
        sala = self.salas.get(codigo_sala)
        if not sala:
            return
        for id_jogador in sala.get("jogadores", []):
            cliente = self.jogadores_conectados.get(id_jogador)
            if cliente is not None:
                self.enviar_mensagem(cliente, tipo_mensagem, dados)

    def remover_jogador(self, id_jogador: str):
        with self._lock:
            socket_jogador = self.jogadores_conectados.pop(id_jogador, None)
            if socket_jogador is not None:
                try:
                    socket_jogador.close()
                except OSError:
                    pass

            for codigo_sala, sala in list(self.salas.items()):
                jogadores = sala.get("jogadores", [])
                if id_jogador in jogadores:
                    sala["jogadores"] = [jogador for jogador in jogadores if jogador != id_jogador]
                    self.transmitir(TipoMensagem.DESCONEXAO, {"id_jogador": id_jogador, "codigo_sala": codigo_sala})
                    if not sala["jogadores"]:
                        self.salas.pop(codigo_sala, None)
                        self.partidas_ativas.pop(codigo_sala, None)
                        self.perguntas_rodada.pop(codigo_sala, None)
                        self.rodadas_por_sala.pop(codigo_sala, None)
                        self.tempo_resposta_por_sala.pop(codigo_sala, None)
                        self.respostas_por_sala.pop(codigo_sala, None)
                    break

    def selecionar_pergunta_para_sala(self, codigo_sala: str):
        with self._lock:
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

        for id_jogador in sala["jogadores"]:
            socket_jogador = self.jogadores_conectados.get(id_jogador)
            if socket_jogador is not None:
                self._enviar_mensagem_socket(socket_jogador, TipoMensagem.PERGUNTA, pergunta)

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
        with self._lock:
            sala = self.salas.get(codigo_sala)
            if not sala:
                raise ValueError(f"Sala {codigo_sala} não existe.")

            partida = self.partidas_ativas.get(codigo_sala, {})
            numero_rodada = int(partida.get("rodada", rodada_id or 1))
            estado_rodada = self.rodadas_por_sala.setdefault(
                codigo_sala,
                {"inicio": time.time(), "respostas": {}, "vencedor": None, "concluida": False, "rodada_id": numero_rodada},
            )
            estado_rodada["rodada_id"] = numero_rodada
            if estado_rodada["concluida"]:
                return None

            if id_jogador in estado_rodada["respostas"]:
                return None

            if time.time() - estado_rodada["inicio"] > self.tempo_limite_rodada:
                estado_rodada["concluida"] = True
                self.finalizar_rodada(codigo_sala=codigo_sala, vencedor=None)
                return {"vencedor": "nenhum", "delta_barra": 0, "direcao_barra": 0}

            resposta_normalizada = str(resposta).strip().upper()
            pergunta = self.perguntas_rodada.get(codigo_sala, {})
            resposta_correta = str(pergunta.get("resposta_correta", "")).strip().upper()

            instante_resposta = time.time()
            estado_rodada["respostas"][id_jogador] = {
                "resposta": resposta_normalizada,
                "tempo": instante_resposta,
            }
            self.tempo_resposta_por_sala.setdefault(codigo_sala, {}).setdefault(str(rodada_id), {})
            self.tempo_resposta_por_sala[codigo_sala][str(rodada_id)][id_jogador] = instante_resposta

            if len(estado_rodada["respostas"]) < len(sala["jogadores"]):
                return None

            estado_rodada["concluida"] = True
            respostas_certas = [
                jogador for jogador, dados in estado_rodada["respostas"].items()
                if str(dados.get("resposta", "")).strip().upper() == resposta_correta
            ]

            if respostas_certas:
                vencedor = min(respostas_certas, key=lambda jogador: estado_rodada["respostas"][jogador]["tempo"])
                estado_rodada["vencedor"] = vencedor
                self.estado_jogo["pontuacao"][vencedor] = self.estado_jogo["pontuacao"].get(vencedor, 0) + 1
                resultado = {"vencedor": vencedor, "delta_barra": 1, "direcao_barra": 1}
                self.finalizar_rodada(codigo_sala=codigo_sala, vencedor=vencedor)
                return resultado

            estado_rodada["vencedor"] = None
            resultado = {"vencedor": "nenhum", "delta_barra": 0, "direcao_barra": 0}
            self.finalizar_rodada(codigo_sala=codigo_sala, vencedor=None)
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

    def avancar_para_proxima_pergunta(self, codigo_sala: str):
        with self._lock:
            sala = self.salas.get(codigo_sala)
            if not sala:
                return None

            partida = self.partidas_ativas.get(codigo_sala)
            rodada_atual = int((partida or {}).get("rodada", self.estado_jogo.get("rodada", 1)))
            if rodada_atual >= self.estado_jogo["maximo_rodadas"]:
                return None

            proxima_rodada = rodada_atual + 1
            if partida is not None:
                partida["rodada"] = proxima_rodada
                partida["respostas"] = {}
            self.estado_jogo["rodada"] = proxima_rodada
            sala["rodada_atual"] = proxima_rodada
            self.rodadas_por_sala.setdefault(codigo_sala, {})
            self.rodadas_por_sala[codigo_sala] = {
                "inicio": time.time(),
                "respostas": {},
                "vencedor": None,
                "concluida": False,
                "rodada_id": proxima_rodada,
            }

            pergunta = self.selecionar_pergunta_para_sala(codigo_sala)
            payload = {
                "rodada_id": proxima_rodada,
                "pergunta": pergunta["pergunta"],
                "opcoes": pergunta["opcoes"],
                "resposta_correta": pergunta["resposta_correta"],
                "tempo_limite": self.tempo_limite_rodada,
            }
            self.enviar_pergunta_para_sala(codigo_sala, payload)
            return pergunta

    def _avancar_rodada_com_retorno(self, codigo_sala: str):
        try:
            self.avancar_para_proxima_pergunta(codigo_sala)
        except Exception:
            return None
        return codigo_sala

    def finalizar_rodada(self, codigo_sala: str | None = None, vencedor: str | None = None):
        if codigo_sala is None:
            return

        with self._lock:
            partida = self.partidas_ativas.get(codigo_sala, {})
            rodada_corrente = int(partida.get("rodada", self.estado_jogo.get("rodada", 1)))
            self.transmitir_para_sala(
                codigo_sala,
                TipoMensagem.FIM_RODADA,
                {"vencedor": vencedor, "rodada": rodada_corrente, "codigo_sala": codigo_sala},
            )

        timer = threading.Timer(0.2, self._avancar_rodada_com_retorno, args=(codigo_sala,))
        timer.daemon = True
        timer.start()

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
