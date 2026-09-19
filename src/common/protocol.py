import json
from enum import Enum


class TipoMensagem(str, Enum):
    ENTRAR = "ENTRAR"
    PRONTO = "PRONTO"
    PERGUNTA = "PERGUNTA"
    RESPOSTA = "RESPOSTA"
    RESULTADO = "RESULTADO"
    ATUALIZAR_BARRA = "ATUALIZAR_BARRA"
    FIM_RODADA = "FIM_RODADA"
    FIM_JOGO = "FIM_JOGO"
    PING = "PING"
    PONG = "PONG"


def criar_mensagem(tipo_mensagem: TipoMensagem, dados: dict | None = None) -> dict:
    """Cria uma mensagem padronizada com tipo e payload."""
    mensagem = {"tipo": tipo_mensagem.value if isinstance(tipo_mensagem, TipoMensagem) else str(tipo_mensagem)}

    if dados:
        mensagem.update(dados)

    return mensagem


def codificar_mensagem(mensagem: dict) -> bytes:
    """Serializa uma mensagem em JSON em bytes."""
    return json.dumps(mensagem, ensure_ascii=False).encode("utf-8")


def decodificar_mensagem(mensagem_bruta: bytes | str) -> dict:
    """Desserializa uma mensagem JSON em dicionário."""
    if isinstance(mensagem_bruta, bytes):
        mensagem_bruta = mensagem_bruta.decode("utf-8")

    return json.loads(mensagem_bruta)


MessageType = TipoMensagem
build_message = criar_mensagem
encode_message = codificar_mensagem
decode_message = decodificar_mensagem
