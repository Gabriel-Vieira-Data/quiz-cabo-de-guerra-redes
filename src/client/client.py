"""
client.py — Biblioteca cliente do Quiz Cabo de Guerra.

Esta classe é a CAMADA DE TRANSPORTE que um frontend usa para falar com o
servidor. Ela cuida de:
  - conectar/fechar sockets TCP e UDP;
  - enquadrar (framing) mensagens TCP no formato [4 bytes tamanho][JSON];
  - remontar mensagens que chegam fragmentadas ou em rajada;
  - enviar PING e ler PONG via UDP, calculando a latência (RTT);
  - despachar mensagens recebidas para callbacks por tipo (dispatcher).

O frontend NÃO precisa mexer em sockets — basta instanciar ClienteQuiz,
conectar, registrar callbacks e chamar `escutar_em_thread()`.
"""
import json
import socket
import threading
import time

from src.common.protocol import (
    TipoMensagem,
    criar_mensagem,
    decodificar_mensagem,
    codificar_mensagem,
)


class ClienteQuiz:
    """
    Cliente TCP/UDP do Quiz Cabo de Guerra.

    Framing TCP: cada mensagem é [4 bytes big-endian = tamanho][payload JSON UTF-8].
    O buffer acumula bytes e extrai mensagens completas uma a uma, sem perder
    mensagens que cheguem juntas no mesmo recv (rajada) nem quebrar quando uma
    mensagem chega dividida em vários recv (fragmentação).
    """

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

        # Callbacks do dispatcher: { "PERGUNTA": funcao, ... }
        self._handlers: dict[str, callable] = {}
        # id definitivo recebido do servidor no BEM_VINDO (pode diferir do enviado).
        self.id_jogador_confirmado: str | None = None
        # Última latência medida em milissegundos (via PING/PONG).
        self.latencia_ms: float | None = None

        self._thread_escuta: threading.Thread | None = None
        self._escutando = False

    # -----------------------------------------------------------------------
    # Conexão
    # -----------------------------------------------------------------------

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

    def fechar(self):
        """Fecha ambos os sockets e para o loop de escuta."""
        self._escutando = False
        for sock in (self.socket_tcp, self.socket_udp):
            try:
                sock.close()
            except OSError:
                pass

    # -----------------------------------------------------------------------
    # Envio de mensagens (Cliente → Servidor)
    # -----------------------------------------------------------------------

    def enviar_entrada(self, id_jogador: str, apelido: str):
        """Envia ENTRAR para entrar na fila. O servidor responde com BEM_VINDO."""
        mensagem = criar_mensagem(TipoMensagem.ENTRAR, {"id_jogador": id_jogador, "apelido": apelido})
        self.socket_tcp.sendall(codificar_mensagem(mensagem))

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

    def _extrair_mensagens_do_buffer(self):
        """
        Extrai todas as mensagens completas presentes em self._buffer e as
        coloca em self._mensagens_pendentes.

        Suporta dois formatos:
          - Com cabeçalho de 4 bytes (formato oficial TCP)
          - JSON puro concatenado (compatibilidade com testes/scripts)
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

            payload = self._buffer[4:4 + tamanho]
            self._buffer = self._buffer[4 + tamanho:]
            try:
                self._mensagens_pendentes.append(decodificar_mensagem(payload))
            except Exception:
                pass  # mensagem malformada — ignora e segue

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

    def definir_timeout(self, segundos: float | None):
        """
        Define um timeout de leitura no socket TCP. Com timeout, receber_mensagem
        retorna None periodicamente em vez de bloquear para sempre — útil para
        loops de UI que precisam checar uma flag de parada.
        """
        try:
            self.socket_tcp.settimeout(segundos)
        except OSError:
            pass

    # -----------------------------------------------------------------------
    # Dispatcher de eventos (conveniência para o frontend)
    # -----------------------------------------------------------------------

    def registrar_handler(self, tipo: str, funcao):
        """
        Registra uma função a ser chamada quando uma mensagem daquele tipo
        chegar. Ex.: cliente.registrar_handler("PERGUNTA", minha_funcao).
        A função recebe o dict da mensagem como único argumento.
        """
        self._handlers[str(tipo)] = funcao

    def _despachar(self, mensagem: dict):
        """Chama o handler registrado para o tipo da mensagem, se houver."""
        tipo = mensagem.get("tipo", "")
        # Guarda o id confirmado assim que o BEM_VINDO chega.
        if tipo == TipoMensagem.BEM_VINDO.value:
            self.id_jogador_confirmado = mensagem.get("id_jogador")
        handler = self._handlers.get(tipo)
        if handler is not None:
            handler(mensagem)

    def escutar_em_thread(self):
        """
        Inicia uma thread que fica recebendo mensagens e despachando para os
        handlers registrados. O frontend chama isto uma vez após conectar e
        registrar seus handlers — não precisa gerenciar threads na mão.
        """
        if self._escutando:
            return
        self._escutando = True

        def _loop():
            while self._escutando:
                try:
                    msg = self.receber_mensagem()
                except Exception:
                    break
                if msg is None:
                    # None = timeout (continua) ou conexão fechada (encerra).
                    if not self._conexao_viva():
                        break
                    continue
                self._despachar(msg)

        self._thread_escuta = threading.Thread(target=_loop, daemon=True)
        self._thread_escuta.start()

    def _conexao_viva(self) -> bool:
        """Retorna True se o socket TCP ainda está conectado ao servidor."""
        try:
            self.socket_tcp.getpeername()
            return True
        except OSError:
            return False

    # -----------------------------------------------------------------------
    # PING / PONG (UDP) — medição de latência
    # -----------------------------------------------------------------------

    def enviar_ping_udp(self):
        """
        Envia um PING via UDP incluindo o timestamp atual. Datagrama JSON puro
        (sem cabeçalho de tamanho, pois UDP não é stream).
        """
        ping = criar_mensagem(TipoMensagem.PING, {"id_jogador": "cliente", "ts": time.time()})
        payload = json.dumps(ping, ensure_ascii=False).encode("utf-8")
        self.socket_udp.sendto(payload, (self.host, self.porta_udp))

    def receber_pong_udp(self, timeout: float = 1.0) -> float | None:
        """
        Aguarda o PONG do servidor e calcula a latência (RTT) em milissegundos.

        Retorna a latência em ms, ou None se não houver resposta dentro do
        timeout. Atualiza também self.latencia_ms.
        """
        try:
            self.socket_udp.settimeout(timeout)
            dados, _ = self.socket_udp.recvfrom(4096)
        except (socket.timeout, OSError):
            return None

        try:
            mensagem = json.loads(dados.decode("utf-8"))
        except Exception:
            return None

        ts_enviado = mensagem.get("ts")
        if ts_enviado is not None:
            self.latencia_ms = (time.time() - float(ts_enviado)) * 1000.0
            return self.latencia_ms
        return None

    def medir_latencia(self, timeout: float = 1.0) -> float | None:
        """Envia um PING e espera o PONG, retornando a latência em ms (ou None)."""
        self.enviar_ping_udp()
        return self.receber_pong_udp(timeout=timeout)


