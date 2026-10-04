"""
Interface gráfica do Quiz Cabo de Guerra.

Layout:
  ┌──────────────────────────────────────────┐
  │          ⚔ QUIZ CABO DE GUERRA ⚔  📶 12 ms│  ← ping via UDP
  │            [mensagem de status]          │
  │   [ Jogador A  0 ]  VS  [ Jogador B  0 ] │  ← cartões de placar
  │   🧍═════════════●═════════════🧍          │  ← corda (Canvas)
  │               Rodada N / 10              │
  │   [ Pergunta ]                           │
  │   ⏱ Tempo + barra de tempo               │
  │   [1 opção] [2 opção] [3 opção] [4 opção]│
  │   Seu nome: [______] 0/20                │  ← some quando a partida começa
  │   [ Conectar ]   [ Enviar resposta ]     │
  │   Histórico da partida                   │
  └──────────────────────────────────────────┘

Mensagens tratadas (recebidas do servidor):
  BEM_VINDO      → confirma a entrada e o id definitivo
  PERGUNTA       → exibe pergunta + opções, reativa controles
  FIM_RODADA     → exibe quem venceu a rodada e a resposta certa
  ATUALIZAR_BARRA→ move a corda e atualiza o placar
  FIM_JOGO       → exibe a tela final animada
  DESCONEXAO     → avisa que o adversário saiu (ou que ninguém entrou)
  PONG (UDP)     → resposta ao PING enviado a cada 2 s; mostra a latência no topo

Threads: o Tkinter só pode ser mexido pela thread principal. A escuta do
servidor roda em outra thread (escutar_servidor) e, ao receber uma mensagem,
agenda o tratamento na thread do Tk com janela.after(0, ...).

Animações: um "loop" com janela.after(FPS_MS, ...) redesenha a corda ~33
vezes por segundo. Cada quadro calcula a posição a partir do tempo passado
(time.monotonic), então a velocidade não depende do computador.

Marcação de origem (ver USO_DE_IA.md): "# [Origem: ...]" acima de cada
classe/função — "IA" = escrito com auxílio de IA; "autoral" = escrito pelos
integrantes sem IA (medido com git blame).
"""
import argparse
import math
import random
import threading
import time
import tkinter as tk
from tkinter import messagebox

from src.client.client import ClienteQuiz
# Importa o limite da corda direto da lógica para nunca ficar dessincronizado.
from src.common.game_logic import LIMITE_BARRA

# ── Paleta de cores ─────────────────────────────────────────────────────────
COR_FUNDO_EXTERNO = "#020617"   # moldura externa da janela (quase preto azulado)
COR_FUNDO       = "#0f172a"     # painel central (card)
COR_CARD_TOPO   = "#111c33"     # faixa de cabeçalho do card
COR_BORDA       = "#1e293b"     # contorno do card e divisórias
COR_PAINEL      = "#172032"     # painéis internos (pergunta, histórico)
COR_TEXTO       = "#f8fafc"
COR_STATUS      = "#94a3b8"
COR_PERGUNTA    = "#f1f5f9"
COR_TEMPO       = "#fbbf24"
COR_ACENTO      = "#38bdf8"     # ciano de destaque (título/detalhes)
COR_BTN_CONN    = "#2563eb"
COR_BTN_RESP    = "#16a34a"
COR_BTN_OFF     = "#334155"
COR_OPCAO       = "#1e293b"     # botão de opção normal
COR_OPCAO_H     = "#334155"     # botão de opção com hover
COR_OPCAO_SEL   = "#2563eb"     # botão de opção selecionado
COR_ACERTO      = "#16a34a"     # opção correta (feedback)
COR_ERRO        = "#dc2626"     # opção errada escolhida (feedback)

# Cores do cabo de guerra
COR_BARRA_A     = "#3b82f6"   # azul — jogador da esquerda
COR_BARRA_A_ESC = "#1e3a8a"   # azul escuro (sombra da corda)
COR_BARRA_B     = "#ef4444"   # vermelho — jogador da direita
COR_BARRA_B_ESC = "#7f1d1d"   # vermelho escuro (sombra da corda)
COR_CORDA       = "#d6a15e"   # bege/marrom — a corda em si
COR_CORDA_ESC   = "#a06a2c"   # marrom escuro — trança/sombra da corda
COR_NO          = "#fbbf24"   # nó central (marcador) amarelo
COR_TRILHO      = "#0b1220"   # canaleta onde a corda corre
# LIMITE_BARRA vem de game_logic (import acima): a corda vai de -LIMITE a +LIMITE.
FONTE           = "Segoe UI"  # fonte nativa do Windows, visual mais moderno
LIMITE_NOME     = 20          # máximo de caracteres no nome do jogador
FPS_MS          = 30          # intervalo entre quadros das animações (~33 fps)
DURACAO_PUXADA  = 0.8         # segundos da animação de puxada da corda
PAUSA_RESULTADO_MS = 2000     # tempo mostrando a resposta certa antes da tela final
INTERVALO_PING_S = 2          # segundos entre um PING (UDP) e o próximo


# ── Curvas de animação (t de 0 a 1) ─────────────────────────────────────────
# "Easing": recebem o progresso t (0 = início, 1 = fim) e devolvem quanto do
# movimento já deve ter acontecido. São fórmulas prontas e conhecidas
# (Robert Penner, easings.net); as constantes vêm dessas fórmulas.


# [Origem: IA]
def _ease_out_back(t: float) -> float:
    """Passa um pouco do destino e volta: efeito elástico."""
    c1 = 1.70158
    c3 = c1 + 1
    return 1 + c3 * (t - 1) ** 3 + c1 * (t - 1) ** 2


# [Origem: IA]
def _ease_out_bounce(t: float) -> float:
    """Cai e quica no chão (usado no título de derrota)."""
    n1, d1 = 7.5625, 2.75
    if t < 1 / d1:
        return n1 * t * t
    if t < 2 / d1:
        t -= 1.5 / d1
        return n1 * t * t + 0.75
    if t < 2.5 / d1:
        t -= 2.25 / d1
        return n1 * t * t + 0.9375
    t -= 2.625 / d1
    return n1 * t * t + 0.984375


