"""
Protocolo de mensagens do Quiz Cabo de Guerra.

Formato de wire: [4 bytes big-endian = tamanho do payload][payload JSON UTF-8]

Tipos de mensagem (9 no total):
  ENTRAR        Client → Server  Jogador entra na fila      {id_jogador, apelido}
  PERGUNTA      Server → Client  Nova rodada começa         {rodada_id, pergunta, opcoes, resposta_correta, tempo_limite}
  RESPOSTA      Client → Server  Jogador responde           {id_jogador, rodada_id, resposta}
  ATUALIZAR_BARRA Server→Client  Barra se move              {posicao, pontuacao}
  FIM_RODADA    Server → Client  Rodada terminou            {vencedor, rodada, codigo_sala}
  FIM_JOGO      Server → Client  Partida encerrada          {vencedor, pontuacao}
  DESCONEXAO    Server → Client  Jogador desconectou        {id_jogador, codigo_sala}
  PING          Client → Server  Verificação de latência UDP {id_jogador}
  PONG          Server → Client  Resposta ao ping UDP       {id_jogador}
"""
import json
from enum import Enum


class TipoMensagem(str, Enum):
    ENTRAR          = "ENTRAR"
    PERGUNTA        = "PERGUNTA"
    RESPOSTA        = "RESPOSTA"
    ATUALIZAR_BARRA = "ATUALIZAR_BARRA"
    FIM_RODADA      = "FIM_RODADA"
    FIM_JOGO        = "FIM_JOGO"
    DESCONEXAO      = "DESCONEXAO"
    PING            = "PING"
    PONG            = "PONG"
    PRONTO          = "PRONTO"   # reservado para uso futuro (10º tipo)


def criar_mensagem(tipo_mensagem: TipoMensagem, dados: dict | None = None) -> dict:
    """Cria uma mensagem padronizada com tipo e payload."""
    mensagem = {"tipo": tipo_mensagem.value if isinstance(tipo_mensagem, TipoMensagem) else str(tipo_mensagem)}
    if dados:
        mensagem.update(dados)
    return mensagem


def codificar_mensagem(mensagem: dict) -> bytes:
    """Serializa uma mensagem em JSON em bytes com prefixo de tamanho (4 bytes big-endian)."""
    payload = json.dumps(mensagem, ensure_ascii=False).encode("utf-8")
    cabecalho = len(payload).to_bytes(4, byteorder="big", signed=False)
    return cabecalho + payload


def decodificar_mensagem(mensagem_bruta: bytes | str) -> dict:
    """Desserializa uma mensagem JSON. Aceita payload com ou sem cabeçalho de tamanho."""
    if isinstance(mensagem_bruta, bytes):
        if len(mensagem_bruta) >= 4:
            try:
                tamanho = int.from_bytes(mensagem_bruta[:4], byteorder="big", signed=False)
                if tamanho > 0 and len(mensagem_bruta) >= 4 + tamanho:
                    payload = mensagem_bruta[4 : 4 + tamanho]
                    if payload.strip().startswith(b"{"):
                        mensagem_bruta = payload
            except (OverflowError, ValueError):
                pass
        mensagem_bruta = mensagem_bruta.decode("utf-8")
    return json.loads(mensagem_bruta)


# Aliases em inglês para compatibilidade com testes existentes
MessageType = TipoMensagem
build_message = criar_mensagem
encode_message = codificar_mensagem
decode_message = decodificar_mensagem
