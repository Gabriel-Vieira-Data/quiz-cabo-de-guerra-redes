import json
from enum import Enum


class MessageType(str, Enum):
    JOIN = "JOIN"
    READY = "READY"
    QUESTION = "QUESTION"
    ANSWER = "ANSWER"
    RESULT = "RESULT"
    UPDATE_BAR = "UPDATE_BAR"
    END_ROUND = "END_ROUND"
    END_GAME = "END_GAME"
    PING = "PING"
    PONG = "PONG"


def build_message(message_type: MessageType, payload: dict | None = None) -> dict:
    """Cria uma mensagem padronizada com type e payload."""
    message = {"type": message_type.value if isinstance(message_type, MessageType) else str(message_type)}

    if payload:
        message.update(payload)

    return message


def encode_message(message: dict) -> bytes:
    """Serializa uma mensagem em JSON em bytes."""
    return json.dumps(message, ensure_ascii=False).encode("utf-8")


def decode_message(raw_message: bytes | str) -> dict:
    """Desserializa uma mensagem JSON em dicionário."""
    if isinstance(raw_message, bytes):
        raw_message = raw_message.decode("utf-8")

    return json.loads(raw_message)