# [Origem: IA 89% · autoral 11%]
class JanelaQuiz:
    # [Origem: IA 52% · autoral 48%]
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
        self._timer_contagem: str | None = None   # after-id do Tk
        self._segundos_restantes = 30
        self._segundos_totais = 30

        # ── Janela principal ──────────────────────────────────────────────
        self.janela = tk.Tk()
        self.janela.title("Quiz Cabo de Guerra — Redes")
        self.janela.resizable(False, False)
        self.janela.configure(bg=COR_FUNDO_EXTERNO)
        self.janela.protocol("WM_DELETE_WINDOW", self._ao_fechar)

        # Estado das animações
        self._fase_corda = 0.0        # relógio do balanço contínuo da corda
        self._pos_visual = 0.0        # posição do nó na tela (animada)
        self._anim_corda = None       # animação de puxada em andamento
        self._overlay = None          # tela final (vitória/derrota/empate)
        self._janela_fechada = False  # avisa a thread de ping para parar

        self._construir_ui()
        self._configurar_atalhos_teclado()
        self._centralizar_janela(820, 900)
        self._loop_corda()

    # ── Construção da UI ──────────────────────────────────────────────────

    # [Origem: IA 85% · autoral 15%]
    def _construir_ui(self):
        # ── Área rolável ──────────────────────────────────────────────────
        # Todo o conteúdo vive dentro de um Canvas rolável. Assim, em qualquer
        # resolução/DPI, se o conteúdo for maior que a janela aparece uma barra
        # de rolagem em vez de cortar elementos (pergunta, opções, histórico).
        moldura = tk.Frame(
            self.janela, bg=COR_FUNDO,
            highlightbackground=COR_BORDA, highlightthickness=1,
        )
        moldura.pack(fill="both", expand=True, padx=10, pady=8)

        self._scroll_canvas = tk.Canvas(moldura, bg=COR_FUNDO, highlightthickness=0)
        scrollbar = tk.Scrollbar(moldura, orient="vertical",
                                 command=self._scroll_canvas.yview)
        self._scroll_canvas.configure(yscrollcommand=scrollbar.set)

        # A scrollbar só é exibida quando o conteúdo não cabe (ver abaixo).
        self._scrollbar = scrollbar
        self._scroll_canvas.pack(side="left", fill="both", expand=True)

        # frame_conteudo é o container real dos widgets, dentro do canvas.
        self.frame_conteudo = tk.Frame(self._scroll_canvas, bg=COR_FUNDO)
        self._janela_conteudo = self._scroll_canvas.create_window(
            (0, 0), window=self.frame_conteudo, anchor="nw",
        )

        # Mantém a scrollregion e a largura do conteúdo em dia.
        def _ajustar_scrollbar():
            # Mostra a barra de rolagem apenas se o conteúdo for maior que a área visível.
            precisa = self.frame_conteudo.winfo_reqheight() > self._scroll_canvas.winfo_height()
            visivel = self._scrollbar.winfo_ismapped()
            if precisa and not visivel:
                self._scrollbar.pack(side="right", fill="y", before=self._scroll_canvas)
            elif not precisa and visivel:
                self._scrollbar.pack_forget()
                self._scroll_canvas.yview_moveto(0)

        def _ao_configurar_conteudo(_evento):
            self._scroll_canvas.configure(scrollregion=self._scroll_canvas.bbox("all"))
            _ajustar_scrollbar()

        def _ao_configurar_canvas(evento):
            # Faz o frame interno ter a mesma largura do canvas (conteúdo centralizado).
            self._scroll_canvas.itemconfigure(self._janela_conteudo, width=evento.width)
            _ajustar_scrollbar()

        self.frame_conteudo.bind("<Configure>", _ao_configurar_conteudo)
        self._scroll_canvas.bind("<Configure>", _ao_configurar_canvas)

        # Rolagem com a roda do mouse.
        def _ao_rolar(evento):
            self._scroll_canvas.yview_scroll(int(-1 * (evento.delta / 120)), "units")

        self._scroll_canvas.bind_all("<MouseWheel>", _ao_rolar)

        # ── Cabeçalho com título ──────────────────────────────────────────
        cabecalho = tk.Frame(self.frame_conteudo, bg=COR_CARD_TOPO)
        cabecalho.pack(fill="x")
        tk.Label(
            cabecalho, text="⚔  QUIZ CABO DE GUERRA  ⚔",
            font=(FONTE, 18, "bold"), fg=COR_TEXTO, bg=COR_CARD_TOPO,
        ).pack(pady=(8, 0))
        tk.Label(
            cabecalho, text="Duelo de redes em tempo real",
            font=(FONTE, 9), fg=COR_ACENTO, bg=COR_CARD_TOPO,
        ).pack(pady=(0, 6))

        # Latência medida por PING/PONG via UDP (canto superior direito).
        # place() posiciona por cima do cabeçalho sem ocupar altura extra.
        self.rotulo_ping = tk.Label(
            cabecalho, text="📶 Ping: —", font=(FONTE, 9, "bold"),
            fg=COR_STATUS, bg=COR_CARD_TOPO,
        )
        self.rotulo_ping.place(relx=1.0, x=-12, y=8, anchor="ne")

        # Faixa de destaque sob o cabeçalho: metade azul (A), metade vermelha (B),
        # antecipando os dois "territórios" do cabo de guerra.
        self.faixa_topo = tk.Canvas(self.frame_conteudo, height=3, bg=COR_FUNDO,
                                    highlightthickness=0)
        self.faixa_topo.pack(fill="x")
        self.faixa_topo.bind("<Configure>", self._desenhar_faixa_topo)

        # Status em formato de "pílula" (fundo próprio, cantos visuais pelo padding)
        self.rotulo_status = tk.Label(
            self.frame_conteudo, text="Digite seu nome e clique em Conectar",
            font=(FONTE, 10), fg=COR_TEXTO, bg=COR_PAINEL, padx=14, pady=2,
        )
        self.rotulo_status.pack(pady=(6, 5))

        # ── Placar dos jogadores (cartões lado a lado) ────────────────────
        frame_placar = tk.Frame(self.frame_conteudo, bg=COR_FUNDO)
        frame_placar.pack(fill="x", padx=34, pady=(0, 4))
        frame_placar.columnconfigure(0, weight=1, uniform="jog")
        frame_placar.columnconfigure(1, weight=0)
        frame_placar.columnconfigure(2, weight=1, uniform="jog")

        # Cartão do jogador A (esquerda, azul)
        card_a = tk.Frame(frame_placar, bg=COR_PAINEL, highlightbackground=COR_BARRA_A,
                          highlightthickness=2)
        card_a.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self.rotulo_nome_a = tk.Label(
            card_a, text="Jogador A", font=(FONTE, 11, "bold"),
            fg=COR_BARRA_A, bg=COR_PAINEL, anchor="center",
        )
        self.rotulo_nome_a.pack(pady=(4, 0), padx=10)
        self.rotulo_pts_a = tk.Label(
            card_a, text="0", font=(FONTE, 18, "bold"),
            fg=COR_TEXTO, bg=COR_PAINEL,
        )
        self.rotulo_pts_a.pack(pady=(0, 4))

        # "VS" central
        tk.Label(
            frame_placar, text="VS", font=(FONTE, 12, "bold"),
            fg=COR_STATUS, bg=COR_FUNDO,
        ).grid(row=0, column=1, padx=6)

        # Cartão do jogador B (direita, vermelho)
        card_b = tk.Frame(frame_placar, bg=COR_PAINEL, highlightbackground=COR_BARRA_B,
                          highlightthickness=2)
        card_b.grid(row=0, column=2, sticky="ew", padx=(6, 0))
        self.rotulo_nome_b = tk.Label(
            card_b, text="Jogador B", font=(FONTE, 11, "bold"),
            fg=COR_BARRA_B, bg=COR_PAINEL, anchor="center",
        )
        self.rotulo_nome_b.pack(pady=(4, 0), padx=10)
        self.rotulo_pts_b = tk.Label(
            card_b, text="0", font=(FONTE, 18, "bold"),
            fg=COR_TEXTO, bg=COR_PAINEL,
        )
        self.rotulo_pts_b.pack(pady=(0, 4))

        # Referências para destacar o cartão de quem está na frente.
        self.card_a, self.card_b = card_a, card_b

        # ── Corda do cabo de guerra ───────────────────────────────────────
        frame_barra = tk.Frame(self.frame_conteudo, bg=COR_FUNDO)
        frame_barra.pack(fill="x", padx=34, pady=(4, 2))

        self.canvas_barra = tk.Canvas(
            frame_barra, width=620, height=58,
            bg=COR_FUNDO, highlightthickness=0,
        )
        self.canvas_barra.pack(fill="x")
        self._ultima_barra = (0, {})   # guarda o último estado para redesenhar
        self.canvas_barra.bind("<Configure>", self._ao_redimensionar_barra)

        # Rodada, centralizado abaixo da corda
        self.rotulo_rodada = tk.Label(
            self.frame_conteudo, text="Rodada — / 10",
            font=(FONTE, 10, "bold"), fg=COR_STATUS, bg=COR_FUNDO,
        )
        self.rotulo_rodada.pack(pady=(0, 2))

        self._desenhar_barra(0, {})

        # ── Pergunta (painel destacado) ───────────────────────────────────
        painel_pergunta = tk.Frame(
            self.frame_conteudo, bg=COR_PAINEL,
            highlightbackground=COR_BORDA, highlightthickness=1,
        )
        painel_pergunta.pack(pady=(4, 4), padx=28, fill="x")
        self.rotulo_pergunta = tk.Label(
            painel_pergunta, text="A pergunta aparecerá aqui quando a partida começar.",
            wraplength=640, justify="center",
            font=(FONTE, 14, "bold"), fg=COR_PERGUNTA, bg=COR_PAINEL,
        )
        self.rotulo_pergunta.pack(pady=8, padx=16)

        # Tempo restante
        self.rotulo_tempo = tk.Label(
            self.frame_conteudo, text="",
            font=(FONTE, 12, "bold"), fg=COR_TEMPO, bg=COR_FUNDO,
        )
        self.rotulo_tempo.pack(pady=(0, 3))

        # Barra de progresso do tempo restante
        self.canvas_tempo = tk.Canvas(
            self.frame_conteudo, width=320, height=10, bg=COR_FUNDO, highlightthickness=0,
        )
        self.canvas_tempo.pack(pady=(0, 8))

        # ── Opções ────────────────────────────────────────────────────────
        self.opcoes_var = tk.StringVar(self.janela, value="")
        self.frame_opcoes = tk.Frame(self.frame_conteudo, bg=COR_FUNDO)
        self.frame_opcoes.pack(pady=(0, 8))
        self._botoes_opcao: list[tk.Button] = []

        # ── Campo de nome do jogador ──────────────────────────────────────
        # Guardamos o frame em self para poder escondê-lo quando o jogo começa.
        self.frame_nome = tk.Frame(self.frame_conteudo, bg=COR_FUNDO)
        self.frame_nome.pack(pady=(4, 8))
        frame_nome = self.frame_nome

        tk.Label(
            frame_nome, text="Seu nome:",
            font=(FONTE, 10), fg=COR_STATUS, bg=COR_FUNDO,
        ).grid(row=0, column=0, padx=(0, 8))

        # Campo onde o jogador digita o apelido antes de conectar.
        # Usa um StringVar com trace para habilitar/desabilitar o botão Conectar
        # conforme o campo tem ou não um nome válido.
        self.var_nome = tk.StringVar(value=self.apelido or "")
        self.var_nome.trace_add("write", lambda *_: self._atualizar_estado_botao_conectar())
        self.entrada_nome = tk.Entry(
            frame_nome, font=(FONTE, 11), width=22,
            textvariable=self.var_nome,
            bg=COR_BORDA, fg=COR_TEXTO, insertbackground=COR_TEXTO,
            relief="flat", justify="center",
        )
        self.entrada_nome.grid(row=0, column=1, ipady=4)
        # Contador "n/20" ao lado do campo (fica vermelho quando passa do limite).
        self.rotulo_contador_nome = tk.Label(
            frame_nome, text="", font=(FONTE, 9), fg=COR_STATUS, bg=COR_FUNDO, width=6,
        )
        self.rotulo_contador_nome.grid(row=0, column=2, padx=(8, 0))
        # Enter no campo de nome também conecta (se houver nome válido).
        # "break" impede que o Enter propague para o atalho global da janela
        # (que enviaria resposta e mostraria o alerta "Nenhuma pergunta ativa").
        self.entrada_nome.bind("<Return>", lambda e: (self.conectar(), "break")[1])
        # Foco automático no campo para o jogador já começar digitando.
        self.entrada_nome.focus_set()

        # ── Botões de ação ────────────────────────────────────────────────
        frame_btns = tk.Frame(self.frame_conteudo, bg=COR_FUNDO)
        frame_btns.pack(pady=(4, 4))

        self.botao_conectar = tk.Button(
            frame_btns, text="Conectar",
            command=self.conectar,
            bg=COR_BTN_CONN, fg="white", activebackground="#1d4ed8",
            font=(FONTE, 11, "bold"), width=16, height=1, relief="flat",
            cursor="hand2", pady=6,
        )
        self.botao_conectar.grid(row=0, column=0, padx=10)
        self._aplicar_efeito_hover(self.botao_conectar, COR_BTN_CONN, "#1e40af")
        # Estado inicial do botão depende de já haver um nome preenchido.
        self._atualizar_estado_botao_conectar()

        self.botao_enviar = tk.Button(
            frame_btns, text="Enviar resposta",
            command=self.enviar_resposta,
            bg=COR_BTN_OFF, fg="#64748b", activebackground="#15803d",
            font=(FONTE, 11, "bold"), width=16, height=1, relief="flat",
            state="disabled", cursor="hand2", pady=6,
        )
        self.botao_enviar.grid(row=0, column=1, padx=10)
        self._aplicar_efeito_hover(self.botao_enviar, COR_BTN_RESP, "#15803d")

        # ── Histórico da partida ──────────────────────────────────────────
        frame_historico = tk.Frame(self.frame_conteudo, bg=COR_FUNDO)
        frame_historico.pack(pady=(4, 8), padx=24, fill="x")

        tk.Label(
            frame_historico, text="Histórico da partida",
            font=(FONTE, 9, "bold"), fg=COR_STATUS, bg=COR_FUNDO,
        ).pack(anchor="w")

        self.texto_historico = tk.Text(
            frame_historico, height=3, bg=COR_BORDA, fg=COR_TEXTO,
            font=("Consolas", 9), relief="flat", state="disabled", wrap="word",
            padx=8, pady=6,
        )
        self.texto_historico.pack(fill="x", pady=(4, 0))

    # [Origem: IA 82% · autoral 18%]
    def _centralizar_janela(self, largura: int, altura: int):
        """
        Centraliza a janela na tela e limita a altura ao espaço realmente
        disponível. Em telas menores (ou com barra de tarefas/DPI), pedir
        900px de altura faz a base da janela ficar escondida; por isso
        limitamos a altura à área útil da tela, deixando uma folga para a
        barra de tarefas.
        """
        self.janela.update_idletasks()
        tela_larg = self.janela.winfo_screenwidth()
        tela_alt = self.janela.winfo_screenheight()

        # Folga para a barra de tarefas + moldura da janela (~80px).
        alt_max = tela_alt - 80
        altura = min(altura, alt_max)
        largura = min(largura, tela_larg - 40)

        x = (tela_larg // 2) - (largura // 2)
        y = max(0, (tela_alt // 2) - (altura // 2) - 20)
        self.janela.geometry(f"{largura}x{altura}+{x}+{y}")

    # [Origem: autoral]
    def _aplicar_efeito_hover(self, botao: tk.Button, cor_normal: str, cor_hover: str):
        """Realça um botão ao passar o mouse, somente enquanto ele estiver habilitado."""
        def ao_entrar(_evento):
            if str(botao["state"]) == "normal":
                botao.config(bg=cor_hover)

        def ao_sair(_evento):
            if str(botao["state"]) == "normal":
                botao.config(bg=cor_normal)

        botao.bind("<Enter>", ao_entrar)
        botao.bind("<Leave>", ao_sair)

    # [Origem: autoral]
    def _configurar_atalhos_teclado(self):
        """Permite escolher a opção com as teclas numéricas e enviar com Enter."""
        self.janela.bind("<Return>", lambda _evento: self.enviar_resposta())
        for numero in range(1, 10):
            self.janela.bind(str(numero), self._selecionar_opcao_por_indice)

    # [Origem: autoral 78% · IA 22%]
    def _selecionar_opcao_por_indice(self, evento):
        try:
            indice = int(evento.char) - 1
        except (TypeError, ValueError):
            return
        botoes = getattr(self, "_botoes_opcao", [])
        if 0 <= indice < len(botoes) and str(botoes[indice]["state"]) == "normal":
            valor = getattr(botoes[indice], "_opcao_valor", botoes[indice]["text"])
            self._selecionar_opcao(valor)

    # [Origem: autoral]
    def _retangulo_arredondado(self, canvas: tk.Canvas, x1, y1, x2, y2, raio, **kwargs):
        """Desenha (e retorna) um retângulo de cantos arredondados no canvas."""
        raio = max(0, min(raio, (x2 - x1) / 2, (y2 - y1) / 2))
        pontos = [
            x1 + raio, y1, x2 - raio, y1, x2, y1, x2, y1 + raio,
            x2, y2 - raio, x2, y2, x2 - raio, y2, x1 + raio, y2,
            x1, y2, x1, y2 - raio, x1, y1 + raio, x1, y1,
        ]
        return canvas.create_polygon(pontos, smooth=True, **kwargs)

    # ── Barra visual ──────────────────────────────────────────────────────

    # [Origem: IA]
    def _ao_redimensionar_barra(self, _evento):
        """Redesenha a corda quando o canvas muda de tamanho (mantém centralização)."""
        self._renderizar_corda()

    # [Origem: IA]
    def _desenhar_barra(self, posicao: int, pontuacao: dict):
        """
        Atualiza o estado da CORDA do cabo de guerra e o placar dos cartões.

        Convenção alinhada com game_logic.EstadoJogo:
          posicao > 0 → jogador_a (esquerda/AZUL) na frente → nó desliza p/ ESQUERDA
          posicao < 0 → jogador_b (direita/VERMELHO) na frente → nó desliza p/ DIREITA
          posicao == 0 → nó no centro (empate)

        Se a posição mudou, dispara a animação de "puxada": o nó desliza com
        efeito elástico, o boneco do lado que pontuou se inclina e dá passos
        para trás e a corda vibra. O desenho em si fica em _renderizar_corda,
        chamado a cada quadro pelo loop de animação (_loop_corda).
        """
        anterior = getattr(self, "_ultima_barra", (0, {}))[0]
        self._ultima_barra = (posicao, pontuacao)

        if posicao != anterior:
            self._anim_corda = {
                "de": getattr(self, "_pos_visual", float(anterior)),
                "para": float(posicao),
                # Posição subiu → A (esquerda) puxou; desceu → B (direita) puxou.
                "lado": -1 if posicao > anterior else 1,
                "t0": time.monotonic(),
            }
        elif getattr(self, "_anim_corda", None) is None:
            self._pos_visual = float(posicao)

        # ── Atualiza os números do placar nos cartões ─────────────────────
        jogadores = list(pontuacao.keys())
        pts_a = pontuacao.get(jogadores[0], 0) if jogadores else 0
        pts_b = pontuacao.get(jogadores[1], 0) if len(jogadores) > 1 else 0
        self.rotulo_pts_a.config(text=str(pts_a))
        self.rotulo_pts_b.config(text=str(pts_b))
        self._destacar_lider(posicao)
        self._renderizar_corda()

    # [Origem: IA]
    def _loop_corda(self):
        """Loop contínuo (~33 fps): balanço suave da corda + animação de puxada."""
        try:
            self._fase_corda = getattr(self, "_fase_corda", 0.0) + 0.12
            # Com a tela final aberta a corda fica escondida: não gasta CPU redesenhando.
            if getattr(self, "_overlay", None) is None:
                self._renderizar_corda()
            self.janela.after(FPS_MS, self._loop_corda)
        except tk.TclError:
            return  # janela fechada

    # [Origem: IA]
    def _renderizar_corda(self):
        """Desenha um quadro da corda, dos bonecos e do nó (estado atual + animação)."""
        c = getattr(self, "canvas_barra", None)
        if c is None:
            return
        posicao = getattr(self, "_ultima_barra", (0, {}))[0]
        fase = getattr(self, "_fase_corda", 0.0)

        # Progresso da animação de puxada (se houver)
        lado_puxando, forca = 0, 0.0
        anim = getattr(self, "_anim_corda", None)
        if anim:
            t = (time.monotonic() - anim["t0"]) / DURACAO_PUXADA
            if t >= 1.0:
                self._anim_corda = None
                self._pos_visual = anim["para"]
            else:
                progresso = _ease_out_back(t)   # passa um pouco do ponto e volta (elástico)
                self._pos_visual = anim["de"] + (anim["para"] - anim["de"]) * progresso
                lado_puxando = anim["lado"]
                forca = math.sin(math.pi * t)   # esforço: 0 → 1 → 0
        pos = getattr(self, "_pos_visual", float(posicao))

        c.delete("all")

        W = c.winfo_width()
        if W <= 1:
            W = int(c["width"])
        H = c.winfo_height()
        if H <= 1:
            H = int(c["height"])
        cx = W / 2.0
        cy = H / 2.0
        margem = 38                      # espaço nas laterais para os bonecos puxando
        alcance = cx - margem            # deslocamento máximo do nó a partir do centro

        # ── Territórios (faixas de fundo dos dois lados) ──────────────────
        # Lado esquerdo = território de A (azul), direito = de B (vermelho).
        self._retangulo_arredondado(c, 4, cy - 20, cx, cy + 20, 10,
                                     fill=COR_BARRA_A_ESC, outline="")
        self._retangulo_arredondado(c, cx, cy - 20, W - 4, cy + 20, 10,
                                     fill=COR_BARRA_B_ESC, outline="")

        # Linha central (limite dos territórios)
        c.create_line(cx, cy - 22, cx, cy + 22, fill="#e2e8f0", width=2)

        # Marcas de limite (onde a vitória acontece: |posicao| == LIMITE_BARRA)
        for lado in (-1, 1):
            lx = cx + lado * alcance
            c.create_line(lx, cy - 18, lx, cy + 18, fill="#facc15", width=2, dash=(3, 3))

        # ── Posição do nó (usa a posição VISUAL, que é animada) ───────────
        # Permite passar levemente do limite durante o efeito elástico.
        frac = max(-1.08, min(1.08, pos / LIMITE_BARRA))
        # pos > 0 (A vence) → nó vai para a ESQUERDA → x menor que o centro
        no_x = cx - frac * alcance

        # Quem puxa dá um "tranco": as mãos recuam alguns pixels para fora.
        recuo = 6 * forca
        mao_a = margem - (recuo if lado_puxando == -1 else 0)
        mao_b = W - margem + (recuo if lado_puxando == 1 else 0)

        # ── A corda: balanço leve sempre + vibração forte durante a puxada ─
        amp = 1.2 + 4.0 * forca
        self._desenhar_segmento_corda(c, mao_a, no_x, cy, amp, fase)
        self._desenhar_segmento_corda(c, mao_b, no_x, cy, amp, fase + 1.7)

        # ── Bonecos: respiram sempre; quem pontuou se inclina e dá passos ─
        self._desenhar_puxador(c, mao_a, cy, lado=-1, cor=COR_BARRA_A,
                               esforco=forca if lado_puxando == -1 else 0.0, fase=fase)
        self._desenhar_puxador(c, mao_b, cy, lado=1, cor=COR_BARRA_B,
                               esforco=forca if lado_puxando == 1 else 0.0, fase=fase + 1.3)

        # Poeira levantada nos pés + grito "PUXA!" de quem está puxando
        if forca > 0.05:
            mao = mao_a if lado_puxando == -1 else mao_b
            cor = COR_BARRA_A if lado_puxando == -1 else COR_BARRA_B
            for i in range(3):
                dx = -lado_puxando * (4 + i * 6) * (0.5 + forca)
                r = 1.5 + i * 0.8 * forca
                px, py = mao + dx, cy + 20 - i * 2 * forca
                c.create_oval(px - r, py - r, px + r, py + r, fill="#94a3b8", outline="")
            c.create_text(mao + lado_puxando * 16, cy - 23 - 3 * forca, text="PUXA!",
                          fill=cor, font=(FONTE, 8, "bold"))

        # ── O nó central (pulsa durante a puxada) ─────────────────────────
        if posicao > 0:
            cor_halo = COR_BARRA_A
        elif posicao < 0:
            cor_halo = COR_BARRA_B
        else:
            cor_halo = COR_NO
        r_no = 10 + 3 * forca
        r_halo = 15 + 5 * forca
        c.create_oval(no_x - r_halo, cy - r_halo, no_x + r_halo, cy + r_halo,
                      fill="", outline=cor_halo, width=2)
        c.create_oval(no_x - r_no, cy - r_no, no_x + r_no, cy + r_no,
                      fill=COR_NO, outline=COR_CORDA_ESC, width=2)
        c.create_oval(no_x - 5, cy - 7, no_x - 1, cy - 3, fill="#fff7d6", outline="")

        # ── Etiqueta de vantagem (quantas rodadas de frente) ──────────────
        vantagem = abs(posicao)
        if vantagem > 0 and forca < 0.05:
            cor_txt = COR_BARRA_A if posicao > 0 else COR_BARRA_B
            c.create_text(no_x, cy - 26, text=f"+{vantagem}", fill=cor_txt,
                          font=(FONTE, 10, "bold"))

    # [Origem: IA]
    def _destacar_lider(self, posicao: int):
        """Dá um leve brilho (fundo tingido + borda grossa) ao cartão de quem está na frente."""
        card_a = getattr(self, "card_a", None)
        card_b = getattr(self, "card_b", None)
        if card_a is None or card_b is None:
            return
        estilos = {
            card_a: ("#1a2b4d" if posicao > 0 else COR_PAINEL, 3 if posicao > 0 else 2),
            card_b: ("#3a1a24" if posicao < 0 else COR_PAINEL, 3 if posicao < 0 else 2),
        }
        for card, (fundo, borda) in estilos.items():
            card.config(bg=fundo, highlightthickness=borda)
            for filho in card.winfo_children():
                filho.config(bg=fundo)

    # [Origem: IA]
    def _desenhar_puxador(self, c: tk.Canvas, mao_x, cy, lado: int, cor: str,
                          esforco: float = 0.0, fase: float = 0.0, escala: float = 1.0):
        """
        Desenha um boneco puxando a corda. mao_x é onde as mãos seguram a corda;
        lado=-1 → boneco à esquerda (inclina para a esquerda), lado=+1 → à direita.

        esforco (0..1): quanto o boneco está puxando agora — ele deita mais para
        trás e alterna as pernas (passos para trás). fase: relógio da animação,
        usado para a "respiração" leve mesmo parado. escala: tamanho (tela final).
        """
        s = escala
        respira = math.sin(fase * 0.8) * 1.0          # balanço leve do tronco
        inclina = 6 * esforco                          # deita para trás ao puxar
        passo = math.sin(fase * 3.0) * 4 * esforco     # pernas alternando

        def p(dx, dy):
            # dx positivo = para fora (longe do centro)
            return (mao_x + lado * dx * s, cy + dy * s)

        cabeca = p(22 + inclina + respira, -15 + inclina * 0.6)
        ombro = p(18 + inclina + respira * 0.8, -7 + inclina * 0.4)
        quadril = p(9 + inclina * 0.5, 7)
        mao = p(0, 0)
        esp = max(1, round(3 * s))
        # Braços esticados até a corda
        c.create_line(*ombro, *mao, fill=cor, width=esp, capstyle="round")
        # Tronco inclinado para trás
        c.create_line(*ombro, *quadril, fill=cor, width=esp + 1, capstyle="round")
        # Pernas apoiadas à frente (em direção ao centro), alternando ao puxar
        c.create_line(*quadril, *p(-2 + passo, 21), fill=cor, width=esp, capstyle="round")
        c.create_line(*quadril, *p(6 - passo, 21), fill=cor, width=esp, capstyle="round")
        # Cabeça
        r = 5 * s
        c.create_oval(cabeca[0] - r, cabeca[1] - r, cabeca[0] + r, cabeca[1] + r,
                      fill=cor, outline="#0b1220", width=1)

    # [Origem: IA]
    def _desenhar_faixa_topo(self, _evento=None):
        """Faixa fina sob o cabeçalho: azul à esquerda, vermelha à direita."""
        c = self.faixa_topo
        c.delete("all")
        w = c.winfo_width()
        c.create_rectangle(0, 0, w / 2, 3, fill=COR_BARRA_A, outline="")
        c.create_rectangle(w / 2, 0, w, 3, fill=COR_BARRA_B, outline="")

    # [Origem: IA]
    def _desenhar_segmento_corda(self, c: tk.Canvas, x_mao, x_no, cy,
                                 amplitude: float = 0.0, fase: float = 0.0):
        """
        Desenha a corda entre as mãos de um boneco (x_mao) e o nó (x_no), com
        aparência trançada: base grossa marrom + traços diagonais (os fios).

        A corda ondula: uma onda que "corre" pela corda (fase) com amplitude
        zero nas pontas (presas na mão e no nó) e máxima no meio.
        """
        if abs(x_no - x_mao) < 1:
            return
        n = max(2, int(abs(x_no - x_mao) // 8))
        pontos = []
        for i in range(n + 1):
            t = i / n
            x = x_mao + (x_no - x_mao) * t
            y = cy + amplitude * math.sin(math.pi * t) * math.sin(fase + t * 6.0)
            pontos.append((x, y))
        linha = [v for ponto in pontos for v in ponto]
        sombra = [v + 2 if k % 2 else v for k, v in enumerate(linha)]
        c.create_line(*sombra, fill=COR_CORDA_ESC, width=10, capstyle="round", smooth=True)
        c.create_line(*linha, fill=COR_CORDA, width=8, capstyle="round", smooth=True)

        # Fios trançados acompanhando a ondulação
        sinal = 1 if x_no >= x_mao else -1
        for x, y in pontos[:-1]:
            c.create_line(x, y - 3, x + sinal * 5, y + 3, fill=COR_CORDA_ESC, width=1)

    # ── Contagem regressiva ───────────────────────────────────────────────

    # [Origem: IA 80% · autoral 20%]
    def _iniciar_contagem(self, segundos: int):
        self._parar_contagem()
        self._segundos_totais = max(segundos, 1)
        self._segundos_restantes = segundos
        self._tick_contagem()

    # [Origem: IA 83% · autoral 17%]
    def _tick_contagem(self):
        if self._segundos_restantes > 0:
            self.rotulo_tempo.config(
                text=f"⏱ Tempo: {self._segundos_restantes}s",
                fg=COR_TEMPO if self._segundos_restantes > 5 else "#f87171",
            )
            self._atualizar_barra_tempo(self._segundos_restantes / self._segundos_totais)
            self._segundos_restantes -= 1
            self._timer_contagem = self.janela.after(1000, self._tick_contagem)
        else:
            self.rotulo_tempo.config(text="⏱ Tempo esgotado!", fg="#f87171")
            self._atualizar_barra_tempo(0)

    # [Origem: IA]
    def _parar_contagem(self):
        if self._timer_contagem is not None:
            self.janela.after_cancel(self._timer_contagem)
            self._timer_contagem = None

    # [Origem: autoral 62% · IA 38%]
    def _atualizar_barra_tempo(self, fracao: float):
        """Redesenha a barra de progresso do tempo restante (fração de 0.0 a 1.0)."""
        canvas = getattr(self, "canvas_tempo", None)
        if canvas is None:
            return
        largura_total = 320
        altura = 10
        canvas.delete("all")
        self._retangulo_arredondado(canvas, 0, 0, largura_total, altura, 5, fill=COR_TRILHO, outline="")
        largura = max(0, int(largura_total * max(0.0, min(1.0, fracao))))
        if largura >= altura:
            cor = "#22c55e" if fracao > 0.5 else ("#fbbf24" if fracao > 0.2 else "#ef4444")
            self._retangulo_arredondado(canvas, 0, 0, largura, altura, 5, fill=cor, outline="")

    # ── Opções de resposta ────────────────────────────────────────────────

    # [Origem: IA]
    def _construir_opcoes(self, opcoes: list[str]):
        # Remove botões antigos
        for btn in self._botoes_opcao:
            btn.destroy()
        self._botoes_opcao.clear()

        self.opcoes_var.set("")
        for i, opcao in enumerate(opcoes, start=1):
            # Prefixo com o número do atalho de teclado (1-4)
            btn = tk.Button(
                self.frame_opcoes, text=f"  {i}   {opcao}",
                command=lambda o=opcao: self._selecionar_opcao(o),
                bg=COR_OPCAO, fg=COR_TEXTO,
                activebackground=COR_OPCAO_H, activeforeground=COR_TEXTO,
                font=(FONTE, 12), width=34, height=1, relief="flat",
                anchor="w", padx=12, pady=4, cursor="hand2",
                borderwidth=0,
            )
            btn.pack(pady=2)
            # Guarda a opção "limpa" (sem o número) para comparação de resposta.
            btn._opcao_valor = opcao
            self._botoes_opcao.append(btn)
            # Hover: só realça se o botão estiver ativo e não for a resposta enviada.
            self._aplicar_hover_opcao(btn)

    # [Origem: IA]
    def _aplicar_hover_opcao(self, btn: tk.Button):
        """Realce ao passar o mouse sobre um botão de opção (se habilitado)."""
        def entrar(_e):
            if str(btn["state"]) == "normal" and btn["bg"] == COR_OPCAO:
                btn.config(bg=COR_OPCAO_H)
        def sair(_e):
            if str(btn["state"]) == "normal" and btn["bg"] == COR_OPCAO_H:
                btn.config(bg=COR_OPCAO)
        btn.bind("<Enter>", entrar)
        btn.bind("<Leave>", sair)

    # [Origem: IA]
    def _selecionar_opcao(self, opcao: str):
        if self.resposta_enviada:
            return
        self.opcoes_var.set(opcao)
        # Destaca o botão selecionado (compara pelo valor limpo, não pelo texto).
        for btn in self._botoes_opcao:
            if getattr(btn, "_opcao_valor", btn["text"]) == opcao:
                btn.config(bg=COR_OPCAO_SEL, fg="white")
            else:
                btn.config(bg=COR_OPCAO, fg=COR_TEXTO)

    # [Origem: IA]
    def _desativar_opcoes(self):
        for btn in getattr(self, "_botoes_opcao", []):
            btn.config(state="disabled", bg=COR_OPCAO, fg="#475569")
        botao_enviar = getattr(self, "botao_enviar", None)
        if botao_enviar:
            try:
                botao_enviar.config(state="disabled", bg=COR_BTN_OFF, fg="#64748b")
            except Exception:
                pass

    # [Origem: IA]
    def _ativar_opcoes(self):
        for btn in self._botoes_opcao:
            btn.config(state="normal", bg=COR_OPCAO, fg=COR_TEXTO)
        self.botao_enviar.config(state="normal", bg=COR_BTN_RESP, fg="white")

    # ── Conexão ───────────────────────────────────────────────────────────

    # [Origem: IA]
    def _esconder_campo_nome(self):
        """Esconde o campo de nome (chamado quando a partida começa)."""
        frame = getattr(self, "frame_nome", None)
        if frame is not None:
            frame.pack_forget()

    # [Origem: IA]
    def _atualizar_estado_botao_conectar(self):
        """
        Habilita o botão Conectar apenas quando há um nome válido no campo.
        Enquanto o campo estiver vazio (ou só espaços), o botão fica desabilitado.
        Não faz nada se o jogador já está conectado (o botão tem outro papel aí).
        """
        nome = self.var_nome.get().strip() if hasattr(self, "var_nome") else ""
        contador = getattr(self, "rotulo_contador_nome", None)
        if contador is not None:
            contador.config(
                text=f"{len(nome)}/{LIMITE_NOME}",
                fg="#f87171" if len(nome) > LIMITE_NOME else COR_STATUS,
            )
        botao = getattr(self, "botao_conectar", None)
        if botao is None or getattr(self, "conectado", False):
            return
        if nome:
            botao.config(state="normal", bg=COR_BTN_CONN, cursor="hand2")
        else:
            botao.config(state="disabled", bg=COR_BTN_OFF, cursor="arrow")

    # [Origem: IA 77% · autoral 23%]
    def conectar(self):
        if self.conectado:
            return

        # Nome é OBRIGATÓRIO: sem nome, não conecta.
        nome_digitado = self.var_nome.get().strip() if hasattr(self, "var_nome") else ""
        if not nome_digitado:
            messagebox.showinfo("Escolha um nome", "Digite seu nome antes de conectar.")
            self.entrada_nome.focus_set()
            return
        if len(nome_digitado) > LIMITE_NOME:
            messagebox.showwarning(
                "Nome inválido",
                f"O nome pode ter no máximo {LIMITE_NOME} caracteres "
                f"(o seu tem {len(nome_digitado)}).\n\nDigite outro nome.",
            )
            # Seleciona o texto para o jogador já digitar por cima.
            self.entrada_nome.focus_set()
            self.entrada_nome.select_range(0, "end")
            return
        self.apelido = nome_digitado

        try:
            self.cliente.conectar()
            self.conectado = True
            self.botao_conectar.config(
                state="disabled", text="✓ Conectado", bg="#064e3b",
            )
            # Trava o campo de nome enquanto conectado (o nome já foi enviado).
            if hasattr(self, "entrada_nome"):
                self.entrada_nome.config(state="disabled")
            self.cliente.enviar_entrada(self.id_jogador, self.apelido)
            self._set_status("Conectado. Aguardando o adversário entrar na sala…")
        except Exception as erro:
            messagebox.showerror("Erro de conexão", str(erro))
            return

        threading.Thread(target=self.escutar_servidor, daemon=True).start()
        # Uma única thread de ping para toda a vida da janela (ela sempre usa
        # o self.cliente atual, então continua valendo após reconectar).
        if not getattr(self, "_ping_ativo", False):
            self._ping_ativo = True
            threading.Thread(target=self._loop_ping, daemon=True).start()

    # ── Latência (PING/PONG via UDP) ──────────────────────────────────────

    # [Origem: IA]
    def _loop_ping(self):
        """
        Roda numa thread própria: a cada INTERVALO_PING_S segundos envia um PING
        (UDP) ao servidor e espera o PONG para medir a latência (RTT). O
        resultado vai para a tela pela thread do Tk (janela.after).
        """
        while not self._janela_fechada:
            if self.conectado:
                rtt = self.cliente.medir_latencia(self.id_jogador, timeout=1.0)
            else:
                rtt = "desconectado"
            try:
                self.janela.after(0, self._mostrar_ping, rtt)
            except (RuntimeError, tk.TclError):
                pass  # Tk ocupado/encerrando: tenta de novo na próxima volta
            time.sleep(INTERVALO_PING_S)

    # [Origem: IA]
    def _mostrar_ping(self, rtt):
        """Atualiza o indicador de ping: verde (bom), amarelo (médio), vermelho (ruim)."""
        if rtt == "desconectado":
            self.rotulo_ping.config(text="📶 Ping: —", fg=COR_STATUS)
        elif rtt is None:
            # O PONG não voltou dentro do prazo (UDP pode perder pacotes).
            self.rotulo_ping.config(text="📶 Ping: sem resposta", fg="#f87171")
        else:
            cor = "#4ade80" if rtt < 80 else (COR_TEMPO if rtt < 200 else "#f87171")
            # Na rede local o RTT fica abaixo de 1 ms: mostra 1 casa decimal.
            if rtt < 0.1:
                valor = "<0.1"
            elif rtt < 10:
                valor = f"{rtt:.1f}"
            else:
                valor = f"{rtt:.0f}"
            self.rotulo_ping.config(text=f"📶 Ping: {valor} ms", fg=cor)

    # ── Loop de escuta (thread separada) ─────────────────────────────────

    # [Origem: IA 83% · autoral 17%]
    def escutar_servidor(self):
        """
        Roda numa thread separada: fica esperando mensagens do servidor (recv
        bloqueia) sem congelar a janela. Cada mensagem é repassada para a
        thread do Tk com janela.after(0, handler, msg), porque widgets Tk não
        podem ser alterados de outra thread.
        """
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

    # [Origem: IA]
    def _conexao_viva(self) -> bool:
        """Verifica se o socket TCP ainda está conectado ao servidor."""
        try:
            self.cliente.socket_tcp.getpeername()
            return True
        except OSError:
            return False

    # [Origem: IA]
    def _on_conexao_perdida(self):
        """Chamado na thread Tk quando a conexão com o servidor cai."""
        if not self.conectado:
            return
        self.conectado = False
        self._parar_contagem()
        self._parar_espera()
        self._desativar_opcoes()
        self._set_status("🔌 Conexão com o servidor perdida.")
        self.botao_conectar.config(
            state="normal", text="Reconectar",
            bg=COR_BTN_CONN, command=self._voltar_para_partida,
        )
        messagebox.showerror(
            "Conexão perdida",
            "A conexão com o servidor foi encerrada. Clique em 'Reconectar' em até "
            "30 segundos para voltar à partida.",
        )

    # [Origem: IA]
    def _voltar_para_partida(self):
        """
        Reconecta mantendo a tela como está. Se a partida ainda estiver em
        espera, o servidor devolve o lugar (BEM_VINDO com reconectado=True) e
        reenvia a pergunta; se não, _on_bem_vindo limpa a tela.
        """
        self._fechar_tela_final()
        self._voltando = True
        self._reconectar_do_zero()

    # ── Handlers de mensagens (executam na thread Tk) ─────────────────────

    # [Origem: IA]
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
        voltando = getattr(self, "_voltando", False)
        self._voltando = False
        if msg.get("reconectado"):
            self._set_status("✅ Você voltou para a partida!")
            return
        if voltando:
            # Tentou voltar, mas a partida antiga já tinha acabado: começa do zero.
            self._resetar_ui_para_nova_partida()
        if msg.get("em_partida"):
            self._set_status("Partida encontrada! Boa sorte.")
        else:
            self._set_status("Conectado. Aguardando o adversário entrar na sala…")

    # [Origem: IA]
    def _on_pergunta(self, msg: dict):
        self._parar_espera()  # se a partida estava em espera, ela voltou
        self.pergunta_atual = extrair_detalhes_pergunta(msg)
        rodada_id   = self.pergunta_atual["rodada_id"]
        pergunta    = self.pergunta_atual["pergunta"]
        opcoes      = self.pergunta_atual["opcoes"]
        tempo_lim   = self.pergunta_atual["tempo_limite"]

        # A partida começou: esconde o campo de nome (só faz sentido antes de entrar).
        self._esconder_campo_nome()

        # Atualiza os nomes/placar na barra já na 1ª rodada (vêm no payload da PERGUNTA).
        apelidos = msg.get("apelidos", {})
        pontuacao = msg.get("pontuacao", {})
        posicao = msg.get("posicao", 0)
        if apelidos or pontuacao:
            self._desenhar_barra(posicao, pontuacao)
            self._atualizar_nomes_barra(pontuacao, apelidos)

        self.resposta_enviada = False
        self.rotulo_pergunta.config(text=pergunta)
        self.rotulo_rodada.config(text=f"Rodada {rodada_id} / 10")
        self._set_status(f"Rodada {rodada_id} — escolha sua resposta!")
        self._construir_opcoes(opcoes)
        self._ativar_opcoes()
        self._iniciar_contagem(tempo_lim)

    # [Origem: IA 68% · autoral 32%]
    def _on_fim_rodada(self, msg: dict):
        self._parar_contagem()
        self.rotulo_tempo.config(text="")
        self._atualizar_barra_tempo(0)
        self.pergunta_atual = None

        vencedor          = msg.get("vencedor", "nenhum")
        apelido_vencedor  = msg.get("apelido_vencedor")
        resposta_correta  = msg.get("resposta_correta", "")
        rodada            = msg.get("rodada", "?")

        # Destaca a resposta correta em verde e as demais em vermelho
        self._destacar_resposta_correta(resposta_correta)

        nome_venc = apelido_vencedor or vencedor
        if vencedor == self.id_jogador:
            linha = f"✅ Rodada {rodada}: você acertou primeiro! (resposta: {resposta_correta})"
        elif vencedor in (None, "nenhum"):
            linha = f"😐 Rodada {rodada}: ninguém acertou. Resposta certa: {resposta_correta}"
        else:
            linha = f"❌ Rodada {rodada}: {nome_venc} acertou primeiro. Resposta certa: {resposta_correta}"
        self._set_status(linha)
        self._adicionar_historico(linha)

    # [Origem: IA]
    def _destacar_resposta_correta(self, resposta_correta: str):
        """Pinta o botão da resposta certa de verde; a escolhida errada de vermelho."""
        escolhida = self.opcoes_var.get()
        for btn in getattr(self, "_botoes_opcao", []):
            valor = getattr(btn, "_opcao_valor", btn["text"])
            btn.config(state="disabled")
            if valor == resposta_correta:
                btn.config(bg=COR_ACERTO, fg="white", disabledforeground="white")
            elif valor == escolhida:
                btn.config(bg=COR_ERRO, fg="white", disabledforeground="white")
            else:
                btn.config(bg=COR_OPCAO, fg="#64748b", disabledforeground="#64748b")
        botao_enviar = getattr(self, "botao_enviar", None)
        if botao_enviar:
            try:
                botao_enviar.config(state="disabled", bg=COR_BTN_OFF, fg="#64748b")
            except Exception:
                pass

    # [Origem: IA]
    def _on_atualizar_barra(self, msg: dict):
        posicao   = msg.get("posicao", 0)
        pontuacao = msg.get("pontuacao", {})
        apelidos  = msg.get("apelidos", {})
        self._desenhar_barra(posicao, pontuacao)
        self._atualizar_nomes_barra(pontuacao, apelidos)

    # [Origem: IA]
    def _atualizar_nomes_barra(self, pontuacao: dict, apelidos: dict):
        """Atualiza os nomes nos cartões dos jogadores usando apelidos (não IDs)."""
        jogadores = list(pontuacao.keys())
        if jogadores:
            jid_a = jogadores[0]
            nome_a = apelidos.get(jid_a, jid_a)
            if jid_a == self.id_jogador:
                nome_a += "  (você)"
            self.rotulo_nome_a.config(text=nome_a)
        if len(jogadores) > 1:
            jid_b = jogadores[1]
            nome_b = apelidos.get(jid_b, jid_b)
            if jid_b == self.id_jogador:
                nome_b += "  (você)"
            self.rotulo_nome_b.config(text=nome_b)

    # [Origem: IA]
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
            tipo    = "empate"
            titulo  = "🤝 Empate!"
            detalhe = "Ninguém cedeu: a corda ficou equilibrada."
        elif vencedor == self.id_jogador:
            tipo    = "vitoria"
            titulo  = "🏆 Você venceu!"
            detalhe = f"Parabéns, {self.apelido}! Você puxou a corda até o fim."
        else:
            tipo    = "derrota"
            nome_venc = apelido_vencedor or vencedor
            titulo  = "😔 Você perdeu."
            detalhe = f"{nome_venc} venceu. Não foi dessa vez... que tal uma revanche?"

        # Placar exibido com apelidos
        placar = [f"{apelidos.get(jid, jid)}: {p} pontos" for jid, p in pontuacao.items()]
        # Tela final animada. Espera 2 s (como entre as rodadas) para o jogador
        # ver a resposta certa da última pergunta e a puxada decisiva da corda.
        self._parar_espera()
        atraso = max(PAUSA_RESULTADO_MS, int(DURACAO_PUXADA * 1000) + 200)
        self._id_tela_final = self.janela.after(
            atraso, lambda: self._mostrar_tela_final(tipo, detalhe, placar)
        )
        self._set_status(f"Fim de jogo — {titulo}  |  Clique em 'Jogar novamente'")
        self.rotulo_rodada.config(text="Partida encerrada")

        self.botao_conectar.config(
            state="normal", text="Jogar novamente",
            bg=COR_BTN_CONN, command=self._jogar_novamente,
        )

    # [Origem: IA]
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

        if id_evento == self.id_jogador:
            return
        apelido_adv = msg.get("apelido", id_evento)

        # Adversário caiu: a partida fica em espera enquanto ele pode voltar.
        if motivo == "aguardando_reconexao":
            self._parar_contagem()
            self._desativar_opcoes()
            self.rotulo_tempo.config(text="⏸ Partida em espera", fg=COR_TEMPO)
            self._adicionar_historico(f"⏸ {apelido_adv} desconectou. Partida em espera.")
            self._iniciar_espera(apelido_adv, int(msg.get("tempo_espera", 30)))
            return

        # Ele voltou: a próxima PERGUNTA (reenviada pelo servidor) retoma o jogo.
        if motivo == "reconectado":
            self._parar_espera()
            self._set_status(f"✅ {apelido_adv} voltou! Retomando a partida…")
            self._adicionar_historico(f"✅ {apelido_adv} voltou para a partida.")
            return

        # Ele não voltou a tempo (motivo "tempo_esgotado") ou caso antigo sem motivo.
        self._parar_espera()
        self._parar_contagem()
        self._desativar_opcoes()
        self.rotulo_tempo.config(text="")
        self.rotulo_rodada.config(text="Partida encerrada")
        self._set_status(f"⚠ {apelido_adv} não voltou. A partida foi encerrada.")
        self.botao_conectar.config(
            state="normal", text="Jogar novamente",
            bg=COR_BTN_CONN, command=self._jogar_novamente,
        )
        messagebox.showwarning(
            "Adversário desconectado",
            f"{apelido_adv} não voltou a tempo e a partida foi encerrada. "
            "Você pode iniciar uma nova.",
        )

    # [Origem: IA]
    def _iniciar_espera(self, apelido: str, segundos: int):
        """Mostra a contagem regressiva enquanto o adversário pode voltar."""
        self._parar_espera()
        self._espera_apelido = apelido
        self._espera_restante = max(0, segundos)
        self._tick_espera()

    # [Origem: IA]
    def _tick_espera(self):
        self._set_status(
            f"⏳ {self._espera_apelido} desconectou. Aguardando a volta: "
            f"{self._espera_restante}s"
        )
        if self._espera_restante > 0:
            self._espera_restante -= 1
            self._timer_espera = self.janela.after(1000, self._tick_espera)

    # [Origem: IA]
    def _parar_espera(self):
        timer = getattr(self, "_timer_espera", None)
        self._timer_espera = None
        if timer is not None:
            try:
                self.janela.after_cancel(timer)
            except (tk.TclError, ValueError):
                pass

    # ── Envio de resposta ─────────────────────────────────────────────────

    # [Origem: IA 60% · autoral 40%]
    def enviar_resposta(self):
        if self.pergunta_atual is None:
            # Sem pergunta ativa (ex.: Enter antes da partida começar): ignora em silêncio.
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

    # ── Tela final animada (vitória / derrota / empate) ───────────────────

    # [Origem: IA]
    def _mostrar_tela_final(self, tipo: str, detalhe: str, placar: list[str]):
        """
        Cobre a janela com uma tela animada de fim de partida:
          vitoria → troféu surgindo com raios de sol girando e chuva de confete
          derrota → carinha triste com lágrima, chuva e título caindo e quicando
          empate  → dois bonecos em disputa equilibrada, título alternando cores
        O jogador fecha com o botão "Continuar" (ou Esc) e volta para a tela do jogo.
        """
        self._fechar_tela_final()
        fundos = {"vitoria": "#0b1226", "derrota": "#080c16", "empate": "#0d1326"}
        ov = tk.Canvas(self.janela, bg=fundos.get(tipo, COR_FUNDO), highlightthickness=0)
        ov.place(x=0, y=0, relwidth=1, relheight=1)
        self._overlay = ov

        largura = max(self.janela.winfo_width(), 400)
        altura = max(self.janela.winfo_height(), 400)
        particulas = []
        if tipo == "vitoria":
            cores = ["#fbbf24", "#f472b6", "#38bdf8", "#4ade80", "#a78bfa", "#fb923c"]
            for _ in range(90):
                particulas.append({
                    "x": random.uniform(0, largura), "y": random.uniform(-altura, 0),
                    "vx": random.uniform(-1.2, 1.2), "vy": random.uniform(2.5, 5.5),
                    "tam": random.uniform(5, 9), "giro": random.uniform(0, 6.28),
                    "cor": random.choice(cores),
                })
        elif tipo == "derrota":
            for _ in range(70):
                particulas.append({
                    "x": random.uniform(0, largura), "y": random.uniform(-altura, altura),
                    "vy": random.uniform(7, 11), "tam": random.uniform(10, 18),
                })
        else:
            for _ in range(40):
                particulas.append({
                    "x": random.uniform(0, largura), "y": random.uniform(0, altura),
                    "vy": random.uniform(0.3, 1.0), "fase": random.uniform(0, 6.28),
                    "cor": random.choice([COR_BARRA_A, COR_BARRA_B]),
                })

        self._overlay_estado = {
            "tipo": tipo, "detalhe": detalhe, "placar": placar,
            "t0": time.monotonic(), "particulas": particulas,
        }
        ov.tag_bind("btn_continuar", "<Button-1>", lambda _e: self._fechar_tela_final())
        ov.tag_bind("btn_continuar", "<Enter>", lambda _e: ov.config(cursor="hand2"))
        ov.tag_bind("btn_continuar", "<Leave>", lambda _e: ov.config(cursor=""))
        self.janela.bind("<Escape>", lambda _e: self._fechar_tela_final())
        self._animar_tela_final()

    # [Origem: IA]
    def _fechar_tela_final(self):
        """Remove a tela final (se estiver aberta) e volta para a tela do jogo."""
        pendente = getattr(self, "_id_tela_final", None)
        self._id_tela_final = None
        if pendente is not None:
            try:
                self.janela.after_cancel(pendente)
            except (tk.TclError, ValueError):
                pass
        ov = getattr(self, "_overlay", None)
        self._overlay = None
        if ov is not None:
            try:
                ov.destroy()
            except tk.TclError:
                pass

    # [Origem: IA]
    def _animar_tela_final(self):
        """Desenha um quadro da tela final e agenda o próximo."""
        ov = getattr(self, "_overlay", None)
        if ov is None:
            return
        try:
            est = self._overlay_estado
            t = time.monotonic() - est["t0"]
            W = max(ov.winfo_width(), 400)
            H = max(ov.winfo_height(), 400)
            ov.delete("all")
            tipo = est["tipo"]
            if tipo == "vitoria":
                self._quadro_vitoria(ov, W, H, t, est["particulas"])
            elif tipo == "derrota":
                self._quadro_derrota(ov, W, H, t, est["particulas"])
            else:
                self._quadro_empate(ov, W, H, t, est["particulas"])
            self._quadro_rodape(ov, W, H, t, est["detalhe"], est["placar"])
            self.janela.after(FPS_MS, self._animar_tela_final)
        except tk.TclError:
            self._overlay = None

    # [Origem: IA]
    def _quadro_vitoria(self, ov: tk.Canvas, W, H, t, confete):
        cx, ty = W / 2, H * 0.30
        # Raios de sol girando atrás do troféu
        raio = max(W, H)
        n_raios = 14
        for i in range(n_raios):
            a1 = t * 0.35 + i * 2 * math.pi / n_raios
            a2 = a1 + math.pi / n_raios
            ov.create_polygon(cx, ty,
                              cx + raio * math.cos(a1), ty + raio * math.sin(a1),
                              cx + raio * math.cos(a2), ty + raio * math.sin(a2),
                              fill="#141f3d" if i % 2 else "#101a33", outline="")

        # Troféu surgindo com efeito elástico + leve flutuação
        s = 1.5 * _ease_out_back(min(1.0, t / 0.9)) if t > 0 else 0
        ty += math.sin(t * 2.2) * 4
        ouro, ouro_esc = "#fbbf24", "#b45309"
        if s > 0.05:
            # Alças
            ov.create_oval(cx - 58 * s, ty - 48 * s, cx - 18 * s, ty - 8 * s,
                           outline=ouro, width=max(1, int(6 * s)))
            ov.create_oval(cx + 18 * s, ty - 48 * s, cx + 58 * s, ty - 8 * s,
                           outline=ouro, width=max(1, int(6 * s)))
            # Taça
            ov.create_polygon(cx - 40 * s, ty - 55 * s, cx + 40 * s, ty - 55 * s,
                              cx + 30 * s, ty - 5 * s, cx + 10 * s, ty + 12 * s,
                              cx - 10 * s, ty + 12 * s, cx - 30 * s, ty - 5 * s,
                              fill=ouro, outline=ouro_esc, width=2, smooth=True)
            # Haste e base
            ov.create_rectangle(cx - 7 * s, ty + 10 * s, cx + 7 * s, ty + 30 * s,
                                fill=ouro, outline=ouro_esc)
            ov.create_rectangle(cx - 30 * s, ty + 30 * s, cx + 30 * s, ty + 42 * s,
                                fill=ouro_esc, outline="")
            # Estrela na taça e brilho
            self._estrela(ov, cx, ty - 28 * s, 13 * s, "#fff7d6")
            ov.create_oval(cx - 30 * s, ty - 50 * s, cx - 22 * s, ty - 30 * s,
                           fill="#fde68a", outline="")

        # Título pulsando
        tam = int(42 + 3 * math.sin(t * 4))
        ov.create_text(cx + 3, H * 0.55 + 3, text="VITÓRIA!", fill="#78350f",
                       font=(FONTE, tam, "bold"))
        ov.create_text(cx, H * 0.55, text="VITÓRIA!", fill="#fbbf24",
                       font=(FONTE, tam, "bold"))

        # Confete caindo e girando
        for p in confete:
            p["x"] += p["vx"] + math.sin(t * 2 + p["giro"]) * 0.6
            p["y"] += p["vy"]
            p["giro"] += 0.15
            if p["y"] > H + 10:
                p["y"] = random.uniform(-40, -10)
                p["x"] = random.uniform(0, W)
            larg = p["tam"] * abs(math.cos(p["giro"])) + 1   # "vira" no ar
            ov.create_rectangle(p["x"] - larg / 2, p["y"] - p["tam"] / 3,
                                p["x"] + larg / 2, p["y"] + p["tam"] / 3,
                                fill=p["cor"], outline="")

    # [Origem: IA]
    def _quadro_derrota(self, ov: tk.Canvas, W, H, t, chuva):
        cx, fy = W / 2, H * 0.30
        # Chuva
        for p in chuva:
            p["y"] += p["vy"]
            if p["y"] > H:
                p["y"] = random.uniform(-60, -10)
                p["x"] = random.uniform(0, W)
            ov.create_line(p["x"], p["y"], p["x"] - 2, p["y"] + p["tam"],
                           fill="#334766", width=1)

        # Nuvem pesada sobre a carinha
        for dx, dy, r in ((-50, -95, 30), (-15, -110, 38), (30, -100, 32), (60, -88, 24)):
            ov.create_oval(cx + dx - r, fy + dy - r, cx + dx + r, fy + dy + r,
                           fill="#1f2937", outline="")

        # Carinha triste (entra de baixo e balança devagar)
        entrada = _ease_out_back(min(1.0, t / 0.8))
        fy = fy + (1 - entrada) * 60
        balanco = math.sin(t * 1.5) * 3
        r = 55
        ov.create_oval(cx - r + balanco, fy - r, cx + r + balanco, fy + r,
                       fill="#475569", outline="#64748b", width=3)
        # Olhos
        for ox in (-20, 20):
            ov.create_oval(cx + ox - 6 + balanco, fy - 18, cx + ox + 6 + balanco, fy - 6,
                           fill="#0f172a", outline="")
        # Sobrancelhas caídas
        ov.create_line(cx - 30 + balanco, fy - 26, cx - 12 + balanco, fy - 32,
                       fill="#0f172a", width=3)
        ov.create_line(cx + 30 + balanco, fy - 26, cx + 12 + balanco, fy - 32,
                       fill="#0f172a", width=3)
        # Boca triste
        ov.create_arc(cx - 24 + balanco, fy + 12, cx + 24 + balanco, fy + 44,
                      start=20, extent=140, style="arc", outline="#0f172a", width=4)
        # Lágrima escorrendo (repete a cada 1,6 s)
        ciclo = (t % 1.6) / 1.6
        lx, ly = cx - 20 + balanco, fy - 4 + ciclo * 45
        ov.create_polygon(lx, ly - 7, lx - 5, ly + 2, lx, ly + 7, lx + 5, ly + 2,
                          fill="#60a5fa", outline="", smooth=True)

        # Título cai do topo e quica
        queda = _ease_out_bounce(min(1.0, t / 1.1))
        ty = -40 + (H * 0.55 + 40) * queda
        ov.create_text(cx + 3, ty + 3, text="DERROTA", fill="#450a0a",
                       font=(FONTE, 42, "bold"))
        ov.create_text(cx, ty, text="DERROTA", fill="#f87171", font=(FONTE, 42, "bold"))

    # [Origem: IA]
    def _quadro_empate(self, ov: tk.Canvas, W, H, t, brilhos):
        cx, cy = W / 2, H * 0.30
        # Fundo dividido: território azul x vermelho
        ov.create_rectangle(0, 0, cx, H, fill="#0f1a33", outline="")
        ov.create_rectangle(cx, 0, W, H, fill="#2a1019", outline="")
        ov.create_line(cx, 0, cx, H, fill="#e2e8f0", width=2, dash=(6, 6))

        # Brilhos flutuando
        for p in brilhos:
            p["y"] -= p["vy"]
            if p["y"] < -10:
                p["y"] = H + 10
                p["x"] = random.uniform(0, W)
            r = 2 + 1.5 * (1 + math.sin(t * 3 + p["fase"]))
            ov.create_oval(p["x"] - r, p["y"] - r, p["x"] + r, p["y"] + r,
                           fill=p["cor"], outline="")

        # Cabo de guerra equilibrado: o nó oscila em volta do centro
        escala = 2.2
        mao_a, mao_b = cx - 190, cx + 190
        no_x = cx + math.sin(t * 2.4) * 22
        # Quem "puxa" alterna conforme o nó vai para um lado ou outro
        esforco_a = max(0.0, -math.sin(t * 2.4))
        esforco_b = max(0.0, math.sin(t * 2.4))
        self._desenhar_segmento_corda(ov, mao_a, no_x, cy, 3, t * 4)
        self._desenhar_segmento_corda(ov, mao_b, no_x, cy, 3, t * 4 + 1.7)
        self._desenhar_puxador(ov, mao_a, cy, -1, COR_BARRA_A, esforco_a, t * 4, escala)
        self._desenhar_puxador(ov, mao_b, cy, 1, COR_BARRA_B, esforco_b, t * 4 + 1.3, escala)
        ov.create_oval(no_x - 14, cy - 14, no_x + 14, cy + 14,
                       fill=COR_NO, outline=COR_CORDA_ESC, width=2)

        # Título alternando entre as cores dos dois lados
        cor = COR_BARRA_A if int(t * 2) % 2 == 0 else COR_BARRA_B
        tam = int(42 + 2 * math.sin(t * 3))
        ov.create_text(cx + 3, H * 0.55 + 3, text="EMPATE!", fill="#020617",
                       font=(FONTE, tam, "bold"))
        ov.create_text(cx, H * 0.55, text="EMPATE!", fill=cor, font=(FONTE, tam, "bold"))

    # [Origem: IA]
    def _quadro_rodape(self, ov: tk.Canvas, W, H, t, detalhe, placar):
        """Texto, placar final e botão "Continuar" (surgem com fade-in por posição)."""
        cx = W / 2
        if t < 0.6:
            return
        subida = (1 - min(1.0, (t - 0.6) / 0.4)) * 20   # desliza 20 px para cima
        ov.create_text(cx, H * 0.64 + subida, text=detalhe, fill=COR_TEXTO,
                       font=(FONTE, 12), width=W - 80, justify="center")
        ov.create_text(cx, H * 0.70 + subida, text="Placar final", fill=COR_STATUS,
                       font=(FONTE, 10, "bold"))
        for i, linha in enumerate(placar):
            ov.create_text(cx, H * 0.70 + 22 + i * 22 + subida, text=linha,
                           fill=COR_TEXTO, font=(FONTE, 12, "bold"))
        if t > 1.0:
            by = H * 0.86
            self._retangulo_arredondado(ov, cx - 90, by - 22, cx + 90, by + 22, 14,
                                        fill=COR_BTN_CONN, outline="", tags="btn_continuar")
            ov.create_text(cx, by, text="Continuar", fill="white",
                           font=(FONTE, 12, "bold"), tags="btn_continuar")

    # [Origem: IA]
    def _estrela(self, c: tk.Canvas, cx, cy, r, cor):
        """Estrela de 5 pontas centrada em (cx, cy)."""
        pontos = []
        for i in range(10):
            ang = -math.pi / 2 + i * math.pi / 5
            rr = r if i % 2 == 0 else r * 0.45
            pontos += [cx + rr * math.cos(ang), cy + rr * math.sin(ang)]
        c.create_polygon(pontos, fill=cor, outline="")

    # ── Jogar novamente ───────────────────────────────────────────────────

    # [Origem: IA]
    def _jogar_novamente(self):
        """
        Inicia uma nova partida REUSANDO a conexão existente.

        Se o socket TCP ainda está vivo, apenas reenvia ENTRAR (o servidor
        trata como reentrada e recoloca o jogador na fila). Só se a conexão
        tiver realmente caído é que fazemos uma reconexão do zero.
        """
        self._resetar_ui_para_nova_partida()

        if self.conectado and self._conexao_viva():
            # Caminho feliz: conexão viva → só reentra na fila, sem reconectar.
            self.botao_conectar.config(state="disabled", text="Aguardando…", bg="#334155")
            self._set_status("Procurando adversário para uma nova partida…")
            try:
                self.cliente.enviar_entrada(self.id_jogador, self.apelido)
            except OSError:
                # A conexão caiu no meio do envio → cai para reconexão total.
                self._reconectar_do_zero()
        else:
            # Conexão realmente perdida → reconecta do zero.
            self._reconectar_do_zero()

    # [Origem: IA]
    def _reconectar_do_zero(self):
        """Fecha a conexão antiga e abre uma nova (usado só quando o socket caiu)."""
        self.botao_conectar.config(state="disabled", text="Conectando…", bg="#334155")
        self._set_status("Reconectando…")

        # Encerra a thread de escuta antiga antes de trocar o cliente.
        self.conectado = False
        self.cliente.fechar()

        # Reabilita o campo de nome temporariamente para o conectar() lê-lo.
        if hasattr(self, "entrada_nome"):
            self.entrada_nome.config(state="normal")

        self.cliente = ClienteQuiz(
            host=self.cliente.host,
            porta_tcp=self.cliente.porta_tcp,
            porta_udp=self.cliente.porta_udp,
        )
        self.conectar()

    # [Origem: IA 71% · autoral 29%]
    def _resetar_ui_para_nova_partida(self):
        """Limpa a interface (barra, placar, opções, histórico) para uma nova partida."""
        self._fechar_tela_final()
        # Volta o nó ao centro sem animação de "puxada" (é um reinício, não um ponto).
        self._ultima_barra = (0, {})
        self._anim_corda = None
        self._pos_visual = 0.0
        self._desenhar_barra(0, {})
        self.rotulo_rodada.config(text="Rodada — / 10")
        self.rotulo_pts_a.config(text="0 pts")
        self.rotulo_pts_b.config(text="0 pts")
        self.rotulo_tempo.config(text="")
        self.rotulo_pergunta.config(text="A pergunta aparecerá aqui quando a partida começar.")

        for btn in getattr(self, "_botoes_opcao", []):
            btn.destroy()
        self._botoes_opcao.clear()
        self._atualizar_barra_tempo(0)

        texto_historico = getattr(self, "texto_historico", None)
        if texto_historico is not None:
            texto_historico.config(state="normal")
            texto_historico.delete("1.0", "end")
            texto_historico.config(state="disabled")

    # ── Utilitários ───────────────────────────────────────────────────────

    # [Origem: IA]
    def _set_status(self, texto: str):
        self.rotulo_status.config(text=texto)

    # [Origem: IA 56% · autoral 44%]
    def _adicionar_historico(self, texto: str):
        """Acrescenta uma linha ao painel de histórico da partida, se ele existir."""
        texto_historico = getattr(self, "texto_historico", None)
        if texto_historico is None:
            return
        texto_historico.config(state="normal")
        # Cor por resultado: verde = você venceu, vermelho = adversário, cinza = ninguém.
        texto_historico.tag_configure("vitoria", foreground="#4ade80")
        texto_historico.tag_configure("derrota", foreground="#f87171")
        texto_historico.tag_configure("neutro", foreground=COR_STATUS)
        if texto.startswith("✅"):
            tag = "vitoria"
        elif texto.startswith("❌"):
            tag = "derrota"
        else:
            tag = "neutro"
        texto_historico.insert("end", f"{texto}\n", tag)
        texto_historico.see("end")
        texto_historico.config(state="disabled")

    # [Origem: IA]
    def _ao_fechar(self):
        self._janela_fechada = True
        self.janela.destroy()

    # [Origem: autoral]
    def iniciar(self):
        self.janela.mainloop()


# ── Funções utilitárias (usadas pelos testes) ─────────────────────────────


# [Origem: IA 57% · autoral 43%]
def extrair_detalhes_pergunta(mensagem: dict) -> dict:
    return {
        "rodada_id":   mensagem.get("rodada_id", 1),
        "pergunta":    mensagem.get("pergunta", "Pergunta não disponível"),
        "opcoes":      mensagem.get("opcoes", []),
        "tempo_limite": mensagem.get("tempo_limite", 30),
    }


# [Origem: autoral 60% · IA 40%]
def extrair_detalhes_desconexao(mensagem: dict) -> dict:
    return {
        "id_jogador":  mensagem.get("id_jogador", "desconhecido"),
        "codigo_sala": mensagem.get("codigo_sala", "sala-1"),
    }


# ── Entry point ───────────────────────────────────────────────────────────


# [Origem: autoral 52% · IA 48%]
def main():
    parser = argparse.ArgumentParser(description="Cliente do Quiz Cabo de Guerra")
    parser.add_argument("--id-jogador", default="player-1",
                        help="Identificador técnico do jogador no servidor")
    parser.add_argument("--apelido", default="",
                        help="Apelido inicial (opcional; o jogador digita na tela)")
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
