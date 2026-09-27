# [Origem: IA] Medido com git blame.
"""
Testes das melhorias de rede e de jogo:
  - Framing TCP robusto no cliente (rajada de mensagens)
  - PONG UDP sem cabeçalho
  - Anti-trapaça (id_jogador validado contra socket)
  - resposta_correta NÃO enviada ao cliente na PERGUNTA
  - FIM_RODADA com resposta_correta e apelido do vencedor
  - DESCONEXAO automática ao cair a conexão
  - Fim de jogo na última rodada (sem off-by-one)
  - Banco sem perguntas duplicadas
"""
import json

from src.client.client import ClienteQuiz
from src.common.banco_perguntas import BancoPerguntas
from src.common.game_logic import EstadoJogo
from src.common.protocol import TipoMensagem
from src.server.server import ServidorQuiz


# ---------------------------------------------------------------------------
# Framing TCP do cliente
# ---------------------------------------------------------------------------

def test_cliente_processa_rajada_de_mensagens_com_cabecalho():
    """Duas mensagens com cabeçalho de 4 bytes chegando no mesmo recv."""
    from src.common.protocol import codificar_mensagem

    m1 = codificar_mensagem({"tipo": "FIM_RODADA", "vencedor": "player-1", "rodada": 1})
    m2 = codificar_mensagem({"tipo": "PERGUNTA", "rodada_id": 2, "pergunta": "P2", "opcoes": ["A", "B"], "tempo_limite": 30})

    class SoqueteFake:
        def __init__(self):
            self._pacotes = [m1 + m2, b""]

        def recv(self, tamanho):
            return self._pacotes.pop(0) if self._pacotes else b""

    cliente = ClienteQuiz()
    cliente.socket_tcp = SoqueteFake()

    primeira = cliente.receber_mensagem()
    segunda = cliente.receber_mensagem()

    assert primeira["tipo"] == "FIM_RODADA"
    assert segunda["tipo"] == "PERGUNTA"
    assert segunda["rodada_id"] == 2


def test_cliente_processa_mensagem_fragmentada_em_dois_recv():
    """Uma mensagem com cabeçalho chega dividida em dois recv."""
    from src.common.protocol import codificar_mensagem

    completa = codificar_mensagem({"tipo": "PERGUNTA", "rodada_id": 5, "pergunta": "X", "opcoes": [], "tempo_limite": 30})
    meio = len(completa) // 2

    class SoqueteFake:
        def __init__(self):
            self._pacotes = [completa[:meio], completa[meio:], b""]

        def recv(self, tamanho):
            return self._pacotes.pop(0) if self._pacotes else b""

    cliente = ClienteQuiz()
    cliente.socket_tcp = SoqueteFake()

    msg = cliente.receber_mensagem()
    assert msg["tipo"] == "PERGUNTA"
    assert msg["rodada_id"] == 5


# ---------------------------------------------------------------------------
# Anti-trapaça
# ---------------------------------------------------------------------------

def test_servidor_rejeita_resposta_com_id_de_outro_jogador():
    """Um socket não pode responder usando o id_jogador do adversário."""
    class SoqueteFake:
        def __init__(self):
            self.enviadas = []

        def sendall(self, dados):
            self.enviadas.append(dados)

    servidor = ServidorQuiz()
    sock1 = SoqueteFake()
    sock2 = SoqueteFake()

    # Registra via processar_mensagem para popular socket_para_jogador
    servidor.processar_mensagem({"tipo": "ENTRAR", "id_jogador": "player-1", "apelido": "Alice"}, sock1)
    servidor.processar_mensagem({"tipo": "ENTRAR", "id_jogador": "player-2", "apelido": "Bob"}, sock2)

    pergunta = servidor.perguntas_rodada.get("sala-1", {})
    correta = pergunta.get("resposta_correta", "TCP")

    # sock1 (player-1) tenta responder COMO player-2 → deve ser rejeitado
    resultado = servidor.processar_mensagem(
        {"tipo": "RESPOSTA", "id_jogador": "player-2", "rodada_id": 1, "resposta": correta},
        sock1,
    )
    assert resultado is None

    # A resposta do player-2 ainda não foi registrada (a tentativa foi bloqueada)
    estado_rodada = servidor.rodadas_por_sala.get("sala-1", {})
    assert "player-2" not in estado_rodada.get("respostas", {})


# ---------------------------------------------------------------------------
# resposta_correta não vaza para o cliente na PERGUNTA
# ---------------------------------------------------------------------------

