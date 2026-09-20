"""
Lógica do jogo Quiz Cabo de Guerra.

Convenção de barra:
  direcao_barra = +1 → jogador_a ganha a rodada, barra vai para o lado de A
  direcao_barra = -1 → jogador_b ganha a rodada, barra vai para o lado de B
  posicao_barra positiva → jogador_a está na frente
  posicao_barra negativa → jogador_b está na frente

A partida pode ser vencida por:
  1. Acumulação de pontos (pontos_para_vencer)
  2. Fim das rodadas (quem tiver mais pontos)
"""
from dataclasses import dataclass, field

LIMITE_BARRA = 5
MAXIMO_RODADAS = 10


@dataclass
class RodadaJogo:
    """Representa uma única rodada (pergunta) — usado principalmente em testes."""
    rodada_id: int                       # número da rodada (1..maximo_rodadas)
    pergunta: str                        # enunciado
    resposta_correta: str                # gabarito (só no servidor)
    posicao_barra: int = 0               # posição da barra no momento
    respondida: bool = False             # se já foi respondida
    vencedor: str | None = None          # quem venceu a rodada
    horario_resposta: float | None = None  # timestamp da resposta vencedora


@dataclass
class EstadoJogo:
    """
    Estado completo de uma partida entre dois jogadores.

    A barra (posicao_barra) é o coração do "cabo de guerra":
      > 0 → jogador_a puxou para o seu lado (na frente)
      < 0 → jogador_b puxou para o seu lado (na frente)
      == 0 → empatado no centro
    """
    jogador_a: str = "player-1"          # id do jogador da esquerda
    jogador_b: str = "player-2"          # id do jogador da direita
    maximo_rodadas: int = MAXIMO_RODADAS  # total de rodadas da partida (10)
    rodada_atual: int = 1                # rodada em andamento
    posicao_barra: int = 0               # ver docstring da classe
    pontos_para_vencer: int = 3          # knockout: vence quem chegar a N pontos
    pontuacao_jogadores: dict = field(default_factory=dict)  # {id: pontos}
    vencedor: str | None = None          # id do vencedor, "empate" ou None

    def __post_init__(self):
        # Garante que o placar comece zerado para os dois jogadores.
        if not self.pontuacao_jogadores:
            self.pontuacao_jogadores = {self.jogador_a: 0, self.jogador_b: 0}

    # ------------------------------------------------------------------ #
    # API pública                                                          #
    # ------------------------------------------------------------------ #

    def avancar_rodada(self) -> bool:
        """Avança para a próxima rodada. Retorna False se já estiver na última ou se houver vencedor."""
        if self.vencedor is not None:
            return False
        if self.rodada_atual < self.maximo_rodadas:
            self.rodada_atual += 1
            return True
        return False

    def atualizar_barra(self, delta: int):
        """Move a barra em `delta` unidades (positivo = lado A, negativo = lado B)."""
        self.posicao_barra += delta

    def registrarResultadoRodada(self, vencedor: str | None):
        """
        Registra o resultado de uma rodada e atualiza pontuação/barra/vencedor.
        Compatibilidade com testes legados.
        """
        if vencedor is None or vencedor in ("nenhum", "empate"):
            return

        self.pontuacao_jogadores[vencedor] = self.pontuacao_jogadores.get(vencedor, 0) + 1

        # Move a barra
        if vencedor == self.jogador_a:
            self.posicao_barra += 1
        else:
            self.posicao_barra -= 1

        # Verifica condição de vitória por pontos
        if self.pontuacao_jogadores[vencedor] >= self.pontos_para_vencer:
            self.vencedor = vencedor

    def verificar_fim_de_jogo(self) -> str | None:
        """
        Verifica se o jogo terminou após a rodada atual.

        IMPORTANTE: deve ser chamado ANTES de avancar_rodada(), enquanto
        rodada_atual ainda reflete a rodada que acabou de ser jogada. Assim, o
        desempate por barra/pontos só dispara exatamente na última rodada
        (rodada_atual == maximo_rodadas), evitando o bug off-by-one de terminar
        cedo demais ou tarde demais.
        """
        if self.vencedor:
            return self.vencedor

        # Só encerra por fim de rodadas quando a última rodada foi concluída
        if self.rodada_atual < self.maximo_rodadas:
            return None

        # Última rodada: desempata pela posição da barra
        if self.posicao_barra > 0:
            self.vencedor = self.jogador_a
        elif self.posicao_barra < 0:
            self.vencedor = self.jogador_b
        else:
            # Empate na barra → desempata por pontuação
            pts_a = self.pontuacao_jogadores.get(self.jogador_a, 0)
            pts_b = self.pontuacao_jogadores.get(self.jogador_b, 0)
            if pts_a > pts_b:
                self.vencedor = self.jogador_a
            elif pts_b > pts_a:
                self.vencedor = self.jogador_b
            else:
                self.vencedor = "empate"

        return self.vencedor

    def terminou(self) -> bool:
        if self.vencedor is not None:
            return True
        if self.rodada_atual >= self.maximo_rodadas:
            return True
        return any(p >= self.pontos_para_vencer for p in self.pontuacao_jogadores.values())


# ---------------------------------------------------------------------------
# Função utilitária de resolução de rodada
# ---------------------------------------------------------------------------

def resolverResultadoRodada(
    jogador_a: str,
    jogador_b: str,
    resposta_a: str,
    resposta_b: str,
    resposta_correta: str = "TCP",
) -> dict:
    """
    Determina o vencedor de uma rodada sem considerar timing.

    Retorna:
      vencedor      : id do vencedor, "empate" ou "nenhum"
      delta_barra   : quanto a barra se move (0 ou 1)
      direcao_barra : +1 = jogador_a vence, -1 = jogador_b vence, 0 = ninguém
    """
    correta = resposta_correta.strip().upper()
    acertou_a = resposta_a.strip().upper() == correta
    acertou_b = resposta_b.strip().upper() == correta

    if acertou_a and not acertou_b:
        return {"vencedor": jogador_a, "delta_barra": 1, "direcao_barra": 1}
    if acertou_b and not acertou_a:
        return {"vencedor": jogador_b, "delta_barra": 1, "direcao_barra": -1}
    if acertou_a and acertou_b:
        return {"vencedor": "empate", "delta_barra": 0, "direcao_barra": 0}
    return {"vencedor": "nenhum", "delta_barra": 0, "direcao_barra": 0}



