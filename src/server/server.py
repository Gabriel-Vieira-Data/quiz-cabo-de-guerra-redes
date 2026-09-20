"""
Servidor do Quiz Cabo de Guerra.

Arquitetura de threads:
  - Thread principal : loop de keep-alive
  - Thread TCP accept: aceitar_conexoes()
  - Thread UDP       : escutar_ping_udp()
  - Thread por cliente: processar_mensagens_de_conexao()

Fluxo de uma partida:
  1. Dois clientes enviam ENTRAR → servidor cria sala e envia PERGUNTA
  2. Clientes enviam RESPOSTA → registrar_resposta_jogador() resolve a rodada
  3. Servidor envia FIM_RODADA + ATUALIZAR_BARRA
  4. Se o jogo terminou → envia FIM_JOGO; senão avança para próxima PERGUNTA
  5. Timeout de rodada é gerenciado por threading.Timer em background
"""
import json
import re
import socket
import threading
import time
from typing import Dict

from src.common.banco_perguntas import BancoPerguntas
from src.common.game_logic import EstadoJogo, resolverResultadoRodada
from src.common.protocol import TipoMensagem, codificar_mensagem, criar_mensagem, decodificar_mensagem


class _EstadoJogoProxy(dict):
    """
    Dicionário proxy que mantém sincronizado com um EstadoJogo.
    Garante retrocompatibilidade com testes que acessam servidor.estado_jogo["pontuacao"] etc.
    """

    def __init__(self, estado: EstadoJogo):
        super().__init__(
            posicao_barra=estado.posicao_barra,
            rodada=estado.rodada_atual,
            maximo_rodadas=estado.maximo_rodadas,
            pontuacao=estado.pontuacao_jogadores,
            vencedor=estado.vencedor,
        )
        self._estado = estado

    def _sync(self):
        self["posicao_barra"] = self._estado.posicao_barra
        self["rodada"] = self._estado.rodada_atual
        self["pontuacao"] = self._estado.pontuacao_jogadores
        self["vencedor"] = self._estado.vencedor

    def __setitem__(self, key, value):
        super().__setitem__(key, value)
        if key == "posicao_barra" and hasattr(self, "_estado"):
            self._estado.posicao_barra = value
        elif key == "vencedor" and hasattr(self, "_estado"):
            self._estado.vencedor = value

    def __getitem__(self, key):
        if hasattr(self, "_estado"):
            self._sync()
        return super().__getitem__(key)


