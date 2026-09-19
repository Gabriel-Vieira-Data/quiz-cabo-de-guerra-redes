from dataclasses import dataclass, field


@dataclass
class RodadaJogo:
    rodada_id: int
    pergunta: str
    resposta_correta: str
    posicao_barra: int = 0
    respondida: bool = False
    vencedor: str | None = None
    horario_resposta: float | None = None


@dataclass
class EstadoJogo:
    maximo_rodadas: int = 10
    rodada_atual: int = 1
    posicao_barra: int = 0
    pontos_para_vencer: int = 3
    pontuacao_jogadores: dict[str, int] = field(default_factory=lambda: {"player-1": 0, "player-2": 0})
    vencedor: str | None = None

    def avancar_rodada(self) -> bool:
        if self.rodada_atual < self.maximo_rodadas:
            self.rodada_atual += 1
            self.posicao_barra = 0
            return True

        self.posicao_barra = 0
        return False

    def registrarResultadoRodada(self, vencedor: str | None):
        if vencedor is None or vencedor == "nenhum":
            return

        if vencedor == "empate":
            return

        if vencedor in self.pontuacao_jogadores:
            self.pontuacao_jogadores[vencedor] += 1
            if self.pontuacao_jogadores[vencedor] >= self.pontos_para_vencer:
                self.vencedor = vencedor

    def atualizar_barra(self, delta: int):
        self.posicao_barra += delta

    def terminou(self):
        if self.vencedor is not None:
            return True

        if self.rodada_atual >= self.maximo_rodadas:
            return True

        return any(pontos >= self.pontos_para_vencer for pontos in self.pontuacao_jogadores.values())


def resolverResultadoRodada(
    jogador_a: str,
    jogador_b: str,
    resposta_a: str,
    resposta_b: str,
    resposta_correta: str = "TCP",
):
    """Determina quem responde corretamente e atualiza a barra do cabo de guerra."""
    resposta_correta_normalizada = resposta_correta.strip().upper()
    correta_a = resposta_a.strip().upper() == resposta_correta_normalizada
    correta_b = resposta_b.strip().upper() == resposta_correta_normalizada

    if correta_a and not correta_b:
        return {"vencedor": jogador_a, "delta_barra": 1, "direcao_barra": 1}
    if correta_b and not correta_a:
        return {"vencedor": jogador_b, "delta_barra": 1, "direcao_barra": -1}
    if correta_a and correta_b:
        return {"vencedor": "empate", "delta_barra": 0, "direcao_barra": 0}

    return {"vencedor": "nenhum", "delta_barra": 0, "direcao_barra": 0}


GameRound = RodadaJogo
QuizGameState = EstadoJogo
resolve_round_result = resolverResultadoRodada
