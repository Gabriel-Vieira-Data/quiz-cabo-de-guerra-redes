from src.server.server import ServidorQuiz


def test_servidor_organiza_fila_de_espera_e_aceita_sala_com_dois_jogadores():
    servidor = ServidorQuiz()

    servidor.adicionar_jogador_espera("player-1")
    servidor.adicionar_jogador_espera("player-2")

    sala = servidor.criar_sala_para_espera()

    assert sala["codigo"] == "sala-1"
    assert sala["jogadores"] == ["player-1", "player-2"]
    assert servidor.fila_espera == []


def test_servidor_cria_sala_automaticamente_ao_registrar_segundo_jogador():
    servidor = ServidorQuiz()

    servidor.registrar_jogador("player-1", object())
    sala = servidor.registrar_jogador("player-2", object())

    assert sala is not None
    assert sala["codigo"] == "sala-1"
    assert sala["jogadores"] == ["player-1", "player-2"]
    assert servidor.fila_espera == []


def test_servidor_permite_apenas_uma_sala_ativa_por_vez():
    servidor = ServidorQuiz()

    servidor.registrar_jogador("player-1", object())
    servidor.registrar_jogador("player-2", object())

    servidor.adicionar_jogador_espera("player-3")
    servidor.adicionar_jogador_espera("player-4")
    sala_nova = servidor.criar_sala_para_espera()

    assert sala_nova is not None
    assert len(servidor.salas) == 1
    assert sala_nova["jogadores"] == ["player-3", "player-4"]


def test_servidor_gera_id_unico_quando_o_mesmo_identificador_é_usado_duas_vezes():
    servidor = ServidorQuiz()

    servidor.registrar_jogador("player-1", object())
    sala = servidor.registrar_jogador("player-1", object())

    assert sala is not None
    assert sala["jogadores"] == ["player-1", "player-2"]
    assert servidor.fila_espera == []


def test_servidor_envia_pergunta_para_todos_os_jogadores_da_sala():
    class SoqueteFake:
        def __init__(self):
            self.ultima_mensagem = None

        def sendall(self, dados):
            self.ultima_mensagem = __import__("json").loads(dados.decode("utf-8"))

    servidor = ServidorQuiz()
    jogador_1 = SoqueteFake()
    jogador_2 = SoqueteFake()

    servidor.registrar_jogador("player-1", jogador_1)
    servidor.registrar_jogador("player-2", jogador_2)

    pergunta = {
        "rodada_id": 1,
        "pergunta": "Qual protocolo é orientado à conexão?",
        "opcoes": ["TCP", "UDP", "ICMP", "ARP"],
        "tempo_limite": 10,
    }
    servidor.enviar_pergunta_para_sala("sala-1", pergunta)

    assert jogador_1.ultima_mensagem["tipo"] == "PERGUNTA"
    assert jogador_2.ultima_mensagem["tipo"] == "PERGUNTA"
    assert jogador_1.ultima_mensagem["pergunta"] == pergunta["pergunta"]


def test_servidor_avisa_quando_um_jogador_desconecta_da_sala():
    servidor = ServidorQuiz()
    servidor.registrar_jogador("player-1", object())
    servidor.registrar_jogador("player-2", object())

    servidor.remover_jogador("player-2")

    assert "player-2" not in servidor.salas["sala-1"]["jogadores"]


def test_servidor_registra_respostas_por_sala_e_resolve_rodada_quando_os_dois_jogadores_responderam():
    servidor = ServidorQuiz()
    servidor.registrar_jogador("player-1", object())
    sala = servidor.registrar_jogador("player-2", object())

    assert sala is not None

    resultado_1 = servidor.registrar_resposta_jogador("sala-1", 1, "player-1", "TCP")
    assert resultado_1 is None

    resultado_2 = servidor.registrar_resposta_jogador("sala-1", 1, "player-2", "UDP")
    assert resultado_2["vencedor"] == "player-1"
    assert servidor.estado_jogo["pontuacao"]["player-1"] == 1


def test_servidor_lida_com_multiplas_mensagens_na_mesma_conexao():
    class SoqueteFake:
        def __init__(self):
            self.mensagens = [
                __import__("json").dumps({"tipo": "ENTRAR", "id_jogador": "player-1", "apelido": "Alice"}).encode("utf-8"),
                __import__("json").dumps({"tipo": "RESPOSTA", "id_jogador": "player-1", "rodada_id": 1, "resposta": "TCP"}).encode("utf-8"),
                b"",
            ]
            self.enviadas = []

        def recv(self, tamanho):
            if not self.mensagens:
                return b""
            return self.mensagens.pop(0)

        def sendall(self, dados):
            self.enviadas.append(__import__("json").loads(dados.decode("utf-8")))

    servidor = ServidorQuiz()
    soquete = SoqueteFake()

    servidor.processar_mensagens_de_conexao(soquete)

    assert "player-1" in servidor.jogadores_conectados
    assert servidor.salas["sala-1"]["jogadores"] == ["player-1"] or servidor.salas["sala-1"]["jogadores"] == ["player-1", "player-2"]


