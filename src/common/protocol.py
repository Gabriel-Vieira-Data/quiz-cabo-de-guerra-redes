"""
protocol.py — Protocolo de mensagens do Quiz Cabo de Guerra.

═══════════════════════════════════════════════════════════════════════════
FORMATO DE WIRE (como os bytes viajam na rede)
═══════════════════════════════════════════════════════════════════════════

TCP (jogo): cada mensagem é enquadrada com um cabeçalho de tamanho:

    [4 bytes big-endian = N][N bytes de payload JSON UTF-8]

    O cabeçalho de 4 bytes diz quantos bytes de JSON vêm em seguida. Isso é
    necessário porque TCP é um fluxo contínuo (stream) — sem o cabeçalho, o
    receptor não saberia onde uma mensagem termina e a próxima começa.

UDP (ping/latência): datagrama JSON puro, SEM cabeçalho de tamanho.

    UDP já entrega cada datagrama como uma unidade, então o cabeçalho não é
    necessário nem usado aqui.

═══════════════════════════════════════════════════════════════════════════
CONTRATO DE MENSAGENS (o que cada uma carrega de verdade)
═══════════════════════════════════════════════════════════════════════════

Todas as mensagens têm o campo "tipo" (string). Os demais campos dependem do tipo.

── Cliente → Servidor (TCP) ───────────────────────────────────────────────

ENTRAR      Jogador entra na fila.
            { "tipo": "ENTRAR", "id_jogador": str, "apelido": str }

RESPOSTA    Jogador responde a rodada atual.
            { "tipo": "RESPOSTA", "id_jogador": str, "rodada_id": int, "resposta": str }

── Cliente → Servidor (UDP) ───────────────────────────────────────────────

PING        Verificação de latência. Pode conter um timestamp para medir RTT.
            { "tipo": "PING", "id_jogador": str, "ts": float (opcional) }

── Servidor → Cliente (TCP) ───────────────────────────────────────────────

BEM_VINDO   Confirmação de ENTRAR. Informa o id DEFINITIVO do jogador (o
            servidor pode ter renomeado em caso de colisão) e se ele já está
            em partida ou aguardando adversário.
            { "tipo": "BEM_VINDO", "id_jogador": str, "apelido": str,
              "em_partida": bool, "codigo_sala": str | None }

PERGUNTA    Início de uma rodada. NÃO contém a resposta correta (anti-trapaça).
            { "tipo": "PERGUNTA", "rodada_id": int, "pergunta": str,
              "opcoes": [str, ...], "tempo_limite": int }

FIM_RODADA  Rodada terminou. Aqui a resposta correta É revelada (para feedback).
            "vencedor" pode ser um id de jogador OU a string "nenhum".
            { "tipo": "FIM_RODADA", "vencedor": str,
              "apelido_vencedor": str | None, "resposta_correta": str,
              "rodada": int, "codigo_sala": str }

ATUALIZAR_BARRA  Nova posição da barra e placar.
            "posicao" > 0 → jogador_a na frente; < 0 → jogador_b na frente.
            "pontuacao" e "apelidos" são dicts { id_jogador: valor }.
            { "tipo": "ATUALIZAR_BARRA", "posicao": int,
              "pontuacao": {id: int}, "apelidos": {id: str} }

FIM_JOGO    Partida encerrada. "vencedor" pode ser um id OU "empate".
            { "tipo": "FIM_JOGO", "vencedor": str,
              "apelido_vencedor": str | None, "pontuacao": {id: int},
              "posicao": int, "apelidos": {id: str} }

DESCONEXAO  Dois casos distintos — inspecione "motivo"/"id_jogador":
            (a) Adversário caiu:
                { "tipo": "DESCONEXAO", "id_jogador": str, "apelido": str,
                  "codigo_sala": str }
            (b) Ninguém entrou a tempo (timeout de espera):
                { "tipo": "DESCONEXAO", "id_jogador": "servidor",
                  "motivo": "timeout_espera", "mensagem": str, "codigo_sala": str }

── Servidor → Cliente (UDP) ───────────────────────────────────────────────

PONG        Resposta ao PING. Ecoa o "ts" recebido para o cliente medir o RTT.
            { "tipo": "PONG", "id_jogador": str, "ts": float (se veio no PING) }

═══════════════════════════════════════════════════════════════════════════
VALORES ESPECIAIS que o frontend precisa tratar
═══════════════════════════════════════════════════════════════════════════
  - vencedor == "nenhum"  → ninguém acertou a rodada (ou deu timeout)
  - vencedor == "empate"  → a partida terminou empatada (só em FIM_JOGO)
  - apelido_vencedor == None → quando não há vencedor definido (nenhum/empate)
"""
import json
from enum import Enum