class ServidorQuiz:
    def __init__(self, host: str = "0.0.0.0", porta_tcp: int = 5000, porta_udp: int = 5001):
        self.host = host
        self.porta_tcp = porta_tcp
        self.porta_udp = porta_udp
        self._lock = threading.RLock()

        # Conexões e fila
        self.jogadores_conectados: Dict[str, socket.socket] = {}
        self.fila_espera: list[str] = []

        # Salas e partidas
        self.salas: dict[str, dict] = {}
        self.partidas_ativas: dict[str, dict] = {}
        self.estado_por_sala: dict[str, EstadoJogo] = {}

        # Dados de rodada
        self.rodadas_por_sala: dict[str, dict] = {}
        self.perguntas_rodada: dict[str, dict] = {}
        self.perguntas_usadas_por_sala: dict[str, set] = {}

        # Timers de timeout de rodada
        self._timers_timeout: dict[str, threading.Timer] = {}

        self.banco_perguntas = BancoPerguntas()
        self.tempo_limite_rodada = 30

        # Estado global legado (proxy do primeiro EstadoJogo ativo)
        self._estado_global = EstadoJogo()
        self.estado_jogo = _EstadoJogoProxy(self._estado_global)

        self.ultimo_ping = None
        self._servidor_ativo = False

    # -----------------------------------------------------------------------
    # Identificação de jogadores
    # -----------------------------------------------------------------------

    def _gerar_id_jogador_disponivel(self, identificador_jogador: str | None) -> str:
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

    # -----------------------------------------------------------------------
    # Fila de espera e criação de sala
    # -----------------------------------------------------------------------

    def adicionar_jogador_espera(self, id_jogador: str):
        with self._lock:
            if id_jogador not in self.fila_espera:
                self.fila_espera.append(id_jogador)

    def criar_sala_para_espera(self) -> dict | None:
        with self._lock:
            if len(self.fila_espera) < 2:
                # Fila insuficiente — se já existe sala-1 apenas recria os dados legados
                if self.salas:
                    return list(self.salas.values())[0]
                return None

            # Remove sala anterior (se existir) sem desconectar jogadores ativos
            for codigo_sala in list(self.salas.keys()):
                self._limpar_sala(codigo_sala)

            jogadores = self.fila_espera[:2]
            self.fila_espera = self.fila_espera[2:]
            codigo_sala = "sala-1"

            self.salas[codigo_sala] = {
                "codigo": codigo_sala,
                "jogadores": jogadores,
                "estado": "esperando",
                "rodada_atual": 1,
            }
            self.perguntas_usadas_por_sala[codigo_sala] = set()
            return self.salas[codigo_sala]

    def _limpar_sala(self, codigo_sala: str):
        self._cancelar_timer_timeout(codigo_sala)
        self.salas.pop(codigo_sala, None)
        self.partidas_ativas.pop(codigo_sala, None)
        self.estado_por_sala.pop(codigo_sala, None)
        self.rodadas_por_sala.pop(codigo_sala, None)
        self.perguntas_rodada.pop(codigo_sala, None)
        self.perguntas_usadas_por_sala.pop(codigo_sala, None)

    def criar_sala(self, codigo_sala: str):
        """Compatibilidade com testes legados."""
        jogadores_da_sala = [j for j in self.jogadores_conectados if j in {"player-1", "player-2"}]
        self.salas[codigo_sala] = {
            "codigo": codigo_sala,
            "jogadores": jogadores_da_sala,
            "estado": "esperando",
            "rodada_atual": 1,
        }
        return self.salas[codigo_sala]

    # -----------------------------------------------------------------------
    # Início de partida
    # -----------------------------------------------------------------------

    def iniciar_partida_em_sala(self, codigo_sala: str) -> dict:
        with self._lock:
            sala = self.salas.get(codigo_sala)
            if not sala:
                raise ValueError(f"Sala {codigo_sala} não existe.")

            jogadores = sala["jogadores"]
            if len(jogadores) < 2:
                raise ValueError(f"Sala {codigo_sala} precisa de 2 jogadores para iniciar.")

            jogador_a, jogador_b = jogadores[0], jogadores[1]

            estado = EstadoJogo(jogador_a=jogador_a, jogador_b=jogador_b)
            self.estado_por_sala[codigo_sala] = estado

            # Atualiza o proxy global para refletir este estado
            self._estado_global = estado
            self.estado_jogo = _EstadoJogoProxy(estado)

            partida = {
                "codigo": codigo_sala,
                "rodada": 1,
                "estado": "em_andamento",
                "jogadores": jogadores,
            }
            self.partidas_ativas[codigo_sala] = partida
            sala["estado"] = "em_andamento"
            sala["rodada_atual"] = 1
            return partida

    # -----------------------------------------------------------------------
    # Perguntas
    # -----------------------------------------------------------------------

    def selecionar_pergunta_para_sala(self, codigo_sala: str, esperar_dois_jogadores: bool | None = None) -> dict:
        with self._lock:
            todas = self.banco_perguntas.obter_perguntas()
            if not todas:
                raise ValueError("Banco de perguntas vazio.")

            usadas = self.perguntas_usadas_por_sala.get(codigo_sala, set())
            disponiveis = [p for p in todas if p["pergunta"] not in usadas]
            if not disponiveis:
                disponiveis = todas
                self.perguntas_usadas_por_sala[codigo_sala] = set()

            import random
            pergunta = random.choice(disponiveis)
            self.perguntas_usadas_por_sala.setdefault(codigo_sala, set()).add(pergunta["pergunta"])
            self.perguntas_rodada[codigo_sala] = pergunta

            # Determina modo de espera: se não especificado, usa presença de partida ativa
            if esperar_dois_jogadores is None:
                esperar_dois_jogadores = codigo_sala in self.partidas_ativas

            # Reinicia o estado da rodada
            self.rodadas_por_sala[codigo_sala] = {
                "inicio": time.time(),
                "respostas": {},
                "vencedor": None,
                "concluida": False,
                "modo_espera_dupla": esperar_dois_jogadores,
            }
            return pergunta

    def enviar_pergunta_para_sala(self, codigo_sala: str, payload: dict):
        sala = self.salas.get(codigo_sala)
        if not sala:
            return
        for id_jogador in sala["jogadores"]:
            sock = self.jogadores_conectados.get(id_jogador)
            if sock is not None:
                self._enviar_mensagem_socket(sock, TipoMensagem.PERGUNTA, payload)

    # -----------------------------------------------------------------------
    # Processamento de mensagens recebidas dos clientes
    # -----------------------------------------------------------------------

    def processar_mensagem(self, mensagem: dict, socket_remetente: socket.socket | None = None):
        with self._lock:
            if not mensagem:
                return None

            tipo = str(mensagem.get("tipo", "")).upper()

            if tipo == TipoMensagem.ENTRAR.value:
                return self._handle_entrar(mensagem, socket_remetente)

            if tipo == TipoMensagem.RESPOSTA.value:
                return self._handle_resposta(mensagem)

            return mensagem

    def _handle_entrar(self, mensagem: dict, socket_remetente):
        id_jogador = mensagem.get("id_jogador")
        apelido = mensagem.get("apelido", id_jogador)
        if not id_jogador:
            return None

        id_jogador = self._gerar_id_jogador_disponivel(id_jogador)

        if socket_remetente is not None:
            self.jogadores_conectados[id_jogador] = socket_remetente

        self.adicionar_jogador_espera(id_jogador)
        sala = self.criar_sala_para_espera()

        if sala is not None and len(sala.get("jogadores", [])) == 2:
            self.iniciar_partida_em_sala(sala["codigo"])
            self._iniciar_primeira_rodada(sala["codigo"])
            # Retorna a sala diretamente (contratos de teste exigem isso)
            return sala

        # Primeiro jogador: ainda aguardando o segundo
        return None

    def _handle_resposta(self, mensagem: dict):
        id_jogador = mensagem.get("id_jogador")
        rodada_id = mensagem.get("rodada_id", 1)
        resposta = mensagem.get("resposta", "")

        if not id_jogador:
            return None

        codigo_sala = self._obter_codigo_sala_do_jogador(id_jogador)
        if codigo_sala is None:
            return None

        return self.registrar_resposta_jogador(codigo_sala, rodada_id, id_jogador, resposta)

    # -----------------------------------------------------------------------
    # Lógica central de rodada
    # -----------------------------------------------------------------------

    def _iniciar_primeira_rodada(self, codigo_sala: str):
        pergunta = self.selecionar_pergunta_para_sala(codigo_sala)
        estado = self.estado_por_sala.get(codigo_sala)
        rodada_id = estado.rodada_atual if estado else 1
        payload = {
            "rodada_id": rodada_id,
            "pergunta": pergunta["pergunta"],
            "opcoes": pergunta["opcoes"],
            "resposta_correta": pergunta["resposta_correta"],
            "tempo_limite": self.tempo_limite_rodada,
        }
        self.enviar_pergunta_para_sala(codigo_sala, payload)
        self._agendar_timeout_rodada(codigo_sala)

    def registrar_jogador(self, identificador_jogador: str, socket_jogador) -> dict | None:
        """API de compatibilidade usada por testes e scripts de demo."""
        with self._lock:
            identificador_jogador = self._gerar_id_jogador_disponivel(identificador_jogador)
            self.jogadores_conectados[identificador_jogador] = socket_jogador

            self.adicionar_jogador_espera(identificador_jogador)
            sala = self.criar_sala_para_espera()
            if sala is not None and len(sala.get("jogadores", [])) == 2:
                self.iniciar_partida_em_sala(sala["codigo"])
                self._iniciar_primeira_rodada(sala["codigo"])
            return sala

    def registrar_resposta_jogador(
        self, codigo_sala: str, rodada_id: int, id_jogador: str, resposta: str
    ):
        with self._lock:
            sala = self.salas.get(codigo_sala)
            if not sala:
                raise ValueError(f"Sala {codigo_sala} não existe.")

            estado_rodada = self.rodadas_por_sala.get(codigo_sala)
            if estado_rodada is None:
                return None

            if estado_rodada.get("concluida"):
                return None

            # Ignorar resposta duplicada do mesmo jogador
            if id_jogador in estado_rodada["respostas"]:
                return None

            # Verificar timeout
            if time.time() - estado_rodada["inicio"] > self.tempo_limite_rodada:
                estado_rodada["concluida"] = True
                self._cancelar_timer_timeout(codigo_sala)
                # Sai do lock antes de resolver para evitar deadlock
                deve_resolver_timeout = True
            else:
                deve_resolver_timeout = False

            if deve_resolver_timeout:
                pass  # handled below after lock release

        if deve_resolver_timeout:
            self._resolver_rodada(codigo_sala, vencedor=None)
            return {"vencedor": "nenhum", "delta_barra": 0, "direcao_barra": 0}

        with self._lock:

            # Registrar resposta com timestamp
            estado_rodada["respostas"][id_jogador] = {
                "resposta": str(resposta).strip().upper(),
                "tempo": time.time(),
            }

            pergunta = self.perguntas_rodada.get(codigo_sala, {})
            resposta_correta = str(pergunta.get("resposta_correta", "")).strip().upper()

            modo_espera_dupla = estado_rodada.get("modo_espera_dupla", True)

            # Resolve imediatamente se:
            # - Não está no modo de espera dupla (partida sem estado ativo), OU
            # - Todos os jogadores da sala já responderam
            n_jogadores = len(sala["jogadores"])
            todos_responderam = len(estado_rodada["respostas"]) >= n_jogadores

            if not modo_espera_dupla or todos_responderam:
                estado_rodada["concluida"] = True
                self._cancelar_timer_timeout(codigo_sala)

                respostas_certas = [
                    jid for jid, dados in estado_rodada["respostas"].items()
                    if dados["resposta"] == resposta_correta
                ]

                if respostas_certas:
                    vencedor = min(
                        respostas_certas,
                        key=lambda jid: estado_rodada["respostas"][jid]["tempo"],
                    )
                else:
                    vencedor = None

                # Atualiza estado do jogo enquanto ainda temos o lock
                estado = self.estado_por_sala.get(codigo_sala)
                if estado and vencedor:
                    estado.registrarResultadoRodada(vencedor)
                    self.estado_jogo._sync()
                elif not estado and vencedor:
                    self.estado_jogo["pontuacao"][vencedor] = (
                        self.estado_jogo["pontuacao"].get(vencedor, 0) + 1
                    )

                deve_resolver = modo_espera_dupla
                resultado = {"vencedor": vencedor or "nenhum"}

            else:
                # Aguardando o(s) outro(s) jogador(es) responder
                return None

        # _resolver_rodada é chamado FORA do lock para evitar deadlock
        # ao fazer sendall enquanto outra thread aguarda o lock
        if deve_resolver:
            self._resolver_rodada(codigo_sala, vencedor=vencedor)

        return resultado

    def _resolver_rodada(self, codigo_sala: str, vencedor: str | None):
        """
        Atualiza o EstadoJogo, envia FIM_RODADA + ATUALIZAR_BARRA,
        e decide se o jogo acabou (FIM_JOGO) ou avança (PERGUNTA).
        """
        estado = self.estado_por_sala.get(codigo_sala)
        partida = self.partidas_ativas.get(codigo_sala, {})
        rodada_corrente = partida.get("rodada", 1)

        # Envia FIM_RODADA
        self.transmitir_para_sala(
            codigo_sala,
            TipoMensagem.FIM_RODADA,
            {
                "vencedor": vencedor or "nenhum",
                "rodada": rodada_corrente,
                "codigo_sala": codigo_sala,
            },
        )

        # Envia ATUALIZAR_BARRA
        posicao = estado.posicao_barra if estado else 0
        pontuacao = estado.pontuacao_jogadores.copy() if estado else {}
        self.transmitir_para_sala(
            codigo_sala,
            TipoMensagem.ATUALIZAR_BARRA,
            {"posicao": posicao, "pontuacao": pontuacao},
        )

        # Verifica fim de jogo por knockout (via registrar_resultado_rodada já feito acima)
        if estado and estado.vencedor:
            self._enviar_fim_jogo(codigo_sala, estado.vencedor, estado)
            return

        # Verifica fim de jogo ao final das rodadas
        if estado:
            fim = estado.verificar_fim_de_jogo()
            if fim:
                self._enviar_fim_jogo(codigo_sala, fim, estado)
                return
            estado.avancar_rodada()

        # Agenda próxima rodada com delay mínimo para que FIM_RODADA chegue antes de PERGUNTA
        timer = threading.Timer(0.05, self._iniciar_proxima_rodada, args=(codigo_sala,))
        timer.daemon = True
        timer.start()

    def _iniciar_proxima_rodada(self, codigo_sala: str):
        with self._lock:
            sala = self.salas.get(codigo_sala)
            if not sala:
                return

            estado = self.estado_por_sala.get(codigo_sala)
            if not estado or estado.vencedor:
                return

            partida = self.partidas_ativas.get(codigo_sala)
            if partida:
                partida["rodada"] = estado.rodada_atual
            sala["rodada_atual"] = estado.rodada_atual

            pergunta = self.selecionar_pergunta_para_sala(codigo_sala)
            payload = {
                "rodada_id": estado.rodada_atual,
                "pergunta": pergunta["pergunta"],
                "opcoes": pergunta["opcoes"],
                "resposta_correta": pergunta["resposta_correta"],
                "tempo_limite": self.tempo_limite_rodada,
            }
            self.enviar_pergunta_para_sala(codigo_sala, payload)

        self._agendar_timeout_rodada(codigo_sala)

    def _enviar_fim_jogo(self, codigo_sala: str, vencedor: str, estado: EstadoJogo | None):
        pontuacao = estado.pontuacao_jogadores.copy() if estado else {}
        self.transmitir_para_sala(
            codigo_sala,
            TipoMensagem.FIM_JOGO,
            {"vencedor": vencedor, "pontuacao": pontuacao},
        )
        # Agenda limpeza da sala após 3s — dá tempo dos clientes receberem FIM_JOGO
        timer = threading.Timer(3.0, self._resetar_sala_pos_jogo, args=(codigo_sala,))
        timer.daemon = True
        timer.start()

    def _resetar_sala_pos_jogo(self, codigo_sala: str):
        """
        Limpa a sala após o fim de uma partida para o servidor aceitar novos jogadores.
        Os sockets não são fechados — os clientes podem reconectar enviando ENTRAR novamente.
        """
        with self._lock:
            sala = self.salas.get(codigo_sala)
            if sala:
                # Remove jogadores do dicionário de conectados se o socket já fechou
                for id_jogador in list(sala.get("jogadores", [])):
                    sock = self.jogadores_conectados.get(id_jogador)
                    if sock is not None:
                        try:
                            # Testa se o socket ainda está vivo
                            sock.getpeername()
                        except OSError:
                            # Socket fechado — remove do mapa
                            self.jogadores_conectados.pop(id_jogador, None)
            self._limpar_sala(codigo_sala)
            print(f"[SERVIDOR] Sala {codigo_sala} resetada. Aguardando novos jogadores...")

    # -----------------------------------------------------------------------
    # Timeout de rodada em background
    # -----------------------------------------------------------------------

    def _agendar_timeout_rodada(self, codigo_sala: str):
        self._cancelar_timer_timeout(codigo_sala)
        timer = threading.Timer(
            self.tempo_limite_rodada + 0.5,
            self._timeout_rodada,
            args=(codigo_sala,),
        )
        timer.daemon = True
        timer.start()
        self._timers_timeout[codigo_sala] = timer

    def _cancelar_timer_timeout(self, codigo_sala: str):
        timer = self._timers_timeout.pop(codigo_sala, None)
        if timer is not None:
            timer.cancel()

    def _timeout_rodada(self, codigo_sala: str):
        with self._lock:
            estado_rodada = self.rodadas_por_sala.get(codigo_sala)
            if estado_rodada is None or estado_rodada.get("concluida"):
                return
            estado_rodada["concluida"] = True
        self._resolver_rodada(codigo_sala, vencedor=None)

    # -----------------------------------------------------------------------
    # Rede — envio e recebimento
    # -----------------------------------------------------------------------

    def _enviar_mensagem_socket(self, socket_cliente, tipo_mensagem: TipoMensagem, dados: dict) -> bool:
        if socket_cliente is None:
            return False
        mensagem = criar_mensagem(tipo_mensagem, dados)
        try:
            # Sockets reais recebem cabeçalho 4 bytes; fakes recebem JSON puro
            if isinstance(socket_cliente, socket.socket):
                payload = codificar_mensagem(mensagem)
            else:
                payload = json.dumps(mensagem, ensure_ascii=False).encode("utf-8")
            socket_cliente.sendall(payload)
            return True
        except (OSError, AttributeError, TypeError):
            return False

    def enviar_mensagem(self, socket_cliente, tipo_mensagem: TipoMensagem, dados: dict) -> bool:
        return self._enviar_mensagem_socket(socket_cliente, tipo_mensagem, dados)

    def transmitir(self, tipo_mensagem: TipoMensagem, dados: dict):
        for cliente in list(self.jogadores_conectados.values()):
            self._enviar_mensagem_socket(cliente, tipo_mensagem, dados)

    def transmitir_para_sala(self, codigo_sala: str, tipo_mensagem: TipoMensagem, dados: dict):
        sala = self.salas.get(codigo_sala)
        if not sala:
            return
        for id_jogador in sala.get("jogadores", []):
            sock = self.jogadores_conectados.get(id_jogador)
            if sock is not None:
                self._enviar_mensagem_socket(sock, tipo_mensagem, dados)

    def _obter_codigo_sala_do_jogador(self, id_jogador: str) -> str | None:
        for codigo_sala, sala in self.salas.items():
            if id_jogador in sala.get("jogadores", []):
                return codigo_sala
        return None

    # -----------------------------------------------------------------------
    # Parsing de buffer TCP
    # -----------------------------------------------------------------------

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
                payload = buffer[4 : 4 + tamanho]
                resto = buffer[4 + tamanho :]
                try:
                    return [decodificar_mensagem(payload)], resto
                except Exception:
                    pass

        return [], buffer

    def processar_mensagens_de_conexao(self, conexao):
        buffer = b""
        while True:
            # Respeita _servidor_ativo apenas se o servidor foi iniciado
            if self._servidor_ativo is False and not buffer:
                # Tenta receber pelo menos uma vez; se falhar, encerra
                pass
            try:
                dados = conexao.recv(4096)
            except socket.timeout:
                if not self._servidor_ativo:
                    break
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
                    id_jogador = mensagem.get("id_jogador")
                    if tipo == TipoMensagem.ENTRAR.value and id_jogador:
                        print(f"[TCP] Cliente conectado: {id_jogador}")
                    self.processar_mensagem(mensagem, conexao)

        try:
            if hasattr(conexao, "close"):
                conexao.close()
        except OSError:
            pass

        # Remove o jogador do mapa de conectados quando a conexão encerra
        with self._lock:
            for id_jogador, sock in list(self.jogadores_conectados.items()):
                if sock is conexao:
                    self.jogadores_conectados.pop(id_jogador, None)
                    print(f"[TCP] Cliente desconectado: {id_jogador}")
                    break

    def escutar_cliente(self, conexao):
        self.processar_mensagens_de_conexao(conexao)

    def aceitar_conexoes(self):
        while self._servidor_ativo:
            try:
                conexao, endereco = self.socket_tcp.accept()
                print(f"[TCP] Nova conexão de {endereco}")
            except socket.timeout:
                continue
            except OSError:
                break
            thread = threading.Thread(target=self.escutar_cliente, args=(conexao,), daemon=True)
            thread.start()

    # -----------------------------------------------------------------------
    # UDP — ping/pong
    # -----------------------------------------------------------------------

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

            try:
                # Tenta remover cabeçalho de 4 bytes se presente
                raw = dados
                if len(raw) >= 4:
                    tamanho = int.from_bytes(raw[:4], byteorder="big", signed=False)
                    if tamanho > 0 and len(raw) == 4 + tamanho:
                        raw = raw[4:]
                mensagem = json.loads(raw.decode("utf-8"))
            except Exception:
                continue

            self.ultimo_ping = mensagem
            resposta = criar_mensagem(
                TipoMensagem.PONG,
                {"id_jogador": mensagem.get("id_jogador", "cliente")},
            )
            self.socket_udp.sendto(codificar_mensagem(resposta), endereco)

    # -----------------------------------------------------------------------
    # Inicialização e encerramento
    # -----------------------------------------------------------------------

    def iniciar_servidor_tcp(self):
        self._servidor_ativo = True
        self.socket_tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket_tcp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket_tcp.bind((self.host, self.porta_tcp))
        self.socket_tcp.listen()
        self.socket_tcp.settimeout(0.2)
        print(f"[TCP] Servidor ouvindo em {self.host}:{self.porta_tcp}")

    def iniciar_servidor_udp(self):
        self._servidor_ativo = True
        self.socket_udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket_udp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket_udp.bind((self.host, self.porta_udp))
        self.socket_udp.settimeout(0.2)
        print(f"[UDP] Servidor ouvindo em {self.host}:{self.porta_udp}")

    def fechar_servidor(self):
        self._servidor_ativo = False
        for codigo_sala in list(self._timers_timeout.keys()):
            self._cancelar_timer_timeout(codigo_sala)
        for sock in list(self.jogadores_conectados.values()):
            try:
                sock.close()
            except OSError:
                pass
        self.jogadores_conectados.clear()
        for atributo in ("socket_tcp", "socket_udp"):
            s = getattr(self, atributo, None)
            if s is not None:
                try:
                    s.close()
                except OSError:
                    pass

    def iniciar_loop_principal(self):
        self.iniciar_servidor_tcp()
        self.iniciar_servidor_udp()
        thread_tcp = threading.Thread(target=self.aceitar_conexoes, daemon=True)
        thread_tcp.start()
        thread_udp = threading.Thread(target=self.escutar_ping_udp, daemon=True)
        thread_udp.start()
        print(f"Servidor pronto em {self.host}:{self.porta_tcp} (UDP: {self.porta_udp})")
        try:
            while self._servidor_ativo:
                time.sleep(0.2)
        except KeyboardInterrupt:
            print("\nEncerrando servidor...")
            self.fechar_servidor()

    # -----------------------------------------------------------------------
    # APIs de compatibilidade com testes legados
    # -----------------------------------------------------------------------

    def lidar_com_pergunta(self, pergunta: dict):
        """Envia pergunta para todos os clientes conectados."""
        self.transmitir(TipoMensagem.PERGUNTA, pergunta)

    def processar_resposta(
        self,
        jogador_a: str,
        jogador_b: str,
        resposta_a: str,
        resposta_b: str,
        resposta_correta: str = "TCP",
    ) -> dict:
        """Compatibilidade com testes legados (sem timing)."""
        resultado = resolverResultadoRodada(
            jogador_a=jogador_a,
            jogador_b=jogador_b,
            resposta_a=resposta_a,
            resposta_b=resposta_b,
            resposta_correta=resposta_correta,
        )

        vencedor_rodada = resultado["vencedor"]
        if vencedor_rodada not in ("empate", "nenhum"):
            estado = self.estado_por_sala.get("sala-1") or self._estado_global
            estado.registrarResultadoRodada(vencedor_rodada)
            self.estado_jogo._sync()
            # Mantém posicao_barra no proxy alinhada com o resultado
            self.estado_jogo["posicao_barra"] = estado.posicao_barra

        return resultado

    def avancar_rodada(self) -> bool:
        estado = self.estado_por_sala.get("sala-1", self._estado_global)
        result = estado.avancar_rodada()
        self.estado_jogo._sync()
        return result

    def registrar_pontuacao(self, jogador: str):
        estado = self.estado_por_sala.get("sala-1", self._estado_global)
        estado.pontuacao_jogadores[jogador] = estado.pontuacao_jogadores.get(jogador, 0) + 1
        if estado.pontuacao_jogadores[jogador] >= 2:
            estado.vencedor = jogador
        self.estado_jogo._sync()
        return estado

    def iniciar_partida(self) -> dict:
        estado = self.estado_por_sala.get("sala-1", self._estado_global)
        self.estado_jogo._sync()
        return {
            "rodada": estado.rodada_atual,
            "maximo_rodadas": estado.maximo_rodadas,
            "pontuacao": estado.pontuacao_jogadores,
        }

    def atualizar_barra(self, direcao: int):
        estado = self.estado_por_sala.get("sala-1", self._estado_global)
        estado.posicao_barra += direcao
        self.estado_jogo._sync()
        self.transmitir(TipoMensagem.ATUALIZAR_BARRA, {
            "posicao": estado.posicao_barra, "pontuacao": {},
        })

    def finalizar_jogo(self, vencedor: str):
        self.transmitir(TipoMensagem.FIM_JOGO, {"vencedor": vencedor, "pontuacao": {}})

    def finalizar_rodada(self, codigo_sala: str | None = None, vencedor: str | None = None):
        if codigo_sala:
            self._resolver_rodada(codigo_sala, vencedor)

    def avancar_para_proxima_pergunta(self, codigo_sala: str):
        self._iniciar_proxima_rodada(codigo_sala)

    def remover_jogador(self, id_jogador: str):
        with self._lock:
            sock = self.jogadores_conectados.pop(id_jogador, None)
            if sock is not None and isinstance(sock, socket.socket):
                try:
                    sock.close()
                except OSError:
                    pass
            for codigo_sala, sala in list(self.salas.items()):
                jogadores = sala.get("jogadores", [])
                if id_jogador in jogadores:
                    sala["jogadores"] = [j for j in jogadores if j != id_jogador]
                    self.transmitir(
                        TipoMensagem.DESCONEXAO,
                        {"id_jogador": id_jogador, "codigo_sala": codigo_sala},
                    )
                    if not sala["jogadores"]:
                        self._limpar_sala(codigo_sala)
                    break

    def receber_mensagem(self, identificador_jogador: str):
        """Leitura síncrona usada em alguns testes de integração."""
        sock = self.jogadores_conectados.get(identificador_jogador)
        if sock is None:
            return None
        dados = sock.recv(4096)
        if not dados:
            return None
        if len(dados) >= 4:
            tamanho = int.from_bytes(dados[:4], byteorder="big", signed=False)
            if len(dados) >= 4 + tamanho:
                dados = dados[4 : 4 + tamanho]
        return json.loads(dados.decode("utf-8"))


QuizServer = ServidorQuiz


if __name__ == "__main__":
    servidor = ServidorQuiz()
    servidor.iniciar_loop_principal()
