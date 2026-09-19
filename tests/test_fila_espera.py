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
