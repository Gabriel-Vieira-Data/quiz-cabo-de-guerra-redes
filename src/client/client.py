import socket

from src.common.protocol import MessageType, build_message, decode_message, encode_message


class QuizClient:
    def __init__(self, host: str = "127.0.0.1", tcp_port: int = 5000, udp_port: int = 5001):
        self.host = host
        self.tcp_port = tcp_port
        self.udp_port = udp_port
        self.tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def connect(self):
        self.tcp_socket.connect((self.host, self.tcp_port))
        self.udp_socket.bind((self.host, self.udp_port))

    def send_join(self, player_id: str, nickname: str):
        message = build_message(MessageType.JOIN, {"player_id": player_id, "nickname": nickname})
        self.tcp_socket.sendall(encode_message(message))

    def send_answer(self, player_id: str, round_id: int, answer: str):
        message = build_message(
            MessageType.ANSWER,
            {"player_id": player_id, "round_id": round_id, "answer": answer},
        )
        self.tcp_socket.sendall(encode_message(message))

    def receive_message(self):
        data = self.tcp_socket.recv(4096)
        if not data:
            return None
        return decode_message(data)

    def send_udp_ping(self):
        ping = build_message(MessageType.PING, {"player_id": "client"})
        self.udp_socket.sendto(encode_message(ping), (self.host, self.udp_port))