def test_servidor_avanca_para_proxima_pergunta_apos_as_duas_respostas():
    class SoqueteFake:
        def __init__(self):
            self.mensagens = []

        def sendall(self, dados):
            self.mensagens.append(__import__("json").loads(dados.decode("utf-8")))

    servidor = ServidorQuiz()
    jogador_1 = SoqueteFake()
    jogador_2 = SoqueteFake()

    servidor.registrar_jogador("player-1", jogador_1)
    servidor.registrar_jogador("player-2", jogador_2)

    servidor.registrar_resposta_jogador("sala-1", 1, "player-1", "TCP")
    resultado = servidor.registrar_resposta_jogador("sala-1", 1, "player-2", "UDP")

    assert resultado is not None
    assert len(jogador_1.mensagens) >= 2
    assert len(jogador_2.mensagens) >= 2
    assert jogador_1.mensagens[-1]["tipo"] == "PERGUNTA"
    assert jogador_2.mensagens[-1]["tipo"] == "PERGUNTA"


def test_servidor_avanca_para_proxima_pergunta_quando_ninguem_acerta():
    class SoqueteFake:
        def __init__(self):
            self.mensagens = []

        def sendall(self, dados):
            self.mensagens.append(__import__("json").loads(dados.decode("utf-8")))

    servidor = ServidorQuiz()
    jogador_1 = SoqueteFake()
    jogador_2 = SoqueteFake()

    servidor.registrar_jogador("player-1", jogador_1)
    servidor.registrar_jogador("player-2", jogador_2)

    servidor.registrar_resposta_jogador("sala-1", 1, "player-1", "UDP")
    resultado = servidor.registrar_resposta_jogador("sala-1", 1, "player-2", "ICMP")

    assert resultado is not None
    assert resultado["vencedor"] == "nenhum"
    assert len(jogador_1.mensagens) >= 2
    assert len(jogador_2.mensagens) >= 2
    assert jogador_1.mensagens[-1]["tipo"] == "PERGUNTA"
    assert jogador_2.mensagens[-1]["tipo"] == "PERGUNTA"


def test_servidor_espera_os_dois_jogadores_antes_de_finalizar_rodada_mesmo_que_um_acerte():
    class SoqueteFake:
        def __init__(self):
            self.mensagens = []

        def sendall(self, dados):
            self.mensagens.append(__import__("json").loads(dados.decode("utf-8")))

    servidor = ServidorQuiz()
    jogador_1 = SoqueteFake()
    jogador_2 = SoqueteFake()

    servidor.registrar_jogador("player-1", jogador_1)
    servidor.registrar_jogador("player-2", jogador_2)

    primeiro = servidor.registrar_resposta_jogador("sala-1", 1, "player-1", "TCP")
    assert primeiro is None

    segundo = servidor.registrar_resposta_jogador("sala-1", 1, "player-2", "UDP")
    assert segundo is not None
    assert segundo["vencedor"] == "player-1"


def test_servidor_processa_mensagem_tcp_de_entrada_e_resposta_do_cliente():
    servidor = ServidorQuiz()

    resposta_entrada_1 = servidor.processar_mensagem({
        "tipo": "ENTRAR",
        "id_jogador": "player-1",
        "apelido": "Alice",
    }, None)
    assert resposta_entrada_1 is None

    resposta_entrada_2 = servidor.processar_mensagem({
        "tipo": "ENTRAR",
        "id_jogador": "player-2",
        "apelido": "Bob",
    }, None)
    assert resposta_entrada_2["codigo"] == "sala-1"
    assert resposta_entrada_2["jogadores"] == ["player-1", "player-2"]

    resultado = servidor.processar_mensagem({
        "tipo": "RESPOSTA",
        "id_jogador": "player-1",
        "rodada_id": 1,
        "resposta": "TCP",
    }, None)
    assert resultado is None

    resultado_final = servidor.processar_mensagem({
        "tipo": "RESPOSTA",
        "id_jogador": "player-2",
        "rodada_id": 1,
        "resposta": "UDP",
    }, None)
    assert resultado_final["vencedor"] == "player-1"


def test_servidor_nao_ler_a_mesma_conexao_duas_vezes_antes_da_partida_iniciar():
    import socket
    import threading

    class ConexaoFake:
        def __init__(self):
            self.chamadas = 0
            self.encaixe = __import__("json").dumps({
                "tipo": "ENTRAR",
                "id_jogador": "player-1",
                "apelido": "Alice",
            }).encode("utf-8")

        def recv(self, tamanho):
            self.chamadas += 1
            if self.chamadas == 1:
                return self.encaixe
            raise socket.timeout

        def sendall(self, dados):
            return None

        def close(self):
            return None

    class SoqueteTcpFake:
        def __init__(self, conexao):
            self.conexao = conexao
            self._aceite = [(conexao, ("127.0.0.1", 5000))]

        def setsockopt(self, *args, **kwargs):
            return None

        def bind(self, *args, **kwargs):
            return None

        def listen(self, *args, **kwargs):
            return None

        def accept(self):
            if self._aceite:
                return self._aceite.pop(0)
            raise socket.timeout

        def settimeout(self, valor):
            return None

    servidor = ServidorQuiz()
    conexao = ConexaoFake()
    servidor.socket_tcp = SoqueteTcpFake(conexao)
    servidor._servidor_ativo = True

    thread_aceite = threading.Thread(target=servidor.aceitar_conexoes, daemon=True)
    thread_aceite.start()
    thread_aceite.join(timeout=0.5)
    servidor._servidor_ativo = False

    assert conexao.chamadas == 1


def test_servidor_escuta_em_endereco_externo_por_padrao_e_cliente_usa_udp_efemero():
    servidor = ServidorQuiz()
    assert servidor.host == "0.0.0.0"

    cliente = ClienteQuiz()
    assert cliente.host == "127.0.0.1"
