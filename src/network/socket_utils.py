import socket
import struct


def create_tcp_server(host: str, port: int):
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((host, port))
    server.listen()
    return server


def create_tcp_client():
    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    return client


def create_udp_socket():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    return sock


def send_all(sock: socket.socket, data: bytes):
    total_sent = 0
    while total_sent < len(data):
        sent = sock.send(data[total_sent:])
        if sent == 0:
            raise RuntimeError("Falha ao enviar dados pela conexão TCP.")
        total_sent += sent


def recv_exactly(sock: socket.socket, length: int) -> bytes:
    chunks = []
    remaining = length

    while remaining > 0:
        chunk = sock.recv(remaining)
        if not chunk:
            raise ConnectionError("Conexão encerrada antes de receber todos os dados.")
        chunks.append(chunk)
        remaining -= len(chunk)

    return b"".join(chunks)


def send_udp_message(sock: socket.socket, message: bytes, address: tuple[str, int]):
    sock.sendto(message, address)


def recv_udp_message(sock: socket.socket, buffer_size: int = 4096):
    data, addr = sock.recvfrom(buffer_size)
    return data, addr


def pack_int(value: int) -> bytes:
    return struct.pack("!I", value)


def unpack_int(data: bytes) -> int:
    return struct.unpack("!I", data)[0]
