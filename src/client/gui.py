import argparse
import json
import threading
import time
from tkinter import Tk, Button, Label, OptionMenu, StringVar, messagebox

from src.client.client import ClienteQuiz


class JanelaQuiz:
    def __init__(
        self,
        host: str = "127.0.0.1",
        porta_tcp: int = 5000,
        porta_udp: int = 5001,
        id_jogador: str = "player-1",
        apelido: str = "Jogador 1",
    ):
        self.id_jogador = id_jogador
        self.apelido = apelido
        self.cliente = ClienteQuiz(host=host, porta_tcp=porta_tcp, porta_udp=porta_udp)
        self.janela = Tk()
        self.janela.title("Quiz Cabo de Guerra - Redes")
        self.janela.geometry("720x520")
        self.janela.configure(bg="#0f172a")

        self.pergunta_atual = None
        self.tempo_limite = 30
        self._thread_escuta = None
        self.conectado = False
        self.resposta_enviada = False

        self.var_resposta = StringVar(self.janela)

        self.rotulo_titulo = Label(
            self.janela,
            text="Quiz Cabo de Guerra",
            font=("Arial", 20, "bold"),
            fg="#e2e8f0",
            bg="#0f172a",
        )
        self.rotulo_titulo.pack(pady=(20, 5))

        self.rotulo_status = Label(
            self.janela,
            text="Conecte-se para começar",
            fg="#cbd5e1",
            bg="#0f172a",
            font=("Arial", 11),
        )
        self.rotulo_status.pack(pady=(0, 15))

        self.rotulo_pergunta = Label(
            self.janela,
            text="Pergunta aparecerá aqui",
            wraplength=620,
            justify="center",
            fg="#f8fafc",
            bg="#0f172a",
            font=("Arial", 14, "bold"),
        )
        self.rotulo_pergunta.pack(pady=(10, 20))

        self.rotulo_tempo = Label(
            self.janela,
            text="Tempo: 30s",
            fg="#fbbf24",
            bg="#0f172a",
            font=("Arial", 12, "bold"),
        )
        self.rotulo_tempo.pack(pady=(0, 15))

        self.opcoes_var = StringVar(self.janela)
        self.opcoes_var.set("Selecione uma opção")

        self.menu_opcoes = OptionMenu(self.janela, self.opcoes_var, "")
        self.menu_opcoes.config(width=40, height=2, bg="#1e293b", fg="#f8fafc")
        self.menu_opcoes.pack(pady=(0, 16))

        self.botao_conectar = Button(
            self.janela,
            text="Conectar",
            command=self.conectar,
            bg="#2563eb",
            fg="white",
            activebackground="#1d4ed8",
            font=("Arial", 11, "bold"),
            width=18,
            height=2,
        )
        self.botao_conectar.pack(pady=(0, 8))

        self.botao_enviar = Button(
            self.janela,
            text="Enviar resposta",
            command=self.enviar_resposta,
            bg="#16a34a",
            fg="white",
            activebackground="#15803d",
            font=("Arial", 11, "bold"),
            width=18,
            height=2,
        )
        self.botao_enviar.pack()

    def conectar(self):
        if self.conectado:
            return

        try:
            self.cliente.conectar()
            self.conectado = True
            self.botao_conectar.config(state="disabled", text="Conectado")
            self.cliente.enviar_entrada(self.id_jogador, self.apelido)
            self.rotulo_status.config(text="Conectado. Aguardando partida...")
            self._thread_escuta = threading.Thread(target=self.escutar_servidor, daemon=True)
            self._thread_escuta.start()
        except Exception as erro:  # pragma: no cover - depende de ambiente de rede
            messagebox.showerror("Erro de conexão", str(erro))

    def escutar_servidor(self):
        while True:
            try:
                mensagem = self.cliente.receber_mensagem()
                if mensagem is None:
                    continue

                if mensagem.get("tipo") == "PERGUNTA":
                    self.atualizar_pergunta(mensagem)
                elif mensagem.get("tipo") == "FIM_RODADA":
                    self.pergunta_atual = None
                    self.resposta_enviada = False
                    self.menu_opcoes.config(state="disabled")
                    self.botao_enviar.config(state="disabled")
                    self.rotulo_status.config(text=f"Rodada finalizada. Vencedor: {mensagem.get('vencedor')}")
                elif mensagem.get("tipo") == "DESCONEXAO":
                    dados = extrair_detalhes_desconexao(mensagem)
                    if dados["id_jogador"] != self.id_jogador:
                        self.rotulo_status.config(text=f"Jogador {dados['id_jogador']} saiu da partida.")
            except OSError:
                break
            except Exception:  # pragma: no cover - depende do servidor
                continue

    def atualizar_pergunta(self, mensagem):
        self.pergunta_atual = extrair_detalhes_pergunta(mensagem)
        self.tempo_limite = self.pergunta_atual["tempo_limite"]
        self.resposta_enviada = False
        self.rotulo_pergunta.config(text=self.pergunta_atual["pergunta"])
        self.rotulo_tempo.config(text=f"Tempo: {self.tempo_limite}s")
        self.rotulo_status.config(text=f"Rodada {self.pergunta_atual['rodada_id']} — escolha uma opção")

        opcoes = self.pergunta_atual["opcoes"]
        menu = self.menu_opcoes["menu"]
        menu.delete(0, "end")
        for opcao in opcoes:
            menu.add_command(label=opcao, command=lambda valor=opcao: self.opcoes_var.set(valor))
        self.opcoes_var.set(opcoes[0])
        self.menu_opcoes.config(state="normal")
        self.botao_enviar.config(state="normal")

    def enviar_resposta(self):
        if self.pergunta_atual is None:
            messagebox.showinfo("Aguardando pergunta", "A pergunta ainda não chegou.")
            return
        if self.resposta_enviada:
            return

        resposta = self.opcoes_var.get()
        self.cliente.enviar_resposta(self.id_jogador, self.pergunta_atual["rodada_id"], resposta)
        self.resposta_enviada = True
        self.menu_opcoes.config(state="disabled")
        self.botao_enviar.config(state="disabled")
        self.rotulo_status.config(text="Resposta enviada. Aguardando resultado...")

    def iniciar(self):
        self.janela.mainloop()