def test_pergunta_enviada_nao_contem_resposta_correta():
    class SoqueteFake:
        def __init__(self):
            self.mensagens = []

        def sendall(self, dados):
            self.mensagens.append(json.loads(dados.decode("utf-8")))

    servidor = ServidorQuiz()
    j1 = SoqueteFake()
    j2 = SoqueteFake()
    servidor.processar_mensagem({"tipo": "ENTRAR", "id_jogador": "player-1", "apelido": "Alice"}, j1)
    servidor.processar_mensagem({"tipo": "ENTRAR", "id_jogador": "player-2", "apelido": "Bob"}, j2)

    perguntas_recebidas = [m for m in j1.mensagens if m.get("tipo") == "PERGUNTA"]
    assert perguntas_recebidas, "Nenhuma PERGUNTA foi enviada"
    for p in perguntas_recebidas:
        assert "resposta_correta" not in p, "resposta_correta NÃO deveria ser enviada ao cliente"


# ---------------------------------------------------------------------------
# FIM_RODADA inclui resposta_correta e apelido do vencedor
# ---------------------------------------------------------------------------

def test_fim_rodada_inclui_resposta_correta_e_apelido():
    class SoqueteFake:
        def __init__(self):
            self.mensagens = []

        def sendall(self, dados):
            self.mensagens.append(json.loads(dados.decode("utf-8")))

    servidor = ServidorQuiz()
    j1 = SoqueteFake()
    j2 = SoqueteFake()
    servidor.processar_mensagem({"tipo": "ENTRAR", "id_jogador": "player-1", "apelido": "Alice"}, j1)
    servidor.processar_mensagem({"tipo": "ENTRAR", "id_jogador": "player-2", "apelido": "Bob"}, j2)

    pergunta = servidor.perguntas_rodada.get("sala-1", {})
    correta = pergunta.get("resposta_correta", "TCP")
    opcoes = pergunta.get("opcoes", [])
    errada = next((o for o in opcoes if o != correta), "UDP")

    servidor.processar_mensagem({"tipo": "RESPOSTA", "id_jogador": "player-1", "rodada_id": 1, "resposta": correta}, j1)
    servidor.processar_mensagem({"tipo": "RESPOSTA", "id_jogador": "player-2", "rodada_id": 1, "resposta": errada}, j2)

    fim_rodada = [m for m in j1.mensagens if m.get("tipo") == "FIM_RODADA"]
    assert fim_rodada, "Nenhum FIM_RODADA recebido"
    ultima = fim_rodada[-1]
    assert ultima["vencedor"] == "player-1"
    assert ultima["apelido_vencedor"] == "Alice"
    assert ultima["resposta_correta"] == correta


def test_atualizar_barra_inclui_apelidos():
    class SoqueteFake:
        def __init__(self):
            self.mensagens = []

        def sendall(self, dados):
            self.mensagens.append(json.loads(dados.decode("utf-8")))

    servidor = ServidorQuiz()
    j1 = SoqueteFake()
    j2 = SoqueteFake()
    servidor.processar_mensagem({"tipo": "ENTRAR", "id_jogador": "player-1", "apelido": "Alice"}, j1)
    servidor.processar_mensagem({"tipo": "ENTRAR", "id_jogador": "player-2", "apelido": "Bob"}, j2)

    pergunta = servidor.perguntas_rodada.get("sala-1", {})
    correta = pergunta.get("resposta_correta", "TCP")
    opcoes = pergunta.get("opcoes", [])
    errada = next((o for o in opcoes if o != correta), "UDP")

    servidor.processar_mensagem({"tipo": "RESPOSTA", "id_jogador": "player-1", "rodada_id": 1, "resposta": correta}, j1)
    servidor.processar_mensagem({"tipo": "RESPOSTA", "id_jogador": "player-2", "rodada_id": 1, "resposta": errada}, j2)

    atualizacoes = [m for m in j1.mensagens if m.get("tipo") == "ATUALIZAR_BARRA"]
    assert atualizacoes, "Nenhum ATUALIZAR_BARRA recebido"
    ultima = atualizacoes[-1]
    assert ultima["apelidos"]["player-1"] == "Alice"
    assert ultima["apelidos"]["player-2"] == "Bob"


# ---------------------------------------------------------------------------
# DESCONEXÃO automática
# ---------------------------------------------------------------------------

