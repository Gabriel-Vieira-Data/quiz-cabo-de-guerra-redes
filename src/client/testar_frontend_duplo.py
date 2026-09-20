import os
import subprocess
import sys
import time


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def iniciar_servidor():
    return subprocess.Popen(
        [sys.executable, "-m", "src.server.server"],
        cwd=ROOT,
        creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0),
    )


def iniciar_cliente(id_jogador: str, apelido: str, porta_udp: int):
    return subprocess.Popen(
        [
            sys.executable,
            "-m",
            "src.client.gui",
            "--id-jogador",
            id_jogador,
            "--apelido",
            apelido,
            "--porta-udp",
            str(porta_udp),
        ],
        cwd=ROOT,
        creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0),
    )


if __name__ == "__main__":
    servidor = iniciar_servidor()
    time.sleep(1)
    cliente_1 = iniciar_cliente("player-1", "Alice", 5002)
    cliente_2 = iniciar_cliente("player-2", "Bob", 5003)

    print("Servidor e dois clientes abertos.")
    print("Feche esta janela para encerrar os processos.")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        for processo in (cliente_1, cliente_2, servidor):
            if processo.poll() is None:
                processo.terminate()
