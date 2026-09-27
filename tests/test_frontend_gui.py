# [Origem: autoral 77% · IA 23%] Medido com git blame (ver USO_DE_IA.md).
import json

from src.client.client import ClienteQuiz
from src.client.gui import extrair_detalhes_desconexao, extrair_detalhes_pergunta


def test_cliente_decodifica_mensagens_json_concatenadas_em_um_bloco_de_rede():
    class SoqueteFake:
        def __init__(self):
            self._pacotes = [
                (
                    b'{"tipo":"FIM_RODADA","vencedor":"nenhum","rodada":1}'
                    b'{"tipo":"PERGUNTA","rodada_id":2,"pergunta":"Pergunta 2","opcoes":["A","B"],"tempo_limite":30}'
                )
            ]
            self.chamadas = 0

        def recv(self, tamanho):
            self.chamadas += 1
            if not self._pacotes:
                return b''
            return self._pacotes.pop(0)

    cliente = ClienteQuiz()
    cliente.socket_tcp = SoqueteFake()

    primeira = cliente.receber_mensagem()
    segunda = cliente.receber_mensagem()

    assert primeira["tipo"] == "FIM_RODADA"
    assert segunda["tipo"] == "PERGUNTA"
    assert segunda["rodada_id"] == 2
    assert cliente.socket_tcp.chamadas == 1


def test_extrair_detalhes_pergunta_retorna_dados_da_rodada():
    mensagem = {
        "tipo": "PERGUNTA",
        "rodada_id": 3,
        "pergunta": "Qual protocolo é orientado à conexão?",
        "opcoes": ["TCP", "UDP", "ICMP", "ARP"],
        "tempo_limite": 30,
    }

    dados = extrair_detalhes_pergunta(mensagem)

    assert dados["rodada_id"] == 3
    assert dados["pergunta"] == "Qual protocolo é orientado à conexão?"
    assert len(dados["opcoes"]) == 4
    assert dados["tempo_limite"] == 30


def test_extrair_detalhes_desconexao_retorna_informacoes_do_jogador():
    mensagem = {
        "tipo": "DESCONEXAO",
        "id_jogador": "player-2",
        "codigo_sala": "sala-1",
    }

    dados = extrair_detalhes_desconexao(mensagem)

    assert dados["id_jogador"] == "player-2"
    assert dados["codigo_sala"] == "sala-1"


def test_gui_bloqueia_alteracao_de_resposta_apos_envio():
    """
    Após enviar a resposta, os botões de opção e o botão Enviar devem ser
    desabilitados, e a flag resposta_enviada deve virar True (impede reenvio).
    Reflete a GUI atual, que usa botões de opção individuais (_botoes_opcao).
    """
    class BotaoFake:
        def __init__(self, valor=None):
            self.state = "normal"
            self.kwargs = {}
            self._opcao_valor = valor
        def config(self, **kwargs):
            self.state = kwargs.get("state", self.state)
            self.kwargs.update(kwargs)
        def __getitem__(self, chave):
            return self.state if chave == "state" else self.kwargs.get(chave)

    class ClienteFake:
        def __init__(self):
            self.envios = []
        def enviar_resposta(self, *args):
            self.envios.append(args)

    app = object.__new__(__import__("src.client.gui", fromlist=["JanelaQuiz"]).JanelaQuiz)
    app.pergunta_atual = {
        "rodada_id": 1,
        "pergunta": "Pergunta 1",
        "opcoes": ["TCP", "UDP"],
        "tempo_limite": 30,
    }
    app.id_jogador = "player-1"
    app.resposta_enviada = False
    app._botoes_opcao = [BotaoFake("TCP"), BotaoFake("UDP")]
    app.botao_enviar = BotaoFake()
    app.rotulo_status = type("LabelFake", (), {"config": lambda self, **kwargs: None})()
    app.opcoes_var = type("VarFake", (), {"get": lambda self: "TCP", "set": lambda self, value: None})()
    app.cliente = ClienteFake()

    app.enviar_resposta()

    # A resposta foi enviada ao servidor
    assert app.cliente.envios == [("player-1", 1, "TCP")]
    # A flag impede reenvio
    assert app.resposta_enviada is True
    # Os controles foram desabilitados
    assert all(b.state == "disabled" for b in app._botoes_opcao)
    assert app.botao_enviar.state == "disabled"

    # Um segundo envio não deve reenviar (resposta_enviada já é True)
    app.enviar_resposta()
    assert len(app.cliente.envios) == 1