def test_servidor_notifica_adversario_ao_cair_conexao():
    class SoqueteFake:
        def __init__(self):
            self.mensagens = []

        def sendall(self, dados):
            self.mensagens.append(json.loads(dados.decode("utf-8")))

        def close(self):
            pass

    servidor = ServidorQuiz()
    j1 = SoqueteFake()
    j2 = SoqueteFake()
    servidor.processar_mensagem({"tipo": "ENTRAR", "id_jogador": "player-1", "apelido": "Alice"}, j1)
    servidor.processar_mensagem({"tipo": "ENTRAR", "id_jogador": "player-2", "apelido": "Bob"}, j2)

    # Simula a queda da conexão de player-1
    servidor._tratar_desconexao_de_socket(j1)

    desconexoes = [m for m in j2.mensagens if m.get("tipo") == "DESCONEXAO"]
    assert desconexoes, "player-2 deveria receber DESCONEXAO"
    assert desconexoes[-1]["id_jogador"] == "player-1"
    assert desconexoes[-1]["apelido"] == "Alice"
    # A sala foi limpa
    assert "sala-1" not in servidor.salas


# ---------------------------------------------------------------------------
# Fim de jogo na última rodada — sem off-by-one
# ---------------------------------------------------------------------------

def test_estado_jogo_termina_exatamente_na_ultima_rodada_por_barra():
    # vantagem alta impede knockout por diferença; testamos só o desempate no fim
    jogo = EstadoJogo(maximo_rodadas=10, vantagem_para_vencer=99)
    jogo.rodada_atual = 10
    # Jogador A com a corda do seu lado
    jogo.posicao_barra = 2
    vencedor = jogo.verificar_fim_de_jogo()
    assert vencedor == "player-1"


def test_estado_jogo_empate_desempata_por_pontos():
    jogo = EstadoJogo(maximo_rodadas=10, vantagem_para_vencer=99)
    jogo.rodada_atual = 10
    jogo.posicao_barra = 0
    jogo.pontuacao_jogadores = {"player-1": 4, "player-2": 6}
    vencedor = jogo.verificar_fim_de_jogo()
    assert vencedor == "player-2"


def test_estado_jogo_nao_termina_antes_da_ultima_rodada():
    jogo = EstadoJogo(maximo_rodadas=10, vantagem_para_vencer=99)
    jogo.rodada_atual = 5
    jogo.posicao_barra = 3
    assert jogo.verificar_fim_de_jogo() is None


# ---------------------------------------------------------------------------
# Banco sem duplicatas
# ---------------------------------------------------------------------------

def test_banco_nao_tem_perguntas_duplicadas():
    banco = BancoPerguntas()
    perguntas = [p["pergunta"] for p in banco.obter_perguntas()]
    assert len(perguntas) == len(set(perguntas)), "Há perguntas duplicadas no banco"


# ---------------------------------------------------------------------------
# BEM_VINDO (ACK de ENTRAR) com id definitivo
# ---------------------------------------------------------------------------

def test_servidor_envia_bem_vindo_com_id_definitivo():
    class SoqueteFake:
        def __init__(self):
            self.mensagens = []

        def sendall(self, dados):
            self.mensagens.append(json.loads(dados.decode("utf-8")))

    servidor = ServidorQuiz()
    sock = SoqueteFake()
    servidor.processar_mensagem({"tipo": "ENTRAR", "id_jogador": "player-1", "apelido": "Alice"}, sock)

    bem_vindos = [m for m in sock.mensagens if m.get("tipo") == "BEM_VINDO"]
    assert bem_vindos, "Servidor deveria enviar BEM_VINDO após ENTRAR"
    bv = bem_vindos[0]
    assert bv["id_jogador"] == "player-1"
    assert bv["apelido"] == "Alice"
    assert bv["em_partida"] is False  # sozinho, ainda aguardando


def test_servidor_renomeia_id_em_colisao_e_informa_no_bem_vindo():
    class SoqueteFake:
        def __init__(self):
            self.mensagens = []

        def sendall(self, dados):
            self.mensagens.append(json.loads(dados.decode("utf-8")))

    servidor = ServidorQuiz()
    s1, s2 = SoqueteFake(), SoqueteFake()
    # Dois jogadores usam o MESMO id "player" → o 2º deve ser renomeado
    servidor.processar_mensagem({"tipo": "ENTRAR", "id_jogador": "player", "apelido": "A"}, s1)
    servidor.processar_mensagem({"tipo": "ENTRAR", "id_jogador": "player", "apelido": "B"}, s2)

    bv1 = [m for m in s1.mensagens if m.get("tipo") == "BEM_VINDO"][0]
    bv2 = [m for m in s2.mensagens if m.get("tipo") == "BEM_VINDO"][0]
    assert bv1["id_jogador"] != bv2["id_jogador"], "IDs devem ser únicos após colisão"


