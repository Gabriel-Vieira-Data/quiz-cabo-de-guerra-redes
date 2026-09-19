import json

from src.common.protocol import MessageType, build_message, decode_message, encode_message


def test_build_message_has_type_and_payload():
    message = build_message(
        MessageType.JOIN,
        {"player_id": "player-1", "nickname": "Alice"},
    )

    assert message["type"] == MessageType.JOIN
    assert message["player_id"] == "player-1"
    assert message["nickname"] == "Alice"


def test_encode_and_decode_round_trip():
    original = {
        "type": MessageType.QUESTION,
        "round_id": 2,
        "question": "Qual protocolo é orientado à conexão?",
        "options": ["TCP", "UDP", "ICMP", "ARP"],
        "time_limit": 10,
    }

    encoded = encode_message(original)
    decoded = decode_message(encoded)

    assert isinstance(encoded, bytes)
    assert decoded == original


def test_decode_message_accepts_json_bytes_and_str():
    payload = json.dumps({"type": MessageType.READY, "player_id": "player-2"}).encode("utf-8")

    decoded = decode_message(payload)

    assert decoded["type"] == MessageType.READY
    assert decoded["player_id"] == "player-2"
