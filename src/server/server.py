import socket
from typing import Dict, List, Tuple

from src.common.protocol import MessageType, build_message, decode_message, encode_message


class QuizServer:
    def __init__(self, host: str = "127.0.0.1", tcp_port: int = 5000, udp_port: int = 5001):
        self.host = host
        self.tcp_port = tcp_port
        self.udp_port = udp_port
        self.connected_players: Dict[str, socket.socket] = {}
        self.game_state = {
            "bar_position": 0,
            "round": 1,
            "max_rounds": 10,
        }

    def start_tcp_server(self):
        self.tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.tcp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.tcp_socket.bind((self.host, self.tcp_port))
        self.tcp_socket.listen()
        print(f"Servidor TCP ouvindo em {self.host}:{self.tcp_port}")

    def start_udp_server(self):
        self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.udp_socket.bind((self.host, self.udp_port))
        print(f"Servidor UDP ouvindo em {self.host}:{self.udp_port}")

    def accept_connections(self):
        while len(self.connected_players) < 2:
            conn, addr = self.tcp_socket.accept()
            client_id = f"player-{len(self.connected_players) + 1}"
            self.connected_players[client_id] = conn
            print(f"Cliente conectado: {client_id} em {addr}")

    def send_message(self, client_socket: socket.socket, message_type: MessageType, payload: dict):
        message = build_message(message_type, payload)
        client_socket.sendall(encode_message(message))

    def broadcast(self, message_type: MessageType, payload: dict):
        for client in self.connected_players.values():
            self.send_message(client, message_type, payload)

    def handle_question(self, question: dict):
        self.broadcast(MessageType.QUESTION, question)

    def update_bar(self, direction: int):
        self.game_state["bar_position"] += direction
        self.broadcast(MessageType.UPDATE_BAR, {"position": self.game_state["bar_position"]})

    def end_round(self, winner: str | None = None):
        self.broadcast(MessageType.END_ROUND, {"winner": winner, "round": self.game_state["round"]})

    def end_game(self, winner: str):
        self.broadcast(MessageType.END_GAME, {"winner": winner})
