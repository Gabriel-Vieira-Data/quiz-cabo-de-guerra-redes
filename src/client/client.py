"""
client.py — Biblioteca cliente do Quiz Cabo de Guerra.

Esta classe é a CAMADA DE TRANSPORTE que a interface (gui.py) usa para falar
com o servidor. Ela cuida de:
  - conectar/fechar sockets TCP e UDP;
  - enquadrar (framing) mensagens TCP no formato [4 bytes tamanho][JSON];
  - remontar mensagens que chegam fragmentadas ou em rajada;
  - enviar PING e ler PONG via UDP, calculando a latência (RTT).

Marcação de origem: "# [Origem: ...]" acima de cada
classe/função — "IA" = escrito com auxílio de IA; "autoral" = escrito pelos
integrantes sem IA (medido com git blame) — e "# [IA - base inicial]" nos
trechos da base inicial gerados com IA.
"""
import json
import socket
import time

from src.common.protocol import (
    TipoMensagem,
    criar_mensagem,
    decodificar_mensagem,
    codificar_mensagem,
)


# [Origem: IA 86% · autoral 14%]
class ClienteQuiz:
    """
    Cliente TCP/UDP do Quiz Cabo de Guerra.

    Framing TCP: cada mensagem é [4 bytes big-endian = tamanho][payload JSON UTF-8].
    O buffer acumula bytes e extrai mensagens completas uma a uma, sem perder
    mensagens que cheguem juntas no mesmo recv (rajada) nem quebrar quando uma
    mensagem chega dividida em vários recv (fragmentação).
    """

    # [Origem: autoral 70% · IA 30%]
    def __init__(self, host: str = "127.0.0.1", porta_tcp: int = 5000, porta_udp: int = 5001):
        self.host = host
        self.porta_tcp = porta_tcp
        self.porta_udp = porta_udp

        # Buffer de bytes ainda não consumidos e fila de mensagens já parseadas.
        self._buffer = b""
        self._mensagens_pendentes: list[dict] = []

        # Sockets: TCP para o jogo, UDP para ping/latência.
        self.socket_tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket_udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        # Última latência medida em milissegundos (via PING/PONG).
        self.latencia_ms: float | None = None
        self._inicio_ping = 0.0   # momento (perf_counter) em que o último PING saiu

    # -----------------------------------------------------------------------
    # Conexão
    # -----------------------------------------------------------------------

    # [Origem: IA 62% · autoral 38%]
    def conectar(self):
        """Abre a conexão TCP com o servidor e prepara o socket UDP."""
        self.socket_tcp.connect((self.host, self.porta_tcp))
        # Keepalive: o SO detecta conexões mortas mesmo sem tráfego ativo.
        try:
            self.socket_tcp.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        except (OSError, AttributeError):
            pass
        # Bind do UDP numa porta efêmera para conseguir receber PONG.
        self.socket_udp.bind(("0.0.0.0", 0))

    # [Origem: IA]
    def fechar(self):
        """Fecha os sockets TCP e UDP."""
        for sock in (self.socket_tcp, self.socket_udp):
            try:
                sock.close()
            except OSError:
                pass

    # -----------------------------------------------------------------------
    # Envio de mensagens (Cliente → Servidor)
    # -----------------------------------------------------------------------

    # [Origem: autoral 75% · IA 25%]
    def enviar_entrada(self, id_jogador: str, apelido: str):
        """Envia ENTRAR para entrar na fila. O servidor responde com BEM_VINDO."""
        mensagem = criar_mensagem(TipoMensagem.ENTRAR, {"id_jogador": id_jogador, "apelido": apelido})
        self.socket_tcp.sendall(codificar_mensagem(mensagem))

    # [Origem: autoral 86% · IA 14%]
    def enviar_resposta(self, id_jogador: str, rodada_id: int, resposta: str):
        """Envia a RESPOSTA do jogador para a rodada atual."""
        mensagem = criar_mensagem(
            TipoMensagem.RESPOSTA,
            {"id_jogador": id_jogador, "rodada_id": rodada_id, "resposta": resposta},
        )
        self.socket_tcp.sendall(codificar_mensagem(mensagem))

    # -----------------------------------------------------------------------
    # Recepção com framing robusto
    # -----------------------------------------------------------------------

    # [Origem: IA]
    def _extrair_mensagens_do_buffer(self):
        """
        Extrai todas as mensagens completas presentes em self._buffer e as
        coloca em self._mensagens_pendentes.

        Suporta dois formatos:
          - Com cabeçalho de 4 bytes (formato oficial TCP)
          - JSON puro concatenado (compatibilidade com testes/scripts)

        [IA - base inicial] A leitura com buffer + cabeçalho de 4 bytes e o
        modo de compatibilidade vieram da base inicial, gerada com IA.

        Exemplo: se chegarem 2,5 mensagens num recv(), as duas completas vão
        para a fila e a metade que sobrou fica no buffer esperando o resto.
        """
        while self._buffer:
            texto = self._buffer.lstrip()
            offset_espacos = len(self._buffer) - len(texto)

            # ── Formato JSON puro (começa com '{') ───────────────────────
            if texto[:1] == b"{":
                try:
                    mensagem, pos = json.JSONDecoder().raw_decode(texto.decode("utf-8"))
                except (ValueError, UnicodeDecodeError):
                    break  # JSON ainda incompleto — aguarda mais bytes
                self._mensagens_pendentes.append(mensagem)
                self._buffer = self._buffer[offset_espacos + pos:]
                continue

            # ── Formato com cabeçalho de 4 bytes ─────────────────────────
            if len(self._buffer) < 4:
                break  # cabeçalho incompleto

            tamanho = int.from_bytes(self._buffer[:4], byteorder="big", signed=False)
            if tamanho <= 0:
                # Cabeçalho inválido: descarta 4 bytes e tenta ressincronizar.
                self._buffer = self._buffer[4:]
                continue

            if len(self._buffer) < 4 + tamanho:
                break  # payload ainda não chegou por completo

            # Recorta exatamente uma mensagem e deixa o resto no buffer.
            payload = self._buffer[4:4 + tamanho]
            self._buffer = self._buffer[4 + tamanho:]
            try:
                self._mensagens_pendentes.append(decodificar_mensagem(payload))
            except Exception:
                pass  # mensagem malformada — ignora e segue

    # [Origem: IA]
    def receber_mensagem(self):
        """
        Retorna a próxima mensagem completa (dict) ou None se a conexão
        fechou / deu timeout. Entrega mensagens já parseadas antes de ler mais
        bytes do socket. É BLOQUEANTE (a menos que o socket tenha settimeout).
        """
        if self._mensagens_pendentes:
            return self._mensagens_pendentes.pop(0)

        while True:
            self._extrair_mensagens_do_buffer()
            if self._mensagens_pendentes:
                return self._mensagens_pendentes.pop(0)

            try:
                dados = self.socket_tcp.recv(4096)
            except socket.timeout:
                return None
            except OSError:
                return None

            if not dados:
                return None  # conexão fechada pelo servidor

            self._buffer += dados

    # -----------------------------------------------------------------------
    # PING / PONG (UDP) — medição de latência
    # -----------------------------------------------------------------------

    # [Origem: IA]
    def enviar_ping_udp(self, id_jogador: str = "cliente") -> float:
        """
        Envia um PING via UDP com o horário atual ("ts"). Datagrama JSON puro
        (sem cabeçalho de tamanho, pois UDP não é stream). Retorna o ts enviado.
        """
        ts = time.time()
        ping = criar_mensagem(TipoMensagem.PING, {"id_jogador": id_jogador, "ts": ts})
        payload = json.dumps(ping, ensure_ascii=False).encode("utf-8")
        # perf_counter é o relógio mais preciso para medir intervalos curtos.
        self._inicio_ping = time.perf_counter()
        self.socket_udp.sendto(payload, (self.host, self.porta_udp))
        return ts

    # [Origem: IA]
    def receber_pong_udp(self, ts_esperado: float, timeout: float = 1.0) -> float | None:
        """
        Aguarda o PONG do PING enviado em `ts_esperado` e calcula a latência
        (RTT) em milissegundos. Retorna None se ele não chegar a tempo.

        Como UDP não garante nada, um PONG de uma medição anterior pode chegar
        atrasado: por isso só aceitamos o PONG cujo "ts" é o do PING atual.
        """
        prazo = time.time() + timeout
        while True:
            restante = prazo - time.time()
            if restante <= 0:
                return None
            try:
                self.socket_udp.settimeout(restante)
                dados, _ = self.socket_udp.recvfrom(4096)
                mensagem = json.loads(dados.decode("utf-8"))
            except (socket.timeout, OSError, ValueError):
                return None

            if mensagem.get("tipo") != TipoMensagem.PONG.value:
                continue
            if mensagem.get("ts") != ts_esperado:
                continue  # PONG atrasado de um PING antigo: descarta

            # RTT (round-trip time) = agora − momento em que o PING saiu.
            # Tudo medido no relógio do cliente: não depende do relógio do servidor.
            self.latencia_ms = (time.perf_counter() - self._inicio_ping) * 1000.0
            return self.latencia_ms

    # [Origem: IA]
    def medir_latencia(self, id_jogador: str = "cliente", timeout: float = 1.0) -> float | None:
        """Envia um PING e espera o PONG, retornando a latência em ms (ou None)."""
        ts = self.enviar_ping_udp(id_jogador)
        return self.receber_pong_udp(ts, timeout=timeout)


