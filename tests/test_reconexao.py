# [Origem: IA] Medido com git blame (ver USO_DE_IA.md).
"""
Espera por reconexão e pausa entre rodadas:
  - quem cai no meio da partida tem 30 s para voltar (a partida fica em espera);
  - se voltar, a partida continua; se não, ela é encerrada;
  - cada jogador ausente tem o seu próprio cronômetro;
  - depois de cada pergunta há uma pausa de 2 s antes da próxima.
"""
import json
import time

from src.server.server import ServidorQuiz


class SoqueteFake:
    def __init__(self):
        self.mensagens = []

    def sendall(self, dados):
        self.mensagens.append(json.loads(dados.decode("utf-8")))

    def close(self):
        pass

    def tipos(self):
        return [m["tipo"] for m in self.mensagens]

    def desconexoes(self):
        return [m for m in self.mensagens if m["tipo"] == "DESCONEXAO"]


def _entrar(servidor, id_jogador, apelido, sock):
    return servidor.processar_mensagem(
        {"tipo": "ENTRAR", "id_jogador": id_jogador, "apelido": apelido}, sock
    )


def _partida(tempo_reconexao=30):
    servidor = ServidorQuiz()
    servidor.tempo_reconexao = tempo_reconexao
    s1, s2 = SoqueteFake(), SoqueteFake()
    _entrar(servidor, "player-1", "Alice", s1)
    _entrar(servidor, "player-2", "Bob", s2)
    return servidor, s1, s2


def _esperar(condicao, limite=2.0):
    fim = time.time() + limite
    while time.time() < fim:
        if condicao():
            return True
        time.sleep(0.02)
    return condicao()


def test_pausa_de_2_segundos_entre_rodadas():
    servidor, s1, s2 = _partida()
    assert servidor.pausa_entre_rodadas == 2.0
    pergunta = servidor.perguntas_rodada["sala-1"]
    servidor.registrar_resposta_jogador("sala-1", 1, "player-1", pergunta["resposta_correta"])
    servidor.registrar_resposta_jogador("sala-1", 1, "player-2", pergunta["resposta_correta"])

    # FIM_RODADA sai na hora; a próxima PERGUNTA ainda não.
    assert "FIM_RODADA" in s1.tipos()
    time.sleep(0.5)
    assert s1.tipos().count("PERGUNTA") == 1
    servidor.fechar_servidor()


def test_desconexao_pausa_a_rodada_e_bloqueia_respostas():
    servidor, s1, s2 = _partida()
    servidor._tratar_desconexao_de_socket(s1)

    assert servidor.rodadas_por_sala["sala-1"]["pausada"] is True
    certa = servidor.perguntas_rodada["sala-1"]["resposta_correta"]
    assert servidor.registrar_resposta_jogador("sala-1", 1, "player-2", certa) is None
    aviso = s2.desconexoes()[-1]
    assert aviso["motivo"] == "aguardando_reconexao"
    assert aviso["tempo_espera"] == 30
    servidor.fechar_servidor()


def test_jogador_volta_a_tempo_e_a_partida_continua():
    servidor, s1, s2 = _partida()
    pergunta_antes = servidor.perguntas_rodada["sala-1"]["pergunta"]
    servidor._tratar_desconexao_de_socket(s1)

    novo = SoqueteFake()
    _entrar(servidor, "player-1", "Alice", novo)

    # Quem voltou recupera o lugar (mesmo id) e recebe a pergunta de novo.
    bem_vindo = [m for m in novo.mensagens if m["tipo"] == "BEM_VINDO"][-1]
    assert bem_vindo["id_jogador"] == "player-1"
    assert bem_vindo["reconectado"] is True
    perguntas = [m for m in novo.mensagens if m["tipo"] == "PERGUNTA"]
    assert perguntas and perguntas[-1]["pergunta"] == pergunta_antes
    # O adversário é avisado e também recebe a pergunta de novo.
    assert s2.desconexoes()[-1]["motivo"] == "reconectado"
    assert s2.tipos().count("PERGUNTA") == 2
    # A rodada voltou a aceitar respostas.
    assert servidor.rodadas_por_sala["sala-1"]["pausada"] is False
    assert "player-1" not in servidor._ausentes
    servidor.fechar_servidor()


def test_partida_encerra_se_o_jogador_nao_voltar():
    servidor, s1, s2 = _partida(tempo_reconexao=0.2)
    servidor._tratar_desconexao_de_socket(s1)
    assert "sala-1" in servidor.salas  # ainda esperando

    assert _esperar(lambda: "sala-1" not in servidor.salas)
    assert s2.desconexoes()[-1]["motivo"] == "tempo_esgotado"
    servidor.fechar_servidor()


def test_cada_jogador_ausente_tem_seu_proprio_cronometro():
    servidor, s1, s2 = _partida(tempo_reconexao=0.6)
    servidor._tratar_desconexao_de_socket(s1)
    time.sleep(0.3)
    servidor._tratar_desconexao_de_socket(s2)
    assert set(servidor._ausentes) == {"player-1", "player-2"}

    # player-2 volta enquanto player-1 ainda está ausente: a partida segue em
    # espera e ele fica sabendo que o outro também caiu.
    volta2 = SoqueteFake()
    _entrar(servidor, "player-2", "Bob", volta2)
    assert volta2.desconexoes()[-1]["motivo"] == "aguardando_reconexao"
    assert volta2.desconexoes()[-1]["id_jogador"] == "player-1"
    assert "PERGUNTA" not in volta2.tipos()

    # O cronômetro de player-1 (que começou antes) acaba e encerra a partida.
    assert _esperar(lambda: "sala-1" not in servidor.salas)
    assert volta2.desconexoes()[-1]["motivo"] == "tempo_esgotado"
    servidor.fechar_servidor()


def test_queda_na_pausa_entre_rodadas_segura_a_proxima_pergunta():
    servidor, s1, s2 = _partida()
    servidor.pausa_entre_rodadas = 0.2
    certa = servidor.perguntas_rodada["sala-1"]["resposta_correta"]
    servidor.registrar_resposta_jogador("sala-1", 1, "player-1", certa)
    servidor.registrar_resposta_jogador("sala-1", 1, "player-2", certa)
    servidor._tratar_desconexao_de_socket(s1)

    time.sleep(0.5)  # a pausa acabou, mas ninguém recebe a rodada 2 ainda
    assert s2.tipos().count("PERGUNTA") == 1

    novo = SoqueteFake()
    _entrar(servidor, "player-1", "Alice", novo)
    rodada2 = [m for m in novo.mensagens if m["tipo"] == "PERGUNTA"]
    assert rodada2 and rodada2[-1]["rodada_id"] == 2
    servidor.fechar_servidor()
