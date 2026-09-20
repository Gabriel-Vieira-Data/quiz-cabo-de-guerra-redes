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
    DESCONEXAO = "DESCONEXAO"
    PING = "PING"
    PONG = "PONG"


def criar_mensagem(tipo_mensagem: TipoMensagem, dados: dict | None = None) -> dict:
    """Cria uma mensagem padronizada com tipo e payload."""
    mensagem = {"tipo": tipo_mensagem.value if isinstance(tipo_mensagem, TipoMensagem) else str(tipo_mensagem)}

    if dados:
        mensagem.update(dados)

    return mensagem


def codificar_mensagem(mensagem: dict) -> bytes:
    """Serializa uma mensagem em JSON em bytes com prefixo de tamanho."""
    payload = json.dumps(mensagem, ensure_ascii=False).encode("utf-8")
    cabecalho = len(payload).to_bytes(4, byteorder="big", signed=False)
    return cabecalho + payload


def decodificar_mensagem(mensagem_bruta: bytes | str) -> dict:
    """Desserializa uma mensagem JSON em dicionário, aceitando payload bruto ou com cabeçalho de tamanho."""
    if isinstance(mensagem_bruta, bytes):
        if len(mensagem_bruta) >= 4:
            try:
                tamanho = int.from_bytes(mensagem_bruta[:4], byteorder="big", signed=False)
                if tamanho > 0 and len(mensagem_bruta) >= 4 + tamanho:
                    payload = mensagem_bruta[4:4 + tamanho]
                    if payload.strip().startswith(b"{"):
                        mensagem_bruta = payload
            except (OverflowError, ValueError):
                pass
        mensagem_bruta = mensagem_bruta.decode("utf-8")

    return json.loads(mensagem_bruta)


MessageType = TipoMensagem
build_message = criar_mensagem
encode_message = codificar_mensagem
decode_message = decodificar_mensagem