def extrair_detalhes_pergunta(mensagem: dict):
    return {
        "rodada_id": mensagem.get("rodada_id", 1),
        "pergunta": mensagem.get("pergunta", "Pergunta não disponível"),
        "opcoes": mensagem.get("opcoes", []),
        "tempo_limite": mensagem.get("tempo_limite", 30),
    }


def extrair_detalhes_desconexao(mensagem: dict):
    return {
        "id_jogador": mensagem.get("id_jogador", "desconhecido"),
        "codigo_sala": mensagem.get("codigo_sala", "sala-1"),
    }


def main():
    parser = argparse.ArgumentParser(description="Cliente do Quiz Cabo de Guerra")
    parser.add_argument("--id-jogador", default="player-1", help="Identificador do jogador no servidor")
    parser.add_argument("--apelido", default="Jogador 1", help="Apelido exibido no jogo")
    parser.add_argument("--host", default="127.0.0.1", help="Host do servidor")
    parser.add_argument("--porta-tcp", type=int, default=5000, help="Porta TCP do servidor")
    parser.add_argument("--porta-udp", type=int, default=5002, help="Porta UDP do cliente")
    args = parser.parse_args()

    app = JanelaQuiz(
        host=args.host,
        porta_tcp=args.porta_tcp,
        porta_udp=args.porta_udp,
        id_jogador=args.id_jogador,
        apelido=args.apelido,
    )
    app.iniciar()


if __name__ == "__main__":
    main()