def test_parser_servidor_descarta_cabecalho_absurdo_e_ressincroniza():
    """
    Um cabeçalho de 4 bytes com tamanho absurdo (lixo binário) não deve travar
    o parser: ele descarta bytes até ressincronizar e extrai a mensagem válida.
    """
    servidor = ServidorQuiz()
    from src.common.protocol import codificar_mensagem

    # 4 bytes que representam um tamanho gigantesco (lixo) + mensagem válida
    lixo = b"\xff\xff\xff\xff"
    valida = codificar_mensagem({"tipo": "ENTRAR", "id_jogador": "player-1", "apelido": "Alice"})

    mensagens, resto = servidor._processar_buffer_cliente(lixo + valida)
    tipos = [m.get("tipo") for m in mensagens]
    assert "ENTRAR" in tipos, "A mensagem válida deveria ser extraída após descartar o lixo"


def test_parser_servidor_extrai_rajada_com_cabecalho():
    """Duas mensagens com cabeçalho concatenadas devem ser ambas extraídas."""
    servidor = ServidorQuiz()
    from src.common.protocol import codificar_mensagem

    m1 = codificar_mensagem({"tipo": "ENTRAR", "id_jogador": "player-1", "apelido": "A"})
    m2 = codificar_mensagem({"tipo": "RESPOSTA", "id_jogador": "player-1", "rodada_id": 1, "resposta": "TCP"})

    mensagens, resto = servidor._processar_buffer_cliente(m1 + m2)
    tipos = [m.get("tipo") for m in mensagens]
    assert tipos == ["ENTRAR", "RESPOSTA"]
    assert resto == b""


# ---------------------------------------------------------------------------
# Reentrada na mesma conexão ("Jogar novamente" sem reconectar)
# ---------------------------------------------------------------------------

def test_reentrada_na_mesma_conexao_reusa_id():
    """
    Um segundo ENTRAR na MESMA conexão (mesmo socket) deve reusar o MESMO
    id_jogador, sem renomear para player-1-1. É o que permite "jogar novamente"
    sem reconectar.
    """
    class SoqueteFake:
        def __init__(self):
            self.mensagens = []
        def sendall(self, dados):
            self.mensagens.append(json.loads(dados.decode("utf-8")))
        def close(self):
            pass

    servidor = ServidorQuiz()
    sock = SoqueteFake()

    # Primeiro ENTRAR
    servidor.processar_mensagem({"tipo": "ENTRAR", "id_jogador": "player-1", "apelido": "Alice"}, sock)
    id_apos_primeiro = servidor.socket_para_jogador[id(sock)]

    # Segundo ENTRAR na MESMA conexão (jogar novamente)
    servidor.processar_mensagem({"tipo": "ENTRAR", "id_jogador": "player-1", "apelido": "Alice"}, sock)
    id_apos_segundo = servidor.socket_para_jogador[id(sock)]

    # O id deve ser o MESMO (reentrada), não renomeado
    assert id_apos_primeiro == id_apos_segundo == "player-1"
    # Só existe uma entrada para esse jogador nos conectados
    assert list(servidor.jogadores_conectados.keys()).count("player-1") == 1


def test_reentrada_atualiza_apelido():
    """Se o jogador trocar o nome ao jogar novamente, o servidor atualiza o apelido."""
    class SoqueteFake:
        def __init__(self):
            self.mensagens = []
        def sendall(self, dados):
            self.mensagens.append(json.loads(dados.decode("utf-8")))
        def close(self):
            pass

    servidor = ServidorQuiz()
    sock = SoqueteFake()

    servidor.processar_mensagem({"tipo": "ENTRAR", "id_jogador": "player-1", "apelido": "Alice"}, sock)
    servidor.processar_mensagem({"tipo": "ENTRAR", "id_jogador": "player-1", "apelido": "Alice Nova"}, sock)

    jid = servidor.socket_para_jogador[id(sock)]
    assert servidor.apelidos[jid] == "Alice Nova"


# ---------------------------------------------------------------------------
# PERGUNTA da 1ª rodada já traz apelidos (nomes aparecem desde o início)
# ---------------------------------------------------------------------------

