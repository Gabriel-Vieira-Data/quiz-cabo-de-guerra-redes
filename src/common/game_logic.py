"""
Lógica do jogo Quiz Cabo de Guerra.

MODELO DE CABO DE GUERRA (o que realmente importa é a VANTAGEM RELATIVA):

  posicao_barra é a "corda". Ela representa a DIFERENÇA de rodadas vencidas
  entre os dois jogadores:
    > 0 → jogador_a está puxando a corda para o lado dele
    < 0 → jogador_b está puxando a corda para o lado dele
    == 0 → corda no centro (empate)

  Cada rodada vencida move a corda 1 unidade na direção do vencedor. Se o
  outro vencer a próxima, a corda volta — como num cabo de guerra real.

A partida termina quando:
  1. KNOCKOUT: a corda chega a uma das pontas, ou seja, a diferença de vitórias
     atinge VANTAGEM_PARA_VENCER (3). Ex.: A vence 3 rodadas a mais que B.
  2. FIM DAS RODADAS: acabaram as 10 perguntas. Vence quem tiver a corda do seu
     lado (posicao != 0); se estiver exatamente no centro, é empate.

Marcação de origem (ver USO_DE_IA.md): "# [Origem: ...]" acima de cada
classe/função — "IA" = escrito com auxílio de IA; "autoral" = escrito pelos
integrantes sem IA (medido com git blame).
"""
from dataclasses import dataclass, field

# A corda vai de -VANTAGEM_PARA_VENCER a +VANTAGEM_PARA_VENCER.
# Atingir uma das pontas (diferença de 3 vitórias) encerra o jogo.
VANTAGEM_PARA_VENCER = 3
LIMITE_BARRA = VANTAGEM_PARA_VENCER   # alias: a ponta da corda é a vantagem máxima
MAXIMO_RODADAS = 10


# [Origem: IA]
@dataclass
class EstadoJogo:
    """
    Estado completo de uma partida entre dois jogadores.

    A corda (posicao_barra) é o coração do "cabo de guerra" — representa a
    DIFERENÇA de rodadas vencidas:
      > 0 → jogador_a puxou para o seu lado (está na frente)
      < 0 → jogador_b puxou para o seu lado (está na frente)
      == 0 → corda no centro (empatados)

    pontuacao_jogadores guarda o total de rodadas que cada um venceu (só para
    exibição/desempate); quem decide a vitória por knockout é a posicao_barra.
    """
    jogador_a: str = "player-1"          # id do jogador da esquerda
    jogador_b: str = "player-2"          # id do jogador da direita
    maximo_rodadas: int = MAXIMO_RODADAS  # total de rodadas da partida (10)
    rodada_atual: int = 1                # rodada em andamento
    posicao_barra: int = 0               # a corda: diferença de vitórias (-3 a +3)
    vantagem_para_vencer: int = VANTAGEM_PARA_VENCER  # diferença que encerra o jogo
    pontuacao_jogadores: dict = field(default_factory=dict)  # {id: rodadas vencidas}
    vencedor: str | None = None          # id do vencedor, "empate" ou None

    # [Origem: IA]
    def __post_init__(self):
        # Garante que o placar comece zerado para os dois jogadores.
        if not self.pontuacao_jogadores:
            self.pontuacao_jogadores = {self.jogador_a: 0, self.jogador_b: 0}

    # ------------------------------------------------------------------ #
    # API pública                                                          #
    # ------------------------------------------------------------------ #

    # [Origem: autoral 62% · IA 38%]
    def avancar_rodada(self) -> bool:
        """Avança para a próxima rodada. Retorna False se já estiver na última ou se houver vencedor."""
        if self.vencedor is not None:
            return False
        if self.rodada_atual < self.maximo_rodadas:
            self.rodada_atual += 1
            return True
        return False

    # [Origem: IA]
    def registrarResultadoRodada(self, vencedor: str | None):
        """
        Registra o resultado de uma rodada: incrementa o placar do vencedor e
        puxa a corda 1 unidade na direção dele.

        A vitória por KNOCKOUT acontece quando a corda atinge uma das pontas,
        ou seja, quando a DIFERENÇA de vitórias chega a `vantagem_para_vencer`
        (|posicao_barra| == 3). NÃO é por pontos acumulados — placar 3x2 não
        encerra o jogo, mas 3x0 (ou 4x1, etc.) sim, pois a diferença é 3.
        """
        if vencedor is None or vencedor in ("nenhum", "empate"):
            return

        # Placar (total de rodadas vencidas — usado para exibição e desempate)
        self.pontuacao_jogadores[vencedor] = self.pontuacao_jogadores.get(vencedor, 0) + 1

        # Puxa a corda na direção do vencedor
        if vencedor == self.jogador_a:
            self.posicao_barra += 1
        else:
            self.posicao_barra -= 1

        # Knockout: a corda chegou na ponta (diferença de vitórias == 3)
        if abs(self.posicao_barra) >= self.vantagem_para_vencer:
            self.vencedor = vencedor

    # [Origem: IA]
    def verificar_fim_de_jogo(self) -> str | None:
        """
        Verifica se o jogo terminou após a rodada atual.

        IMPORTANTE: deve ser chamado ANTES de avancar_rodada(), enquanto
        rodada_atual ainda reflete a rodada que acabou de ser jogada. Assim, o
        desempate por barra/pontos só acontece exatamente na última rodada
        (rodada_atual == maximo_rodadas).
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





