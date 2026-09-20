"""
Interface gráfica do Quiz Cabo de Guerra.

Layout:
  ┌─────────────────────────────────────┐
  │         Quiz Cabo de Guerra         │
  │   [status / aguardando / rodada]    │
  │                                     │
  │   ← Jogador A   [===|===]  Jogador B→ │  ← barra Canvas
  │   pts: X            pts: Y          │
  │                                     │
  │   [Pergunta aparece aqui]           │
  │   [Tempo: 30s]                      │
  │   ▼ Selecione uma opção             │
  │   [ Conectar ]   [ Enviar resposta ]│
  └─────────────────────────────────────┘

Mensagens tratadas (recebidas do servidor):
  PERGUNTA       → exibe pergunta + opções, reativa controles
  FIM_RODADA     → exibe quem venceu a rodada
  ATUALIZAR_BARRA→ redesenha a barra visual
  FIM_JOGO       → exibe tela de fim de jogo
  DESCONEXAO     → avisa que o adversário saiu
"""
import argparse
import threading
import tkinter as tk
from tkinter import messagebox

from src.client.client import ClienteQuiz

# ── Constantes visuais ─────────────────────────────────────────────────────
COR_FUNDO       = "#0f172a"
COR_TEXTO       = "#f8fafc"
COR_STATUS      = "#94a3b8"
COR_PERGUNTA    = "#e2e8f0"
COR_TEMPO       = "#fbbf24"
COR_BTN_CONN    = "#2563eb"
COR_BTN_RESP    = "#16a34a"
COR_BTN_OFF     = "#334155"
COR_BARRA_A     = "#3b82f6"   # azul — jogador da esquerda
COR_BARRA_B     = "#ef4444"   # vermelho — jogador da direita
COR_BARRA_NEU   = "#475569"   # cinza — zona neutra
COR_MARCA       = "#f8fafc"   # marcador central
LIMITE_BARRA    = 5           # deve coincidir com game_logic.LIMITE_BARRA


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

        # Estado local
        self.pergunta_atual: dict | None = None
        self.resposta_enviada = False
        self.conectado = False
        self._thread_escuta: threading.Thread | None = None
        self._timer_contagem: str | None = None   # after-id do Tk
        self._segundos_restantes = 30

        # ── Janela principal ──────────────────────────────────────────────
        self.janela = tk.Tk()
        self.janela.title("Quiz Cabo de Guerra — Redes")
        self.janela.geometry("760x600")
        self.janela.resizable(False, False)
        self.janela.configure(bg=COR_FUNDO)
        self.janela.protocol("WM_DELETE_WINDOW", self._ao_fechar)

        self._construir_ui()

    # ── Construção da UI ──────────────────────────────────────────────────

    def _construir_ui(self):
        # Título
        tk.Label(
            self.janela, text="⚔  Quiz Cabo de Guerra  ⚔",
            font=("Arial", 18, "bold"), fg=COR_TEXTO, bg=COR_FUNDO,
        ).pack(pady=(18, 4))

        # Status
        self.rotulo_status = tk.Label(
            self.janela, text="Clique em Conectar para começar",
            font=("Arial", 11), fg=COR_STATUS, bg=COR_FUNDO,
        )
        self.rotulo_status.pack(pady=(0, 10))

        # ── Barra cabo de guerra ──────────────────────────────────────────
        frame_barra = tk.Frame(self.janela, bg=COR_FUNDO)
        frame_barra.pack(fill="x", padx=30, pady=(0, 4))

        # Nomes dos jogadores (preenchidos ao receber PERGUNTA/FIM_JOGO)
        self.rotulo_nome_a = tk.Label(
            frame_barra, text="Você", font=("Arial", 10, "bold"),
            fg=COR_BARRA_A, bg=COR_FUNDO, width=12, anchor="w",
        )
        self.rotulo_nome_a.grid(row=0, column=0, sticky="w")

        self.rotulo_nome_b = tk.Label(
            frame_barra, text="Adversário", font=("Arial", 10, "bold"),
            fg=COR_BARRA_B, bg=COR_FUNDO, width=12, anchor="e",
        )
        self.rotulo_nome_b.grid(row=0, column=2, sticky="e")

        self.canvas_barra = tk.Canvas(
            frame_barra, width=520, height=40,
            bg=COR_FUNDO, highlightthickness=0,
        )
        self.canvas_barra.grid(row=0, column=1, padx=8)

        # Pontuações
        self.rotulo_pts_a = tk.Label(
            frame_barra, text="0 pts", font=("Arial", 10),
            fg=COR_BARRA_A, bg=COR_FUNDO, width=12, anchor="w",
        )
        self.rotulo_pts_a.grid(row=1, column=0, sticky="w")

        self.rotulo_rodada = tk.Label(
            frame_barra, text="Rodada — / 10",
            font=("Arial", 10), fg=COR_STATUS, bg=COR_FUNDO,
        )
        self.rotulo_rodada.grid(row=1, column=1)

        self.rotulo_pts_b = tk.Label(
            frame_barra, text="0 pts", font=("Arial", 10),
            fg=COR_BARRA_B, bg=COR_FUNDO, width=12, anchor="e",
        )
        self.rotulo_pts_b.grid(row=1, column=2, sticky="e")

        frame_barra.columnconfigure(1, weight=1)

        self._desenhar_barra(0, {})

        # ── Pergunta ──────────────────────────────────────────────────────
        self.rotulo_pergunta = tk.Label(
            self.janela, text="A pergunta aparecerá aqui quando a partida começar.",
            wraplength=680, justify="center",
            font=("Arial", 13, "bold"), fg=COR_PERGUNTA, bg=COR_FUNDO,
        )
        self.rotulo_pergunta.pack(pady=(14, 6), padx=20)

        # Tempo restante
        self.rotulo_tempo = tk.Label(
            self.janela, text="",
            font=("Arial", 12, "bold"), fg=COR_TEMPO, bg=COR_FUNDO,
        )
        self.rotulo_tempo.pack(pady=(0, 8))

        # ── Opções ────────────────────────────────────────────────────────
        self.opcoes_var = tk.StringVar(self.janela, value="")
        self.frame_opcoes = tk.Frame(self.janela, bg=COR_FUNDO)
        self.frame_opcoes.pack(pady=(0, 12))
        self._botoes_opcao: list[tk.Button] = []

        # ── Botões de ação ────────────────────────────────────────────────
        frame_btns = tk.Frame(self.janela, bg=COR_FUNDO)
        frame_btns.pack(pady=(4, 0))

        self.botao_conectar = tk.Button(
            frame_btns, text="Conectar",
            command=self.conectar,
            bg=COR_BTN_CONN, fg="white", activebackground="#1d4ed8",
            font=("Arial", 11, "bold"), width=16, height=2, relief="flat",
        )
        self.botao_conectar.grid(row=0, column=0, padx=10)

        self.botao_enviar = tk.Button(
            frame_btns, text="Enviar resposta",
            command=self.enviar_resposta,
            bg=COR_BTN_OFF, fg="#64748b", activebackground="#15803d",
            font=("Arial", 11, "bold"), width=16, height=2, relief="flat",
            state="disabled",
        )
        self.botao_enviar.grid(row=0, column=1, padx=10)

    # ── Barra visual ──────────────────────────────────────────────────────

    def _desenhar_barra(self, posicao: int, pontuacao: dict):
        """
        Redesenha o canvas da barra cabo de guerra.

        Convenção alinhada com game_logic.EstadoJogo:
          posicao > 0 → jogador_a (esquerda, AZUL) está na frente → barra puxa p/ ESQUERDA
          posicao < 0 → jogador_b (direita, VERMELHO) está na frente → barra puxa p/ DIREITA
          posicao == 0 → empatado no centro
        O marcador central se desloca proporcionalmente à vantagem.
        """
        c = self.canvas_barra
        c.delete("all")
        W, H = 520, 40
        cx = W // 2   # centro fixo

        # Fundo cinza (trilho)
        c.create_rectangle(0, 8, W, H - 8, fill=COR_BARRA_NEU, outline="", tags="trilho")

        # Fração da vantagem (-1.0 … +1.0), limitada ao intervalo válido
        frac = max(-1.0, min(1.0, posicao / LIMITE_BARRA))

        if posicao > 0:
            # Jogador A na frente → marcador vai para a ESQUERDA, azul preenche à esquerda
            marcador_x = cx - int(frac * cx)
            c.create_rectangle(0, 8, marcador_x, H - 8, fill=COR_BARRA_A, outline="")
        elif posicao < 0:
            # Jogador B na frente → marcador vai para a DIREITA, vermelho preenche à direita
            marcador_x = cx - int(frac * cx)   # frac negativo → marcador_x > cx
            c.create_rectangle(marcador_x, 8, W, H - 8, fill=COR_BARRA_B, outline="")
        else:
            marcador_x = cx

        # Marcador central (linha branca)
        c.create_rectangle(marcador_x - 3, 2, marcador_x + 3, H - 2,
                            fill=COR_MARCA, outline="")

        # Linha central de referência (tracejada fina)
        c.create_line(cx, 4, cx, H - 4, fill="#64748b", dash=(4, 4), width=1)

        # Atualiza pontuações nos rótulos
        jogadores = list(pontuacao.keys())
        pts_a = pontuacao.get(jogadores[0], 0) if jogadores else 0
        pts_b = pontuacao.get(jogadores[1], 0) if len(jogadores) > 1 else 0

        self.rotulo_pts_a.config(text=f"{pts_a} pts")
        self.rotulo_pts_b.config(text=f"{pts_b} pts")

    # ── Contagem regressiva ───────────────────────────────────────────────

    def _iniciar_contagem(self, segundos: int):
        self._parar_contagem()
        self._segundos_restantes = segundos
        self._tick_contagem()

    def _tick_contagem(self):
        if self._segundos_restantes > 0:
            self.rotulo_tempo.config(
                text=f"⏱ Tempo: {self._segundos_restantes}s",
                fg=COR_TEMPO if self._segundos_restantes > 5 else "#f87171",
            )
            self._segundos_restantes -= 1
            self._timer_contagem = self.janela.after(1000, self._tick_contagem)
        else:
            self.rotulo_tempo.config(text="⏱ Tempo esgotado!", fg="#f87171")

    def _parar_contagem(self):
        if self._timer_contagem is not None:
            self.janela.after_cancel(self._timer_contagem)
            self._timer_contagem = None

    # ── Opções de resposta ────────────────────────────────────────────────

    def _construir_opcoes(self, opcoes: list[str]):
        # Remove botões antigos
        for btn in self._botoes_opcao:
            btn.destroy()
        self._botoes_opcao.clear()

        self.opcoes_var.set("")
        for opcao in opcoes:
            btn = tk.Button(
                self.frame_opcoes, text=opcao,
                command=lambda o=opcao: self._selecionar_opcao(o),
                bg="#1e293b", fg=COR_TEXTO,
                activebackground="#334155", activeforeground=COR_TEXTO,
                font=("Arial", 11), width=30, height=1, relief="flat",
                anchor="w", padx=10,
            )
            btn.pack(pady=3)
            self._botoes_opcao.append(btn)

    def _selecionar_opcao(self, opcao: str):
        if self.resposta_enviada:
            return
        self.opcoes_var.set(opcao)
        # Destaca o botão selecionado
        for btn in self._botoes_opcao:
            if btn["text"] == opcao:
                btn.config(bg="#2563eb", fg="white")
            else:
                btn.config(bg="#1e293b", fg=COR_TEXTO)

    def _desativar_opcoes(self):
        for btn in getattr(self, "_botoes_opcao", []):
            btn.config(state="disabled", bg="#1e293b", fg="#475569")
        botao_enviar = getattr(self, "botao_enviar", None)
        menu_opcoes = getattr(self, "menu_opcoes", None)
        if botao_enviar:
            try:
                botao_enviar.config(state="disabled", bg=COR_BTN_OFF, fg="#64748b")
            except Exception:
                pass
        if menu_opcoes:
            try:
                menu_opcoes.config(state="disabled")
            except Exception:
                pass

    def _ativar_opcoes(self):
        for btn in self._botoes_opcao:
            btn.config(state="normal", bg="#1e293b", fg=COR_TEXTO)
        self.botao_enviar.config(state="normal", bg=COR_BTN_RESP, fg="white")

    # ── Conexão ───────────────────────────────────────────────────────────

    def conectar(self):
        if self.conectado:
            return
        try:
            self.cliente.conectar()
            self.conectado = True
            self.botao_conectar.config(
                state="disabled", text="✓ Conectado", bg="#064e3b",
            )
            self.cliente.enviar_entrada(self.id_jogador, self.apelido)
            self._set_status("Conectado. Aguardando o adversário entrar na sala…")
        except Exception as erro:
            messagebox.showerror("Erro de conexão", str(erro))
            return

        self._thread_escuta = threading.Thread(
            target=self.escutar_servidor, daemon=True
        )
        self._thread_escuta.start()

    # ── Loop de escuta (thread separada) ─────────────────────────────────

    def escutar_servidor(self):
        while True:
            if not self.conectado:
                return
            try:
                msg = self.cliente.receber_mensagem()
                if msg is None:
                    # None pode ser timeout OU conexão fechada.
                    # Verifica se o socket ainda está vivo.
                    if not self._conexao_viva():
                        self.janela.after(0, self._on_conexao_perdida)
                        return
                    continue
                tipo = msg.get("tipo", "")
                # Despacha para a thread Tk via after() — thread-safe
                if tipo == "BEM_VINDO":
                    self.janela.after(0, self._on_bem_vindo, msg)
                elif tipo == "PERGUNTA":
                    self.janela.after(0, self._on_pergunta, msg)
                elif tipo == "FIM_RODADA":
                    self.janela.after(0, self._on_fim_rodada, msg)
                elif tipo == "ATUALIZAR_BARRA":
                    self.janela.after(0, self._on_atualizar_barra, msg)
                elif tipo == "FIM_JOGO":
                    self.janela.after(0, self._on_fim_jogo, msg)
                elif tipo == "DESCONEXAO":
                    self.janela.after(0, self._on_desconexao, msg)
            except OSError:
                self.janela.after(0, self._on_conexao_perdida)
                return
            except Exception:
                continue

    def _conexao_viva(self) -> bool:
        """Verifica se o socket TCP ainda está conectado ao servidor."""
        try:
            self.cliente.socket_tcp.getpeername()
            return True
        except OSError:
            return False

    def _on_conexao_perdida(self):
        """Chamado na thread Tk quando a conexão com o servidor cai."""
        if not self.conectado:
            return
        self.conectado = False
        self._parar_contagem()
        self._desativar_opcoes()
        self._set_status("🔌 Conexão com o servidor perdida.")
        self.botao_conectar.config(
            state="normal", text="Reconectar",
            bg=COR_BTN_CONN, command=self._jogar_novamente,
        )
        messagebox.showerror(
            "Conexão perdida",
            "A conexão com o servidor foi encerrada. Clique em 'Reconectar' para tentar de novo.",
        )

    # ── Handlers de mensagens (executam na thread Tk) ─────────────────────

    def _on_bem_vindo(self, msg: dict):
        """
        ACK de ENTRAR: o servidor confirma nosso id DEFINITIVO (pode ter sido
        renomeado em caso de colisão). Atualizamos self.id_jogador para casar
        corretamente com os campos de placar/vencedor nas próximas mensagens.
        """
        id_confirmado = msg.get("id_jogador")
        if id_confirmado:
            self.id_jogador = id_confirmado
        apelido = msg.get("apelido")
        if apelido:
            self.apelido = apelido
        if msg.get("em_partida"):
            self._set_status("Partida encontrada! Boa sorte.")
        else:
            self._set_status("Conectado. Aguardando o adversário entrar na sala…")

    def _on_pergunta(self, msg: dict):
        self.pergunta_atual = extrair_detalhes_pergunta(msg)
        rodada_id   = self.pergunta_atual["rodada_id"]
        pergunta    = self.pergunta_atual["pergunta"]
        opcoes      = self.pergunta_atual["opcoes"]
        tempo_lim   = self.pergunta_atual["tempo_limite"]

        self.resposta_enviada = False
        self.rotulo_pergunta.config(text=pergunta)
        self.rotulo_rodada.config(text=f"Rodada {rodada_id} / 10")
        self._set_status(f"Rodada {rodada_id} — escolha sua resposta!")
        self._construir_opcoes(opcoes)
        self._ativar_opcoes()
        self._iniciar_contagem(tempo_lim)

    def _on_fim_rodada(self, msg: dict):
        self._parar_contagem()
        self.rotulo_tempo.config(text="")
        self.pergunta_atual = None

        vencedor          = msg.get("vencedor", "nenhum")
        apelido_vencedor  = msg.get("apelido_vencedor")
        resposta_correta  = msg.get("resposta_correta", "")
        rodada            = msg.get("rodada", "?")

        # Destaca a resposta correta em verde e as demais em vermelho
        self._destacar_resposta_correta(resposta_correta)

        nome_venc = apelido_vencedor or vencedor
        if vencedor == self.id_jogador:
            self._set_status(f"✅ Rodada {rodada}: você acertou primeiro! (resposta: {resposta_correta})")
        elif vencedor in (None, "nenhum"):
            self._set_status(f"😐 Rodada {rodada}: ninguém acertou. Resposta certa: {resposta_correta}")
        else:
            self._set_status(f"❌ Rodada {rodada}: {nome_venc} acertou primeiro. Resposta certa: {resposta_correta}")

    def _destacar_resposta_correta(self, resposta_correta: str):
        """Pinta o botão da resposta certa de verde; a escolhida errada de vermelho."""
        escolhida = self.opcoes_var.get()
        for btn in getattr(self, "_botoes_opcao", []):
            texto = btn["text"]
            btn.config(state="disabled")
            if texto == resposta_correta:
                btn.config(bg="#16a34a", fg="white", disabledforeground="white")
            elif texto == escolhida:
                btn.config(bg="#dc2626", fg="white", disabledforeground="white")
            else:
                btn.config(bg="#1e293b", fg="#64748b", disabledforeground="#64748b")
        botao_enviar = getattr(self, "botao_enviar", None)
        if botao_enviar:
            try:
                botao_enviar.config(state="disabled", bg=COR_BTN_OFF, fg="#64748b")
            except Exception:
                pass

    def _on_atualizar_barra(self, msg: dict):
        posicao   = msg.get("posicao", 0)
        pontuacao = msg.get("pontuacao", {})
        apelidos  = msg.get("apelidos", {})
        self._desenhar_barra(posicao, pontuacao)
        self._atualizar_nomes_barra(pontuacao, apelidos)

    def _atualizar_nomes_barra(self, pontuacao: dict, apelidos: dict):
        """Atualiza os rótulos de nome da barra usando apelidos (não IDs)."""
        jogadores = list(pontuacao.keys())
        if jogadores:
            jid_a = jogadores[0]
            nome_a = apelidos.get(jid_a, jid_a)
            self.rotulo_nome_a.config(
                text=f"▶ {nome_a}" if jid_a == self.id_jogador else nome_a,
            )
        if len(jogadores) > 1:
            jid_b = jogadores[1]
            nome_b = apelidos.get(jid_b, jid_b)
            self.rotulo_nome_b.config(
                text=f"{nome_b} ◀" if jid_b == self.id_jogador else nome_b,
            )

    def _on_fim_jogo(self, msg: dict):
        self._parar_contagem()
        self._desativar_opcoes()
        self.pergunta_atual = None

        vencedor          = msg.get("vencedor", "?")
        apelido_vencedor  = msg.get("apelido_vencedor")
        pontuacao         = msg.get("pontuacao", {})
        apelidos          = msg.get("apelidos", {})
        posicao           = msg.get("posicao", 0)

        # Desenha a barra na posição REAL final (não força extremo)
        self._desenhar_barra(posicao, pontuacao)
        self._atualizar_nomes_barra(pontuacao, apelidos)

        if vencedor == "empate":
            titulo  = "🤝 Empate!"
            detalhe = "A partida terminou empatada."
        elif vencedor == self.id_jogador:
            titulo  = "🏆 Você venceu!"
            detalhe = f"Parabéns, {self.apelido}! Você ganhou a partida."
        else:
            nome_venc = apelido_vencedor or vencedor
            titulo  = "😔 Você perdeu."
            detalhe = f"{nome_venc} venceu a partida."

        # Placar exibido com apelidos
        placar = "\n".join(
            f"  {apelidos.get(jid, jid)}: {p} pontos" for jid, p in pontuacao.items()
        )
        messagebox.showinfo(titulo, f"{detalhe}\n\nPlacar final:\n{placar}")
        self._set_status(f"Fim de jogo — {titulo}  |  Clique em 'Jogar novamente'")
        self.rotulo_rodada.config(text="Partida encerrada")

        self.botao_conectar.config(
            state="normal", text="Jogar novamente",
            bg=COR_BTN_CONN, command=self._jogar_novamente,
        )

    def _on_desconexao(self, msg: dict):
        dados = extrair_detalhes_desconexao(msg)
        motivo = msg.get("motivo")
        id_evento = dados["id_jogador"]

        # Timeout de espera (servidor avisa que ninguém entrou)
        if motivo == "timeout_espera":
            self._parar_contagem()
            self._set_status("⏳ Nenhum adversário entrou a tempo.")
            self.botao_conectar.config(
                state="normal", text="Tentar novamente",
                bg=COR_BTN_CONN, command=self._jogar_novamente,
            )
            messagebox.showinfo(
                "Sem adversário",
                msg.get("mensagem", "Nenhum adversário entrou a tempo. Tente novamente."),
            )
            return

        # Desconexão do adversário durante a partida
        if id_evento != self.id_jogador:
            self._parar_contagem()
            self._desativar_opcoes()
            apelido_adv = msg.get("apelido", id_evento)
            self._set_status(f"⚠ {apelido_adv} saiu da partida.")
            self.botao_conectar.config(
                state="normal", text="Jogar novamente",
                bg=COR_BTN_CONN, command=self._jogar_novamente,
            )
            messagebox.showwarning(
                "Adversário desconectado",
                f"{apelido_adv} saiu da partida. Você pode iniciar uma nova.",
            )

    # ── Envio de resposta ─────────────────────────────────────────────────

    def enviar_resposta(self):
        if self.pergunta_atual is None:
            messagebox.showinfo("Aguardando", "Nenhuma pergunta ativa no momento.")
            return
        if getattr(self, "resposta_enviada", False):
            return
        resposta = self.opcoes_var.get()
        if not resposta:
            messagebox.showinfo("Selecione", "Escolha uma opção antes de enviar.")
            return

        self.cliente.enviar_resposta(
            self.id_jogador, self.pergunta_atual["rodada_id"], resposta
        )
        self.resposta_enviada = True
        self._desativar_opcoes()
        self._set_status("Resposta enviada — aguardando o adversário…")

    # ── Compatibilidade com testes legados ────────────────────────────────

    def atualizar_pergunta(self, mensagem: dict):
        """
        API legada usada por testes que constroem JanelaQuiz via object.__new__.
        Atualiza a pergunta atual e reabilita os controles sem usar Canvas/Timer.
        """
        self.pergunta_atual = extrair_detalhes_pergunta(mensagem)
        self.resposta_enviada = False

        # Atualiza widgets de texto se existirem
        rotulo_pergunta = getattr(self, "rotulo_pergunta", None)
        if rotulo_pergunta:
            rotulo_pergunta.config(text=self.pergunta_atual["pergunta"])

        rotulo_tempo = getattr(self, "rotulo_tempo", None)
        if rotulo_tempo:
            rotulo_tempo.config(text=f"Tempo: {self.pergunta_atual['tempo_limite']}s")

        rotulo_status = getattr(self, "rotulo_status", None)
        if rotulo_status:
            rotulo_status.config(
                text=f"Rodada {self.pergunta_atual['rodada_id']} — escolha uma opção"
            )

        # Atualiza o menu de opções legado (OptionMenu) se existir
        menu_opcoes = getattr(self, "menu_opcoes", None)
        if menu_opcoes:
            try:
                menu = menu_opcoes["menu"]
                menu.delete(0, "end")
                for opcao in self.pergunta_atual["opcoes"]:
                    menu.add_command(label=opcao, command=lambda v=opcao: self.opcoes_var.set(v))
                menu_opcoes.config(state="normal")
            except (TypeError, AttributeError, KeyError):
                try:
                    menu_opcoes.config(state="normal")
                except Exception:
                    pass

        botao_enviar = getattr(self, "botao_enviar", None)
        if botao_enviar:
            try:
                botao_enviar.config(state="normal")
            except Exception:
                pass

    # ── Jogar novamente ───────────────────────────────────────────────────

    def _jogar_novamente(self):
        """Reconecta ao servidor e entra na fila para uma nova partida."""
        self.botao_conectar.config(state="disabled", text="Conectando…", bg="#334155")
        self._set_status("Reconectando…")

        # Fecha o socket antigo
        try:
            self.cliente.socket_tcp.close()
        except Exception:
            pass

        # Cria um cliente novo
        self.cliente = ClienteQuiz(
            host=self.cliente.host,
            porta_tcp=self.cliente.porta_tcp,
            porta_udp=self.cliente.porta_udp,
        )
        self.conectado = False

        # Reseta o visual da barra
        self._desenhar_barra(0, {})
        self.rotulo_rodada.config(text="Rodada — / 10")
        self.rotulo_pts_a.config(text="0 pts")
        self.rotulo_pts_b.config(text="0 pts")
        self.rotulo_tempo.config(text="")
        self.rotulo_pergunta.config(text="A pergunta aparecerá aqui quando a partida começar.")

        # Remove botões de opção antigos
        for btn in getattr(self, "_botoes_opcao", []):
            btn.destroy()
        self._botoes_opcao.clear()

        # Reconecta
        self.conectar()

    # ── Utilitários ───────────────────────────────────────────────────────

    def _set_status(self, texto: str):
        self.rotulo_status.config(text=texto)

    def _ao_fechar(self):
        self.janela.destroy()

    def iniciar(self):
        self.janela.mainloop()


# ── Funções utilitárias (usadas pelos testes) ─────────────────────────────

def extrair_detalhes_pergunta(mensagem: dict) -> dict:
    return {
        "rodada_id":   mensagem.get("rodada_id", 1),
        "pergunta":    mensagem.get("pergunta", "Pergunta não disponível"),
        "opcoes":      mensagem.get("opcoes", []),
        "tempo_limite": mensagem.get("tempo_limite", 30),
    }


def extrair_detalhes_desconexao(mensagem: dict) -> dict:
    return {
        "id_jogador":  mensagem.get("id_jogador", "desconhecido"),
        "codigo_sala": mensagem.get("codigo_sala", "sala-1"),
    }


# ── Entry point ───────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Cliente do Quiz Cabo de Guerra")
    parser.add_argument("--id-jogador", default="player-1",
                        help="Identificador do jogador no servidor")
    parser.add_argument("--apelido", default="Jogador 1",
                        help="Apelido exibido no jogo")
    parser.add_argument("--host", default="127.0.0.1",
                        help="Host do servidor")
    parser.add_argument("--porta-tcp", type=int, default=5000,
                        help="Porta TCP do servidor")
    parser.add_argument("--porta-udp", type=int, default=5001,
                        help="Porta UDP do servidor")
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