def test_primeira_pergunta_inclui_apelidos():
    """
    A PERGUNTA (inclusive a da 1ª rodada) deve carregar os apelidos dos dois
    jogadores, para o cliente exibir os nomes na barra desde o começo — sem
    esperar a primeira ATUALIZAR_BARRA.
    """
    class SoqueteFake:
        def __init__(self):
            self.mensagens = []
        def sendall(self, dados):
            self.mensagens.append(json.loads(dados.decode("utf-8")))
        def close(self):
            pass

    servidor = ServidorQuiz()
    j1, j2 = SoqueteFake(), SoqueteFake()
    servidor.processar_mensagem({"tipo": "ENTRAR", "id_jogador": "player-1", "apelido": "Alice"}, j1)
    servidor.processar_mensagem({"tipo": "ENTRAR", "id_jogador": "player-2", "apelido": "Bob"}, j2)

    perguntas = [m for m in j1.mensagens if m.get("tipo") == "PERGUNTA"]
    assert perguntas, "Nenhuma PERGUNTA enviada"
    primeira = perguntas[0]
    assert "apelidos" in primeira, "PERGUNTA deveria incluir apelidos já na 1ª rodada"
    assert primeira["apelidos"].get("player-1") == "Alice"
    assert primeira["apelidos"].get("player-2") == "Bob"
    # Continua sem vazar a resposta correta
    assert "resposta_correta" not in primeira


# ---------------------------------------------------------------------------
# Rematch: reentrar sozinho NÃO inicia partida (evita "sala fantasma")
# ---------------------------------------------------------------------------

def test_reentrar_sozinho_nao_inicia_partida():
    """
    Após o fim de uma partida, se apenas UM jogador clicar "jogar novamente"
    (reenviar ENTRAR), o jogo NÃO pode começar — deve esperar o segundo.
    """
    class SoqueteFake:
        def __init__(self):
            self.mensagens = []
        def sendall(self, dados):
            self.mensagens.append(json.loads(dados.decode("utf-8")))
        def close(self):
            pass

    servidor = ServidorQuiz()
    s1, s2 = SoqueteFake(), SoqueteFake()
    # Primeira partida
    servidor.processar_mensagem({"tipo": "ENTRAR", "id_jogador": "player-1", "apelido": "Alice"}, s1)
    servidor.processar_mensagem({"tipo": "ENTRAR", "id_jogador": "player-2", "apelido": "Bob"}, s2)
    assert "sala-1" in servidor.salas

    # Encerra a partida (simula fim de jogo limpando a sala)
    estado = servidor.estado_por_sala["sala-1"]
    servidor._enviar_fim_jogo("sala-1", "player-1", estado)
    assert "sala-1" not in servidor.salas, "sala deve ser limpa imediatamente ao fim do jogo"

    # Só player-1 clica "jogar novamente"
    s1.mensagens.clear()
    servidor.processar_mensagem({"tipo": "ENTRAR", "id_jogador": "player-1", "apelido": "Alice"}, s1)

    # NÃO deve haver partida ativa (aguardando o segundo jogador)
    assert "sala-1" not in servidor.salas or len(servidor.salas["sala-1"]["jogadores"]) < 2
    # O BEM_VINDO recebido deve indicar que NÃO está em partida
    bem_vindos = [m for m in s1.mensagens if m.get("tipo") == "BEM_VINDO"]
    assert bem_vindos and bem_vindos[-1]["em_partida"] is False


def test_rematch_com_os_dois_inicia_nova_partida():
    """Quando os DOIS reentram, uma nova partida começa normalmente."""
    class SoqueteFake:
        def __init__(self):
            self.mensagens = []
        def sendall(self, dados):
            self.mensagens.append(json.loads(dados.decode("utf-8")))
        def close(self):
            pass

    servidor = ServidorQuiz()
    s1, s2 = SoqueteFake(), SoqueteFake()
    servidor.processar_mensagem({"tipo": "ENTRAR", "id_jogador": "player-1", "apelido": "Alice"}, s1)
    servidor.processar_mensagem({"tipo": "ENTRAR", "id_jogador": "player-2", "apelido": "Bob"}, s2)

    estado = servidor.estado_por_sala["sala-1"]
    servidor._enviar_fim_jogo("sala-1", "player-1", estado)

    # Os dois reentram
    servidor.processar_mensagem({"tipo": "ENTRAR", "id_jogador": "player-1", "apelido": "Alice"}, s1)
    servidor.processar_mensagem({"tipo": "ENTRAR", "id_jogador": "player-2", "apelido": "Bob"}, s2)

    assert "sala-1" in servidor.salas
    assert set(servidor.salas["sala-1"]["jogadores"]) == {"player-1", "player-2"}