class TipoMensagem(str, Enum):
    """
    Enum de todos os tipos de mensagem do protocolo.

    Herda de `str` para que `TipoMensagem.ENTRAR == "ENTRAR"` seja verdadeiro,
    facilitando comparações e serialização direta em JSON.
    """
    ENTRAR          = "ENTRAR"           # Cliente → Servidor: entrar na fila
    BEM_VINDO       = "BEM_VINDO"        # Servidor → Cliente: confirma entrada + id definitivo
    PERGUNTA        = "PERGUNTA"         # Servidor → Cliente: nova rodada
    RESPOSTA        = "RESPOSTA"         # Cliente → Servidor: resposta do jogador
    ATUALIZAR_BARRA = "ATUALIZAR_BARRA"  # Servidor → Cliente: posição da barra + placar
    FIM_RODADA      = "FIM_RODADA"       # Servidor → Cliente: resultado da rodada
    FIM_JOGO        = "FIM_JOGO"         # Servidor → Cliente: resultado final
    DESCONEXAO      = "DESCONEXAO"       # Servidor → Cliente: adversário caiu / timeout
    PING            = "PING"             # Cliente → Servidor (UDP): latência
    PONG            = "PONG"             # Servidor → Cliente (UDP): resposta ao ping


def criar_mensagem(tipo_mensagem: TipoMensagem, dados: dict | None = None) -> dict:
    """
    Monta o dicionário de uma mensagem: sempre com "tipo", mais os campos de `dados`.

    Ex.: criar_mensagem(TipoMensagem.ENTRAR, {"id_jogador": "p1"})
         → {"tipo": "ENTRAR", "id_jogador": "p1"}
    """
    mensagem = {"tipo": tipo_mensagem.value if isinstance(tipo_mensagem, TipoMensagem) else str(tipo_mensagem)}
    if dados:
        mensagem.update(dados)
    return mensagem


def codificar_mensagem(mensagem: dict) -> bytes:
    """
    Serializa uma mensagem (dict) para bytes prontos para envio por TCP.

    Formato: [4 bytes big-endian com o tamanho][JSON UTF-8].
    """
    payload = json.dumps(mensagem, ensure_ascii=False).encode("utf-8")
    cabecalho = len(payload).to_bytes(4, byteorder="big", signed=False)
    return cabecalho + payload


def decodificar_mensagem(mensagem_bruta: bytes | str) -> dict:
    """
    Desserializa uma mensagem JSON de volta para dict.

    Aceita tanto o formato com cabeçalho de 4 bytes quanto JSON puro (string
    ou bytes), o que dá flexibilidade para testes e para o canal UDP.
    """
    if isinstance(mensagem_bruta, bytes):
        # Se parece ter cabeçalho de 4 bytes, remove-o antes de decodificar
        if len(mensagem_bruta) >= 4:
            try:
                tamanho = int.from_bytes(mensagem_bruta[:4], byteorder="big", signed=False)
                if tamanho > 0 and len(mensagem_bruta) >= 4 + tamanho:
                    payload = mensagem_bruta[4 : 4 + tamanho]
                    if payload.strip().startswith(b"{"):
                        mensagem_bruta = payload
            except (OverflowError, ValueError):
                pass
        mensagem_bruta = mensagem_bruta.decode("utf-8")
    return json.loads(mensagem_bruta)



