import json

from src.common.protocol import TipoMensagem, criar_mensagem, decodificar_mensagem, codificar_mensagem


def test_criar_mensagem_tem_tipo_e_dados():
    mensagem = criar_mensagem(
        TipoMensagem.ENTRAR,
        {"id_jogador": "player-1", "apelido": "Alice"},
    )

    assert mensagem["tipo"] == TipoMensagem.ENTRAR
    assert mensagem["id_jogador"] == "player-1"
    assert mensagem["apelido"] == "Alice"


def test_codificar_e_decodificar_round_trip():
    original = {
        "tipo": TipoMensagem.PERGUNTA,
        "rodada_id": 2,
        "pergunta": "Qual protocolo é orientado à conexão?",
        "opcoes": ["TCP", "UDP", "ICMP", "ARP"],
        "tempo_limite": 10,
    }

    codificado = codificar_mensagem(original)
    decodificado = decodificar_mensagem(codificado)

    assert isinstance(codificado, bytes)
    assert decodificado == original


def test_decodificar_mensagem_aceita_json_em_bytes_e_str():
    payload = json.dumps({"tipo": TipoMensagem.PRONTO, "id_jogador": "player-2"}).encode("utf-8")

    decodificado = decodificar_mensagem(payload)

    assert decodificado["tipo"] == TipoMensagem.PRONTO
    assert decodificado["id_jogador"] == "player-2"
