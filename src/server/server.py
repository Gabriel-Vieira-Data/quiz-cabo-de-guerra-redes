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

Marcação de origem (ver USO_DE_IA.md):
  Cada classe/função tem acima um comentário "# [Origem: ...]", medido com
  git blame: "IA" = escrito com auxílio de IA; "autoral" = escrito pelos
  integrantes sem IA. Funções mistas mostram a
  porcentagem de cada origem. Trechos da base inicial que foram gerados com
  IA estão marcados também com "# [IA - base inicial]".
"""
import json
import re
import socket
import threading
import time
from typing import Dict

from src.common.banco_perguntas import BancoPerguntas
from src.common.game_logic import EstadoJogo
from src.common.protocol import (
    TAMANHO_MAXIMO_MENSAGEM,
    TipoMensagem,
    codificar_mensagem,
    criar_mensagem,
    decodificar_mensagem,
)


# [Origem: IA]
class ServidorQuiz:
    # [Origem: IA 56% · autoral 44%]
    def __init__(self, host: str = "0.0.0.0", porta_tcp: int = 5000, porta_udp: int = 5001):
        self.host = host
        self.porta_tcp = porta_tcp
        self.porta_udp = porta_udp
        # [IA - base inicial] Trava REENTRANTE compartilhada por todas as threads.
        # Várias threads (uma por cliente, o timer de rodada, a de UDP) mexem nos
        # mesmos dicionários; o lock garante que só uma por vez altere o estado.
        # É RLock (e não Lock) porque funções protegidas chamam outras funções
        # que também fazem "with self._lock" — com Lock comum a própria thread
        # ficaria travada esperando por ela mesma (deadlock).
        self._lock = threading.RLock()

        # Conexões e fila
        self.jogadores_conectados: Dict[str, socket.socket] = {}
        self.apelidos: Dict[str, str] = {}          # id_jogador → apelido exibido
        self.socket_para_jogador: dict = {}          # id(socket) → id_jogador (anti-trapaça)
        self.fila_espera: list[str] = []
        self.tempo_limite_espera = 60                # segundos aguardando 2º jogador
        self._timers_espera: dict[str, threading.Timer] = {}

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
        self.banco_perguntas = BancoPerguntas()
        self.tempo_limite_rodada = 30
        # Pausa entre o fim de uma rodada e a próxima pergunta, para os
        # jogadores verem qual era a resposta correta.
        self.pausa_entre_rodadas = 2.0

        # Reconexão: quando um jogador cai no meio da partida, ela fica em
        # espera por tempo_reconexao segundos. Cada ausente tem seu próprio
        # cronômetro: { id_jogador: {"timer", "sala", "inicio"} }.
        self.tempo_reconexao = 30
        self._ausentes: dict[str, dict] = {}

        self._servidor_ativo = False
    # -----------------------------------------------------------------------
    # Identificação de jogadores
    # -----------------------------------------------------------------------

    # [Origem: IA]
    # [IA - base inicial] Função inteira gerada com IA.
    def _gerar_id_jogador_disponivel(self, identificador_jogador: str | None) -> str:
        """
        Garante que cada jogador tenha um id único no servidor.

        Se o id pedido já está em uso (ex.: dois clientes pedindo "player-1"),
        gera "player-2", "player-3"... A regex separa o nome do número final:
          "player-1" → nome "player", número 1
          "alice"    → nome "alice",  sem número (começa do 1)
        "(.+?)" pega o nome (o "?" o torna preguiçoso, para não engolir o
        número) e "-?(\\d+)?" pega um hífen e um número opcionais no fim.
        Se nenhum dos 1000 candidatos estiver livre, usa o horário em ms.
        """
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

    # [Origem: autoral 75% · IA 25%]
    def adicionar_jogador_espera(self, id_jogador: str):
        with self._lock:
            if id_jogador not in self.fila_espera:
                self.fila_espera.append(id_jogador)

    # [Origem: autoral 67% · IA 33%]
    def criar_sala_para_espera(self) -> dict | None:
        with self._lock:
            # Só forma uma sala quando há PELO MENOS 2 jogadores NA FILA, e
            # sempre com uma sala nova: um jogador sozinho nunca inicia partida.
            if len(self.fila_espera) < 2:
                return None

            # Cada dupla ganha a sua própria sala; as partidas que já estão
            # em andamento continuam (várias partidas ao mesmo tempo).
            jogadores = self.fila_espera[:2]
            self.fila_espera = self.fila_espera[2:]
            codigo_sala = self._gerar_codigo_sala()

            self.salas[codigo_sala] = {
                "codigo": codigo_sala,
                "jogadores": jogadores,
                "estado": "esperando",
                "rodada_atual": 1,
            }
            self.perguntas_usadas_por_sala[codigo_sala] = set()
            return self.salas[codigo_sala]

    # [Origem: IA]
    def _gerar_codigo_sala(self) -> str:
        """
        Devolve o menor código "sala-N" que não está em uso. Salas em andamento
        nunca são reaproveitadas; o número de uma sala encerrada volta a ficar livre.
        """
        numero = 1
        while f"sala-{numero}" in self.salas:
            numero += 1
        return f"sala-{numero}"

    # [Origem: IA]
    def _limpar_sala(self, codigo_sala: str):
        self._cancelar_timer_timeout(codigo_sala)
        # Cancela a espera de reconexão de quem era desta sala.
        for id_ausente, info in list(self._ausentes.items()):
            if info["sala"] == codigo_sala:
                info["timer"].cancel()
                del self._ausentes[id_ausente]
        self.salas.pop(codigo_sala, None)
        self.partidas_ativas.pop(codigo_sala, None)
        self.estado_por_sala.pop(codigo_sala, None)
        self.rodadas_por_sala.pop(codigo_sala, None)
        self.perguntas_rodada.pop(codigo_sala, None)
        self.perguntas_usadas_por_sala.pop(codigo_sala, None)

    # -----------------------------------------------------------------------
    # Início de partida
    # -----------------------------------------------------------------------

    # [Origem: autoral 71% · IA 29%]
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

    # [Origem: IA]
    def selecionar_pergunta_para_sala(self, codigo_sala: str) -> dict:
        """Sorteia uma pergunta ainda não usada na sala e zera o estado da rodada."""
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
            original = random.choice(disponiveis)
            # Cópia com as opções embaralhadas: no banco a resposta certa costuma
            # ser a 1ª opção. A correção compara pelo TEXTO (resposta_correta),
            # então a ordem não afeta a validação. O banco original não é alterado.
            opcoes = list(original["opcoes"])
            random.shuffle(opcoes)
            pergunta = {**original, "opcoes": opcoes}
            self.perguntas_usadas_por_sala.setdefault(codigo_sala, set()).add(pergunta["pergunta"])
            self.perguntas_rodada[codigo_sala] = pergunta

            # Descobre o número da rodada atual (a partir do EstadoJogo da sala).
            # É usado para validar que uma RESPOSTA pertence à rodada corrente.
            estado_jogo_sala = self.estado_por_sala.get(codigo_sala)
            numero_rodada = estado_jogo_sala.rodada_atual if estado_jogo_sala else 1

            # Reinicia o estado da rodada
            self.rodadas_por_sala[codigo_sala] = {
                "inicio": time.time(),
                "respostas": {},
                "vencedor": None,
                "concluida": False,
                "rodada_id": numero_rodada,
            }
            return pergunta

    # [Origem: IA]
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

    # [Origem: IA]
    def processar_mensagem(self, mensagem: dict, socket_remetente: socket.socket | None = None):
        with self._lock:
            if not mensagem:
                return None

            tipo = str(mensagem.get("tipo", "")).upper()

            if tipo == TipoMensagem.ENTRAR.value:
                return self._handle_entrar(mensagem, socket_remetente)

            if tipo == TipoMensagem.RESPOSTA.value:
                return self._handle_resposta(mensagem, socket_remetente)

            return mensagem

    # [Origem: IA]
    def _handle_entrar(self, mensagem: dict, socket_remetente):
        """
        Trata a mensagem ENTRAR de um cliente:
          1. Resolve um id único (renomeia se houver colisão).
          2. Associa o socket ao id (para o anti-trapaça) e guarda o apelido.
          3. Envia BEM_VINDO ao cliente com o id DEFINITIVO — isso é essencial
             para o cliente conseguir se identificar no placar depois.
          4. Coloca na fila; se já houver 2 jogadores, inicia a partida.
        """
        id_jogador = mensagem.get("id_jogador")
        apelido = mensagem.get("apelido", id_jogador)
        if not id_jogador:
            return None

        # Limita o tamanho de campos vindos do cliente (defesa contra abuso/DoS).
        id_jogador = str(id_jogador)[:50]
        # Apelido: máx. 20 caracteres (mesmo limite validado na interface).
        apelido = str(apelido).strip()[:20] if apelido else apelido

        # ── Reentrada na MESMA conexão (ex.: "Jogar novamente") ──────────────
        # Se este socket já está associado a um jogador, é uma REENTRADA: o
        # cliente quer uma nova partida sem reconectar. Reusamos o MESMO id
        # (sem renomear) e apenas o recolocamos na fila. Isso evita tratar a
        # reentrada como um jogador novo (que geraria player-1-1, etc.).
        id_existente = None
        if socket_remetente is not None:
            id_existente = self.socket_para_jogador.get(id(socket_remetente))

        # ── Volta de um jogador que caiu no meio da partida ──────────────────
        # Se o id pertence a alguém que está sendo esperado, ele recupera o
        # lugar dele na sala em vez de entrar na fila como jogador novo.
        if id_existente is None:
            if id_jogador in self._ausentes:
                return self._reconectar_jogador(id_jogador, apelido, socket_remetente)
            id_livre = self._gerar_id_jogador_disponivel(id_jogador)
            if id_livre in self._ausentes:
                return self._reconectar_jogador(id_livre, apelido, socket_remetente)

        if id_existente is not None:
            id_jogador = id_existente
            # Atualiza o apelido caso o jogador tenha trocado.
            if apelido:
                self.apelidos[id_jogador] = apelido
            # Já está jogando numa sala: não volta para a fila (com várias
            # salas, isso o colocaria em duas partidas ao mesmo tempo).
            sala_atual = self._obter_codigo_sala_do_jogador(id_jogador)
            if sala_atual is not None:
                self._enviar_mensagem_socket(
                    socket_remetente,
                    TipoMensagem.BEM_VINDO,
                    {
                        "id_jogador": id_jogador,
                        "apelido": self.apelidos.get(id_jogador, id_jogador),
                        "em_partida": True,
                        "codigo_sala": sala_atual,
                    },
                )
                return self.salas[sala_atual]
        else:
            # Jogador novo: o servidor é a autoridade sobre o id (renomeia em colisão).
            id_jogador = id_livre
            if socket_remetente is not None:
                self.jogadores_conectados[id_jogador] = socket_remetente
                # Mapeia o socket → id para validar respostas (anti-trapaça).
                self.socket_para_jogador[id(socket_remetente)] = id_jogador
            # Guarda o apelido exibível (fallback para o próprio id).
            self.apelidos[id_jogador] = apelido or id_jogador

        self.adicionar_jogador_espera(id_jogador)
        sala = self.criar_sala_para_espera()
        em_partida = sala is not None and len(sala.get("jogadores", [])) == 2

        # ACK de ENTRAR: informa ao cliente seu id definitivo e o estado atual.
        # Sem isso, o cliente não saberia se foi renomeado nem se já está jogando.
        if socket_remetente is not None:
            self._enviar_mensagem_socket(
                socket_remetente,
                TipoMensagem.BEM_VINDO,
                {
                    "id_jogador": id_jogador,
                    "apelido": self.apelidos[id_jogador],
                    "em_partida": em_partida,
                    "codigo_sala": sala["codigo"] if sala else None,
                },
            )

        if em_partida:
            self._cancelar_timers_espera(sala["jogadores"])
            self.iniciar_partida_em_sala(sala["codigo"])
            self._iniciar_primeira_rodada(sala["codigo"])
            # Retorna a sala diretamente (contratos de teste dependem disso).
            return sala

        # Primeiro jogador: agenda um timeout de espera pelo segundo.
        if socket_remetente is not None:
            self._agendar_timeout_espera(id_jogador, socket_remetente)

        return None

    # [Origem: IA]
    def _agendar_timeout_espera(self, id_jogador: str, sock):
        """Avisa o jogador se ninguém entrar dentro do tempo limite de espera."""
        def _expirou():
            with self._lock:
                # Só dispara se o jogador ainda está esperando (não entrou em partida)
                if id_jogador in self.fila_espera:
                    self._enviar_mensagem_socket(
                        sock,
                        TipoMensagem.DESCONEXAO,
                        {
                            "id_jogador": "servidor",
                            "motivo": "timeout_espera",
                            "mensagem": "Nenhum adversário entrou a tempo. Tente novamente.",
                            "codigo_sala": None,
                        },
                    )
                    self.fila_espera = [j for j in self.fila_espera if j != id_jogador]
            self._timers_espera.pop(id_jogador, None)

        timer = threading.Timer(self.tempo_limite_espera, _expirou)
        timer.daemon = True
        timer.start()
        self._timers_espera[id_jogador] = timer

    # [Origem: IA]
    def _cancelar_timers_espera(self, jogadores: list[str]):
        """Cancela a espera por adversário só dos jogadores que acabaram de formar sala."""
        for id_jogador in jogadores:
            timer = self._timers_espera.pop(id_jogador, None)
            if timer is not None:
                timer.cancel()

    # [Origem: IA]
    def _handle_resposta(self, mensagem: dict, socket_remetente=None):
        id_jogador = mensagem.get("id_jogador")
        rodada_id = mensagem.get("rodada_id", 1)
        resposta = mensagem.get("resposta", "")

        if not id_jogador:
            return None

        # Anti-trapaça: se conhecemos o socket, o id_jogador da mensagem DEVE
        # corresponder ao id associado àquele socket. Isso impede que um cliente
        # responda "em nome" do adversário.
        if socket_remetente is not None:
            id_real = self.socket_para_jogador.get(id(socket_remetente))
            if id_real is not None and id_real != id_jogador:
                print(f"[SEGURANÇA] Resposta rejeitada: socket de '{id_real}' tentou responder como '{id_jogador}'")
                return None
            # Usa o id verdadeiro do socket, ignorando o que veio na mensagem
            if id_real is not None:
                id_jogador = id_real

        codigo_sala = self._obter_codigo_sala_do_jogador(id_jogador)
        if codigo_sala is None:
            return None

        return self.registrar_resposta_jogador(codigo_sala, rodada_id, id_jogador, resposta)

    # -----------------------------------------------------------------------
    # Lógica central de rodada
    # -----------------------------------------------------------------------

    # [Origem: IA]
    def _apelidos_e_placar_da_sala(self, codigo_sala: str):
        """Retorna (apelidos, pontuacao, posicao) da sala para incluir nos payloads."""
        estado = self.estado_por_sala.get(codigo_sala)
        sala = self.salas.get(codigo_sala, {})
        jogadores = sala.get("jogadores", [])
        apelidos = {jid: self.apelidos.get(jid, jid) for jid in jogadores}
        pontuacao = estado.pontuacao_jogadores.copy() if estado else {jid: 0 for jid in jogadores}
        posicao = estado.posicao_barra if estado else 0
        return apelidos, pontuacao, posicao

    # [Origem: IA]
    def _iniciar_primeira_rodada(self, codigo_sala: str):
        """Sorteia a 1ª pergunta, envia PERGUNTA aos dois jogadores e liga o timer da rodada."""
        pergunta = self.selecionar_pergunta_para_sala(codigo_sala)
        estado = self.estado_por_sala.get(codigo_sala)
        rodada_id = estado.rodada_atual if estado else 1
        # Os nomes já vão na 1ª PERGUNTA para a tela mostrá-los desde o começo.
        payload = self._payload_pergunta(codigo_sala, pergunta, rodada_id)
        self.enviar_pergunta_para_sala(codigo_sala, payload)
        self._agendar_timeout_rodada(codigo_sala)

    # [Origem: IA]
    def registrar_resposta_jogador(
        self, codigo_sala: str, rodada_id: int, id_jogador: str, resposta: str
    ):
        """
        Registra a RESPOSTA de um jogador e, se possível, resolve a rodada.

        Passos:
          1. Descarta respostas inválidas: sala/rodada inexistente, rodada já
             concluída, rodada_id diferente do atual (resposta atrasada) ou
             segunda resposta do mesmo jogador.
          2. Guarda a resposta com o horário de chegada.
          3. Quando os dois responderam, vence quem ACERTOU PRIMEIRO
             (menor horário entre as respostas corretas).
          4. Envia os resultados FORA do lock (ver _resolver_rodada).

        Retorna None enquanto a rodada não foi resolvida, ou um dict com o vencedor.
        """
        with self._lock:
            sala = self.salas.get(codigo_sala)
            if not sala:
                raise ValueError(f"Sala {codigo_sala} não existe.")

            estado_rodada = self.rodadas_por_sala.get(codigo_sala)
            if estado_rodada is None:
                return None

            if estado_rodada.get("concluida"):
                return None

            # Partida em espera (alguém caiu): ninguém responde até ela voltar.
            if estado_rodada.get("pausada"):
                return None

            # Ignorar resposta de uma rodada que não é a atual.
            # Sem isso, uma resposta atrasada da rodada anterior (por latência de
            # rede) seria contada na rodada nova — o jogador "responderia" a
            # pergunta atual sem tê-la visto, roubando a vitória da rodada.
            # rodada_id pode vir como str ou int; comparamos de forma tolerante.
            rodada_corrente = estado_rodada.get("rodada_id")
            if rodada_corrente is not None and rodada_id is not None:
                try:
                    if int(rodada_id) != int(rodada_corrente):
                        return None
                except (TypeError, ValueError):
                    pass

            # Ignorar resposta duplicada do mesmo jogador
            if id_jogador in estado_rodada["respostas"]:
                return None

            # Resposta chegou depois do tempo limite: não conta, e a rodada
            # termina como num timeout normal (quem já tinha acertado pontua).
            expirou = time.time() - estado_rodada["inicio"] > self.tempo_limite_rodada

            if not expirou:
                # Registrar resposta com o horário de chegada
                estado_rodada["respostas"][id_jogador] = {
                    "resposta": str(resposta).strip().upper(),
                    "tempo": time.time(),
                }

                # Ainda falta alguém responder: espera (ou o timer da rodada).
                if len(estado_rodada["respostas"]) < len(sala["jogadores"]):
                    return None

                # Todos responderam: vence quem acertou primeiro.
                estado_rodada["concluida"] = True
                self._cancelar_timer_timeout(codigo_sala)
                vencedor = self._vencedor_pelas_respostas(codigo_sala)
                estado = self.estado_por_sala.get(codigo_sala)
                if estado and vencedor:
                    estado.registrarResultadoRodada(vencedor)

        if expirou:
            self._cancelar_timer_timeout(codigo_sala)
            return self._timeout_rodada(codigo_sala)

        # _resolver_rodada é chamado FORA do lock para evitar deadlock
        # ao fazer sendall enquanto outra thread aguarda o lock
        self._resolver_rodada(codigo_sala, vencedor=vencedor)
        return {"vencedor": vencedor or "nenhum"}

    # [Origem: IA]
    def _resolver_rodada(self, codigo_sala: str, vencedor: str | None):
        """
        Atualiza o EstadoJogo, envia FIM_RODADA + ATUALIZAR_BARRA,
        e decide se o jogo acabou (FIM_JOGO) ou avança (PERGUNTA).
        """
        estado = self.estado_por_sala.get(codigo_sala)
        partida = self.partidas_ativas.get(codigo_sala, {})
        rodada_corrente = partida.get("rodada", 1)

        pergunta = self.perguntas_rodada.get(codigo_sala, {})
        resposta_correta = pergunta.get("resposta_correta", "")

        # Envia FIM_RODADA com a resposta correta (só revelada depois que a
        # rodada acabou) e o apelido do vencedor, para o cliente mostrar o resultado.
        self.transmitir_para_sala(
            codigo_sala,
            TipoMensagem.FIM_RODADA,
            {
                "vencedor": vencedor or "nenhum",
                "apelido_vencedor": self.apelidos.get(vencedor, vencedor) if vencedor else None,
                "resposta_correta": resposta_correta,
                "rodada": rodada_corrente,
                "codigo_sala": codigo_sala,
            },
        )

        # Envia ATUALIZAR_BARRA com placar e apelidos
        posicao = estado.posicao_barra if estado else 0
        pontuacao = estado.pontuacao_jogadores.copy() if estado else {}
        apelidos = {jid: self.apelidos.get(jid, jid) for jid in pontuacao}
        self.transmitir_para_sala(
            codigo_sala,
            TipoMensagem.ATUALIZAR_BARRA,
            {"posicao": posicao, "pontuacao": pontuacao, "apelidos": apelidos},
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

        # Espera pausa_entre_rodadas (2 s) antes da próxima pergunta, para os
        # jogadores verem na tela qual era a resposta correta.
        timer = threading.Timer(
            self.pausa_entre_rodadas, self._iniciar_proxima_rodada, args=(codigo_sala,)
        )
        timer.daemon = True
        timer.start()

    # [Origem: IA]
    def _iniciar_proxima_rodada(self, codigo_sala: str):
        with self._lock:
            sala = self.salas.get(codigo_sala)
            if not sala:
                return

            estado = self.estado_por_sala.get(codigo_sala)
            if not estado or estado.vencedor:
                return

            # Alguém caiu durante a pausa entre rodadas: a próxima pergunta só
            # sai quando todos voltarem (ver _retomar_partida).
            if self._sala_tem_ausentes(codigo_sala):
                sala["proxima_pendente"] = True
                return

            partida = self.partidas_ativas.get(codigo_sala)
            if partida:
                partida["rodada"] = estado.rodada_atual
            sala["rodada_atual"] = estado.rodada_atual

            pergunta = self.selecionar_pergunta_para_sala(codigo_sala)
            payload = self._payload_pergunta(codigo_sala, pergunta, estado.rodada_atual)
            self.enviar_pergunta_para_sala(codigo_sala, payload)

        self._agendar_timeout_rodada(codigo_sala)

    # [Origem: IA]
    def _payload_pergunta(self, codigo_sala: str, pergunta: dict, rodada_id: int) -> dict:
        """
        Monta o conteúdo da mensagem PERGUNTA. NÃO inclui resposta_correta
        (anti-trapaça); leva nomes e placar para a tela ficar atualizada.
        """
        apelidos, pontuacao, posicao = self._apelidos_e_placar_da_sala(codigo_sala)
        return {
            "rodada_id": rodada_id,
            "pergunta": pergunta["pergunta"],
            "opcoes": pergunta["opcoes"],
            "tempo_limite": self.tempo_limite_rodada,
            "apelidos": apelidos,
            "pontuacao": pontuacao,
            "posicao": posicao,
        }

    # [Origem: IA]
    def _enviar_fim_jogo(self, codigo_sala: str, vencedor: str, estado: EstadoJogo | None):
        pontuacao = estado.pontuacao_jogadores.copy() if estado else {}
        posicao = estado.posicao_barra if estado else 0
        apelidos = {jid: self.apelidos.get(jid, jid) for jid in pontuacao}
        self.transmitir_para_sala(
            codigo_sala,
            TipoMensagem.FIM_JOGO,
            {
                "vencedor": vencedor,
                "apelido_vencedor": self.apelidos.get(vencedor, vencedor) if vencedor and vencedor != "empate" else None,
                "pontuacao": pontuacao,
                "posicao": posicao,
                "apelidos": apelidos,
            },
        )
        # Limpa a sala na hora. Os sockets NÃO são fechados: os jogadores
        # continuam conectados e podem reentrar na fila ("Jogar novamente").
        # Uma nova partida só começa quando os DOIS reenviarem ENTRAR.
        with self._lock:
            self._limpar_sala(codigo_sala)
            # Tira da fila quaisquer jogadores dessa sala que tenham sobrado.
            self.fila_espera = [
                j for j in self.fila_espera
                if j not in [jid for jid in pontuacao]
            ]
        print(f"[SERVIDOR] Sala {codigo_sala} encerrada. Aguardando novos ENTRAR para nova partida.")

    # -----------------------------------------------------------------------
    # Timeout de rodada em background
    # -----------------------------------------------------------------------

    # [Origem: IA]
    def _agendar_timeout_rodada(self, codigo_sala: str):
        """
        Liga um cronômetro em outra thread (threading.Timer). Se a rodada não
        terminar antes, _timeout_rodada é chamado. O +0,5 s é uma folga para a
        resposta enviada no último segundo ainda chegar pela rede.
        """
        self._cancelar_timer_timeout(codigo_sala)
        timer = threading.Timer(
            self.tempo_limite_rodada + 0.5,
            self._timeout_rodada,
            args=(codigo_sala,),
        )
        timer.daemon = True
        timer.start()
        self._timers_timeout[codigo_sala] = timer

    # [Origem: IA]
    def _cancelar_timer_timeout(self, codigo_sala: str):
        timer = self._timers_timeout.pop(codigo_sala, None)
        if timer is not None:
            timer.cancel()

    # [Origem: IA]
    def _vencedor_pelas_respostas(self, codigo_sala: str) -> str | None:
        """
        Determina o vencedor a partir das respostas JÁ registradas na rodada.
        Vence quem acertou a resposta correta PRIMEIRO (menor timestamp).
        Retorna None se ninguém que respondeu acertou.
        """
        estado_rodada = self.rodadas_por_sala.get(codigo_sala, {})
        pergunta = self.perguntas_rodada.get(codigo_sala, {})
        resposta_correta = str(pergunta.get("resposta_correta", "")).strip().upper()

        respostas_certas = [
            jid for jid, dados in estado_rodada.get("respostas", {}).items()
            if dados.get("resposta") == resposta_correta
        ]
        if not respostas_certas:
            return None
        return min(
            respostas_certas,
            key=lambda jid: estado_rodada["respostas"][jid]["tempo"],
        )

    # [Origem: IA]
    def _timeout_rodada(self, codigo_sala: str):
        """
        Chamado quando o tempo da rodada esgota. Mesmo que nem todos tenham
        respondido, quem JÁ acertou deve pontuar — não zeramos a rodada.
        """
        with self._lock:
            estado_rodada = self.rodadas_por_sala.get(codigo_sala)
            if estado_rodada is None or estado_rodada.get("concluida"):
                return
            if estado_rodada.get("pausada"):
                return  # partida em espera: o tempo da rodada não corre
            estado_rodada["concluida"] = True

            # Determina o vencedor pelas respostas que chegaram até agora.
            vencedor = self._vencedor_pelas_respostas(codigo_sala)

            # Atualiza o estado do jogo com esse vencedor (se houver), dentro do lock.
            estado = self.estado_por_sala.get(codigo_sala)
            if estado and vencedor:
                estado.registrarResultadoRodada(vencedor)

        # Resolve fora do lock (envia FIM_RODADA/ATUALIZAR_BARRA/etc.).
        self._resolver_rodada(codigo_sala, vencedor=vencedor)
        return {"vencedor": vencedor or "nenhum"}

    # -----------------------------------------------------------------------
    # Rede — envio e recebimento
    # -----------------------------------------------------------------------

    # [Origem: IA]
    def _enviar_mensagem_socket(self, socket_cliente, tipo_mensagem: TipoMensagem, dados: dict) -> bool:
        """
        Monta a mensagem e envia com sendall (que garante mandar TODOS os bytes,
        ao contrário de send). Retorna False se o cliente já desconectou.
        """
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

    # [Origem: IA]
    def transmitir_para_sala(self, codigo_sala: str, tipo_mensagem: TipoMensagem, dados: dict):
        sala = self.salas.get(codigo_sala)
        if not sala:
            return
        for id_jogador in sala.get("jogadores", []):
            sock = self.jogadores_conectados.get(id_jogador)
            if sock is not None:
                self._enviar_mensagem_socket(sock, tipo_mensagem, dados)

    # [Origem: IA]
    def _obter_codigo_sala_do_jogador(self, id_jogador: str) -> str | None:
        for codigo_sala, sala in self.salas.items():
            if id_jogador in sala.get("jogadores", []):
                return codigo_sala
        return None

    # -----------------------------------------------------------------------
    # Parsing de buffer TCP
    # -----------------------------------------------------------------------

    # [Origem: IA]
    # [IA - base inicial] A ideia de acumular bytes num buffer e ler o
    # cabeçalho de tamanho veio da base inicial, também gerada com IA.
    def _processar_buffer_cliente(self, buffer: bytes):
        """
        Extrai TODAS as mensagens completas do buffer de uma vez.

        Por que precisa de buffer: TCP é um FLUXO de bytes, não de mensagens.
        Um recv() pode trazer meia mensagem, uma mensagem inteira ou várias
        grudadas. Por isso cada mensagem tem na frente 4 bytes com o seu
        tamanho: o servidor só processa quando todos os bytes chegaram.

        Retorna (lista_de_mensagens, resto_do_buffer). Trata dois formatos:
          - JSON puro concatenado (usado em testes e no canal de compatibilidade)
          - Framing com cabeçalho de 4 bytes (formato oficial TCP)

        Resiliência: se encontrar bytes irrecuperáveis (JSON inválido ou
        cabeçalho absurdo), descarta o mínimo necessário e segue em frente,
        em vez de travar a conexão para sempre.
        """
        mensagens = []

        while buffer:
            texto = buffer.lstrip()
            offset = len(buffer) - len(texto)

            # ── Formato JSON puro ────────────────────────────────────────
            if texto[:1] == b"{":
                try:
                    msg, pos = json.JSONDecoder().raw_decode(texto.decode("utf-8"))
                    mensagens.append(msg)
                    buffer = buffer[offset + pos:]
                    continue
                except (ValueError, UnicodeDecodeError):
                    # JSON ainda incompleto? Aguarda mais bytes.
                    # Se o buffer for grande e ainda inválido, é lixo: descarta 1 byte
                    # para evitar travar (o cliente reenvia mensagens válidas).
                    if len(buffer) > 65536:
                        buffer = buffer[1:]
                        continue
                    break

            # ── Formato com cabeçalho de 4 bytes ─────────────────────────
            if len(buffer) < 4:
                break  # cabeçalho incompleto — aguarda mais bytes

            tamanho = int.from_bytes(buffer[:4], byteorder="big", signed=False)
            if tamanho <= 0 or tamanho > TAMANHO_MAXIMO_MENSAGEM:
                # Cabeçalho inválido (0 ou absurdamente grande): descarta 1 byte
                # e tenta ressincronizar.
                buffer = buffer[1:]
                continue

            if len(buffer) < 4 + tamanho:
                break  # payload ainda não chegou por completo

            payload = buffer[4 : 4 + tamanho]
            buffer = buffer[4 + tamanho:]
            try:
                mensagens.append(decodificar_mensagem(payload))
            except Exception:
                # Payload malformado: já consumimos os bytes, então seguimos.
                pass

        return mensagens, buffer

    # [Origem: IA 66% · autoral 34%]
    def processar_mensagens_de_conexao(self, conexao):
        """
        Loop de recepção de uma conexão de cliente (roda em thread própria).

        Lê bytes do socket, acumula no buffer, extrai mensagens completas e
        despacha cada uma para processar_mensagem(). Ao encerrar (socket fechado
        ou erro), trata a desconexão notificando o adversário.
        """
        # [IA - base inicial] Buffer que acumula os bytes recebidos (ver também
        # "buffer += dados" abaixo); as mensagens são recortadas dele.
        buffer = b""
        while True:
            try:
                dados = conexao.recv(4096)
            except socket.timeout:
                # Timeout é normal; só encerra se o servidor foi desligado.
                if not self._servidor_ativo:
                    break
                continue
            except OSError:
                break

            if not dados:
                break  # socket fechado pelo cliente (EOF)

            buffer += dados
            # Extrai TODAS as mensagens completas do buffer numa passada só.
            mensagens, buffer = self._processar_buffer_cliente(buffer)
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

        # Conexão encerrada: identifica o jogador, notifica o adversário e limpa.
        self._tratar_desconexao_de_socket(conexao)

    # [Origem: IA]
    def _tratar_desconexao_de_socket(self, conexao):
        """
        Quando um socket cai:
          - fora de partida: só remove o jogador;
          - no meio da partida: a partida entra em ESPERA. A rodada é pausada,
            o adversário recebe DESCONEXAO (motivo "aguardando_reconexao") e
            começa um cronômetro de tempo_reconexao (30 s) só para quem caiu.
            Se ele voltar a tempo, a partida continua; senão, ela é encerrada.
        """
        with self._lock:
            id_desconectado = self.socket_para_jogador.pop(id(conexao), None)
            if id_desconectado is None:
                # Procura pelo socket no mapa de conectados
                for jid, sock in list(self.jogadores_conectados.items()):
                    if sock is conexao:
                        id_desconectado = jid
                        break

            if id_desconectado is None:
                return

            self.jogadores_conectados.pop(id_desconectado, None)
            self.fila_espera = [j for j in self.fila_espera if j != id_desconectado]
            print(f"[TCP] Cliente desconectado: {id_desconectado}")

            codigo_sala = self._obter_codigo_sala_do_jogador(id_desconectado)
            if codigo_sala is None:
                return
            if codigo_sala not in self.partidas_ativas:
                # Sala que ainda nem começou: não há partida para esperar.
                self._limpar_sala(codigo_sala)
                return

            self._pausar_rodada(codigo_sala)
            self._agendar_espera_reconexao(id_desconectado, codigo_sala)
            self._avisar_sala(codigo_sala, id_desconectado, {
                "id_jogador": id_desconectado,
                "apelido": self.apelidos.get(id_desconectado, id_desconectado),
                "codigo_sala": codigo_sala,
                "motivo": "aguardando_reconexao",
                "tempo_espera": self.tempo_reconexao,
            })
            print(f"[SERVIDOR] Partida em {codigo_sala} em espera: aguardando "
                  f"{id_desconectado} voltar ({self.tempo_reconexao}s)")

    # [Origem: IA]
    def _avisar_sala(self, codigo_sala: str, exceto: str | None, dados: dict):
        """Envia DESCONEXAO a todos os jogadores conectados da sala, menos `exceto`."""
        sala = self.salas.get(codigo_sala, {})
        for id_jogador in sala.get("jogadores", []):
            if id_jogador == exceto:
                continue
            sock = self.jogadores_conectados.get(id_jogador)
            if sock is not None:
                self._enviar_mensagem_socket(sock, TipoMensagem.DESCONEXAO, dados)

    # [Origem: IA]
    def _sala_tem_ausentes(self, codigo_sala: str) -> bool:
        return any(info["sala"] == codigo_sala for info in self._ausentes.values())

    # [Origem: IA]
    def _pausar_rodada(self, codigo_sala: str):
        """Para o cronômetro da rodada e bloqueia respostas até a partida voltar."""
        self._cancelar_timer_timeout(codigo_sala)
        estado_rodada = self.rodadas_por_sala.get(codigo_sala)
        if estado_rodada is not None and not estado_rodada.get("concluida"):
            estado_rodada["pausada"] = True

    # [Origem: IA]
    def _agendar_espera_reconexao(self, id_jogador: str, codigo_sala: str):
        """Liga o cronômetro de 30 s deste jogador. Cada ausente tem o seu."""
        anterior = self._ausentes.pop(id_jogador, None)
        if anterior is not None:
            anterior["timer"].cancel()
        timer = threading.Timer(
            self.tempo_reconexao, self._encerrar_por_ausencia, args=(id_jogador, codigo_sala)
        )
        timer.daemon = True
        self._ausentes[id_jogador] = {"timer": timer, "sala": codigo_sala, "inicio": time.time()}
        timer.start()

    # [Origem: IA]
    def _encerrar_por_ausencia(self, id_jogador: str, codigo_sala: str):
        """Os 30 s de um ausente acabaram: a partida é encerrada."""
        with self._lock:
            if self._ausentes.pop(id_jogador, None) is None:
                return  # ele voltou a tempo
            if codigo_sala not in self.salas:
                return
            self._avisar_sala(codigo_sala, id_jogador, {
                "id_jogador": id_jogador,
                "apelido": self.apelidos.get(id_jogador, id_jogador),
                "codigo_sala": codigo_sala,
                "motivo": "tempo_esgotado",
            })
            self._limpar_sala(codigo_sala)  # cancela também a espera dos outros ausentes
            print(f"[SERVIDOR] Partida em {codigo_sala} encerrada: {id_jogador} não voltou a tempo")

    # [Origem: IA]
    def _reconectar_jogador(self, id_jogador: str, apelido: str | None, socket_remetente):
        """
        Um jogador que caiu voltou (ENTRAR com o mesmo id): ele recupera o
        lugar na sala, o adversário é avisado e, se ninguém mais estiver
        ausente, a partida continua de onde parou.
        """
        info = self._ausentes.pop(id_jogador)
        info["timer"].cancel()
        codigo_sala = info["sala"]
        if socket_remetente is not None:
            self.jogadores_conectados[id_jogador] = socket_remetente
            self.socket_para_jogador[id(socket_remetente)] = id_jogador
        if apelido:
            self.apelidos[id_jogador] = apelido
        print(f"[SERVIDOR] {id_jogador} voltou para a partida em {codigo_sala}")

        if socket_remetente is not None:
            self._enviar_mensagem_socket(socket_remetente, TipoMensagem.BEM_VINDO, {
                "id_jogador": id_jogador,
                "apelido": self.apelidos[id_jogador],
                "em_partida": True,
                "reconectado": True,
                "codigo_sala": codigo_sala,
            })
        self._avisar_sala(codigo_sala, id_jogador, {
            "id_jogador": id_jogador,
            "apelido": self.apelidos[id_jogador],
            "codigo_sala": codigo_sala,
            "motivo": "reconectado",
        })

        if self._sala_tem_ausentes(codigo_sala):
            # O outro jogador também caiu: quem voltou fica sabendo quanto falta.
            for outro, outro_info in self._ausentes.items():
                if outro_info["sala"] == codigo_sala and socket_remetente is not None:
                    restante = self.tempo_reconexao - (time.time() - outro_info["inicio"])
                    self._enviar_mensagem_socket(socket_remetente, TipoMensagem.DESCONEXAO, {
                        "id_jogador": outro,
                        "apelido": self.apelidos.get(outro, outro),
                        "codigo_sala": codigo_sala,
                        "motivo": "aguardando_reconexao",
                        "tempo_espera": max(0, round(restante)),
                    })
        else:
            self._retomar_partida(codigo_sala)
        return self.salas.get(codigo_sala)

    # [Origem: IA]
    def _retomar_partida(self, codigo_sala: str):
        """
        Todos voltaram. Se a espera começou no meio de uma pergunta, ela é
        reenviada com o tempo cheio e sem as respostas antigas. Se começou na
        pausa entre rodadas, a próxima pergunta é enviada agora.
        """
        sala = self.salas.get(codigo_sala)
        if not sala:
            return
        if sala.pop("proxima_pendente", False):
            self._iniciar_proxima_rodada(codigo_sala)
            return
        estado_rodada = self.rodadas_por_sala.get(codigo_sala)
        if not estado_rodada or not estado_rodada.get("pausada"):
            return  # a rodada já tinha acabado; o timer da próxima segue normal
        estado_rodada.update(pausada=False, respostas={}, inicio=time.time())
        pergunta = self.perguntas_rodada.get(codigo_sala, {})
        payload = self._payload_pergunta(codigo_sala, pergunta, estado_rodada["rodada_id"])
        self.enviar_pergunta_para_sala(codigo_sala, payload)
        self._agendar_timeout_rodada(codigo_sala)

    # [Origem: autoral 50% · IA 50%]
    def escutar_cliente(self, conexao):
        self.processar_mensagens_de_conexao(conexao)

    # [Origem: autoral 50% · IA 50%]
    def aceitar_conexoes(self):
        """
        Loop do socket TCP "de escuta": accept() devolve um socket NOVO para
        cada cliente que conecta. Cada cliente ganha sua própria thread, assim
        o servidor atende os dois jogadores ao mesmo tempo.
        """
        while self._servidor_ativo:
            try:
                conexao, endereco = self.socket_tcp.accept()
                print(f"[TCP] Nova conexão de {endereco}")
            except socket.timeout:
                continue
            except OSError:
                break
            # Ativa keepalive TCP na conexão aceita: o SO passa a sondar a outra
            # ponta periodicamente e detecta conexões "mortas" (half-open) mesmo
            # quando nenhum dado está sendo trocado.
            self._ativar_keepalive(conexao)
            # Timeout de leitura: evita que uma conexão parada (half-open ou
            # cliente travado) prenda a thread do servidor indefinidamente.
            self._ativar_timeout_leitura(conexao)
            thread = threading.Thread(target=self.escutar_cliente, args=(conexao,), daemon=True)
            thread.start()

    # [Origem: autoral]
    @staticmethod
    def _ativar_timeout_leitura(sock, segundos: float = 60):
        """Define um timeout de recv() no socket, se suportado (sockets fake em testes não têm)."""
        try:
            sock.settimeout(segundos)
        except (OSError, AttributeError):
            pass

    # [Origem: IA]
    @staticmethod
    def _ativar_keepalive(sock):
        """Habilita SO_KEEPALIVE em um socket TCP, se suportado pela plataforma."""
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        except (OSError, AttributeError):
            pass  # Alguns ambientes/sockets fake não suportam; ignora.

    # -----------------------------------------------------------------------
    # UDP — ping/pong
    # -----------------------------------------------------------------------

    # [Origem: IA]
    def escutar_ping_udp(self):
        """
        Responde PING com PONG pelo UDP, para o cliente medir a latência.

        UDP não tem conexão: recvfrom() devolve os dados E o endereço de quem
        mandou, e sendto() responde para esse endereço. Cada datagrama chega
        inteiro (ou não chega), por isso aqui não é preciso buffer como no TCP.
        """
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
                # UDP transporta datagramas JSON puros (sem cabeçalho de tamanho).
                mensagem = json.loads(dados.decode("utf-8"))
            except Exception:
                continue

            if mensagem.get("tipo") != TipoMensagem.PING.value:
                continue
            # PONG também é enviado como datagrama JSON puro. Ecoamos o campo
            # "ts" que veio no PING para o cliente saber a qual PING este PONG
            # responde (e descartar PONGs atrasados de medições antigas).
            dados_pong = {"id_jogador": mensagem.get("id_jogador", "cliente")}
            if "ts" in mensagem:
                dados_pong["ts"] = mensagem["ts"]
            resposta = criar_mensagem(TipoMensagem.PONG, dados_pong)
            payload_pong = json.dumps(resposta, ensure_ascii=False).encode("utf-8")
            self.socket_udp.sendto(payload_pong, endereco)

    # -----------------------------------------------------------------------
    # Inicialização e encerramento
    # -----------------------------------------------------------------------

    # [Origem: IA]
    def iniciar_servidor_tcp(self):
        self._servidor_ativo = True
        # AF_INET = IPv4; SOCK_STREAM = TCP (fluxo confiável e ordenado).
        self.socket_tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # SO_REUSEADDR: permite reabrir o servidor na mesma porta logo após
        # fechá-lo (sem esperar o estado TIME_WAIT do SO expirar).
        self.socket_tcp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket_tcp.bind((self.host, self.porta_tcp))
        self.socket_tcp.listen()
        # Timeout curto no accept() para o loop poder checar se o servidor foi desligado.
        self.socket_tcp.settimeout(0.2)
        print(f"[TCP] Servidor ouvindo em {self.host}:{self.porta_tcp}")

    # [Origem: IA]
    def iniciar_servidor_udp(self):
        self._servidor_ativo = True
        # SOCK_DGRAM = UDP (datagramas independentes, sem garantia de entrega).
        self.socket_udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket_udp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket_udp.bind((self.host, self.porta_udp))
        self.socket_udp.settimeout(0.2)
        print(f"[UDP] Servidor ouvindo em {self.host}:{self.porta_udp}")

    # [Origem: IA 85% · autoral 15%]
    def fechar_servidor(self):
        self._servidor_ativo = False
        for codigo_sala in list(self._timers_timeout.keys()):
            self._cancelar_timer_timeout(codigo_sala)
        for info in list(self._ausentes.values()):
            info["timer"].cancel()
        self._ausentes.clear()
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

    # [Origem: IA]
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


if __name__ == "__main__":
    servidor = ServidorQuiz()
    servidor.iniciar_loop_principal()
