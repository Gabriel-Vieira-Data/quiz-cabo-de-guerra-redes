# Protocolo do Quiz Cabo de Guerra — Guia para o Frontend

Este documento é a **referência única** para construir um frontend que fale com
o servidor. Se algo aqui divergir do código, o código (`src/common/protocol.py`
e `src/server/server.py`) é a fonte da verdade — mas fazemos o possível para
manter os dois sincronizados.

---

## 1. Como os bytes viajam

### TCP (canal do jogo)
Cada mensagem é enquadrada assim:

```
[4 bytes big-endian: N][N bytes de JSON UTF-8]
```

Os 4 primeiros bytes dizem o tamanho do JSON que vem em seguida. Isso é
necessário porque TCP é um fluxo contínuo — sem o cabeçalho, você não saberia
onde uma mensagem acaba e a outra começa.

**Você não precisa implementar isso do zero.** A classe `ClienteQuiz`
(`src/client/client.py`) já faz o enquadramento e o desenquadramento, inclusive
lidando com mensagens fragmentadas ou coladas (rajada).

### UDP (canal de latência)
Datagramas JSON puros, **sem** o cabeçalho de 4 bytes. Usado só para medir ping.

---

## 2. Mensagens que o CLIENTE ENVIA

| Tipo      | Canal | Campos                                          |
|-----------|-------|-------------------------------------------------|
| `ENTRAR`  | TCP   | `id_jogador` (str), `apelido` (str)             |
| `RESPOSTA`| TCP   | `id_jogador` (str), `rodada_id` (int), `resposta` (str) |
| `PING`    | UDP   | `id_jogador` (str), `ts` (float, opcional)      |

> **Importante:** o servidor valida `RESPOSTA` contra o socket que enviou
> (anti-trapaça). Envie sempre o `id_jogador` que você recebeu no `BEM_VINDO`.

**Limites de validação (defesa contra abuso):** o servidor trunca `id_jogador`
para 50 caracteres e `apelido` para 100 caracteres. Mensagens (payload JSON)
acima de 256 KB (`TAMANHO_MAXIMO_MENSAGEM` em `protocol.py`) são rejeitadas.

---

## 3. Mensagens que o CLIENTE RECEBE

### `BEM_VINDO` (ACK de ENTRAR) — TCP
Confirma sua entrada e diz o seu **id definitivo** (o servidor pode ter
renomeado em caso de colisão). **Use este id daqui pra frente.**

```json
{ "tipo": "BEM_VINDO", "id_jogador": "player-1", "apelido": "Alice",
  "em_partida": false, "codigo_sala": null }
```

### `PERGUNTA` — TCP
Início de uma rodada. **Não** contém a resposta correta (anti-trapaça).

```json
{ "tipo": "PERGUNTA", "rodada_id": 1, "pergunta": "Qual protocolo...?",
  "opcoes": ["TCP", "UDP", "ICMP", "ARP"], "tempo_limite": 30 }
```

### `FIM_RODADA` — TCP
Rodada terminou. Aqui a resposta correta **é** revelada, para feedback.

```json
{ "tipo": "FIM_RODADA", "vencedor": "player-1", "apelido_vencedor": "Alice",
  "resposta_correta": "TCP", "rodada": 1, "codigo_sala": "sala-1" }
```

- `vencedor` pode ser um id **ou** a string `"nenhum"` (ninguém acertou/timeout).
- `apelido_vencedor` é `null` quando `vencedor` é `"nenhum"`.

### `ATUALIZAR_BARRA` — TCP
Nova posição da barra e placar.

```json
{ "tipo": "ATUALIZAR_BARRA", "posicao": 2,
  "pontuacao": {"player-1": 2, "player-2": 0},
  "apelidos": {"player-1": "Alice", "player-2": "Bob"} }
```

- `posicao > 0` → **jogador_a** (primeiro da sala) está na frente.
- `posicao < 0` → **jogador_b** está na frente.
- `posicao == 0` → empatado no centro.
- Faixa: de `-5` a `+5`. Atingir `±5` é knockout (vitória imediata).

### `FIM_JOGO` — TCP
Partida encerrada.

```json
{ "tipo": "FIM_JOGO", "vencedor": "player-1", "apelido_vencedor": "Alice",
  "pontuacao": {"player-1": 5, "player-2": 2}, "posicao": 3,
  "apelidos": {"player-1": "Alice", "player-2": "Bob"} }
```

- `vencedor` pode ser um id **ou** a string `"empate"`.
- `apelido_vencedor` é `null` quando `vencedor` é `"empate"`.
- Após ~3s, o servidor reseta a sala e aceita novos jogadores (basta reenviar `ENTRAR`).

### `DESCONEXAO` — TCP (dois casos!)
Inspecione o campo `motivo` / `id_jogador` para distinguir:

**(a) Adversário caiu no meio da partida:**
```json
{ "tipo": "DESCONEXAO", "id_jogador": "player-2", "apelido": "Bob",
  "codigo_sala": "sala-1" }
```

**(b) Ninguém entrou a tempo (timeout de espera):**
```json
{ "tipo": "DESCONEXAO", "id_jogador": "servidor", "motivo": "timeout_espera",
  "mensagem": "Nenhum adversário entrou a tempo. Tente novamente.",
  "codigo_sala": "sala-1" }
```

### `PONG` — UDP
Resposta ao `PING`. Ecoa o `ts` que você enviou, para você calcular o RTT
(latência) subtraindo do relógio local.

```json
{ "tipo": "PONG", "id_jogador": "cliente", "ts": 1712345678.123 }
```

---

## 4. Fluxo típico de uma partida

```
Cliente                          Servidor
  |  --- ENTRAR ------------------>  |
  |  <-- BEM_VINDO ----------------  |   (id definitivo)
  |            (aguarda 2º jogador)  |
  |  <-- PERGUNTA -----------------  |   (rodada 1)
  |  --- RESPOSTA ---------------->  |
  |  <-- FIM_RODADA ---------------  |   (com resposta_correta)
  |  <-- ATUALIZAR_BARRA ----------  |   (nova posição + placar)
  |  <-- PERGUNTA -----------------  |   (rodada 2)
  |            ... repete ...        |
  |  <-- FIM_JOGO -----------------  |   (vencedor + placar final)
```

---

## 5. Valores especiais que você DEVE tratar

| Campo              | Valor especial | Significado                          |
|--------------------|----------------|--------------------------------------|
| `vencedor`         | `"nenhum"`     | ninguém acertou a rodada             |
| `vencedor`         | `"empate"`     | partida empatada (só em `FIM_JOGO`)  |
| `apelido_vencedor` | `null`         | não há vencedor definido             |
| `DESCONEXAO.motivo`| `"timeout_espera"` | ninguém entrou; não é queda de adversário |

---

## 6. Consumindo com a biblioteca `ClienteQuiz`

Você não precisa mexer em sockets. Exemplo mínimo:

```python
from src.client.client import ClienteQuiz

cliente = ClienteQuiz(host="127.0.0.1", porta_tcp=5000, porta_udp=5001)
cliente.conectar()

# Registra callbacks por tipo de mensagem (dispatcher)
cliente.registrar_handler("BEM_VINDO",      lambda m: print("Meu id:", m["id_jogador"]))
cliente.registrar_handler("PERGUNTA",       lambda m: print("Pergunta:", m["pergunta"]))
cliente.registrar_handler("FIM_RODADA",     lambda m: print("Venceu:", m["vencedor"]))
cliente.registrar_handler("ATUALIZAR_BARRA",lambda m: print("Barra:", m["posicao"]))
cliente.registrar_handler("FIM_JOGO",       lambda m: print("Fim:", m["vencedor"]))
cliente.registrar_handler("DESCONEXAO",     lambda m: print("Desconexão:", m))

cliente.escutar_em_thread()          # inicia o loop de recepção numa thread
cliente.enviar_entrada("player-1", "Alice")

# ... quando o usuário responder:
cliente.enviar_resposta(cliente.id_jogador_confirmado, rodada_id, "TCP")

# Medir latência (opcional):
rtt = cliente.medir_latencia()       # retorna ms ou None
```

Métodos úteis do `ClienteQuiz`:

| Método                         | O que faz                                        |
|--------------------------------|--------------------------------------------------|
| `conectar()`                   | abre TCP+UDP e ativa keepalive                   |
| `enviar_entrada(id, apelido)`  | envia `ENTRAR`                                   |
| `enviar_resposta(id, rid, r)`  | envia `RESPOSTA`                                 |
| `registrar_handler(tipo, fn)`  | associa um callback a um tipo de mensagem        |
| `escutar_em_thread()`          | loop de recepção + dispatch em thread daemon     |
| `receber_mensagem()`           | leitura bloqueante de uma mensagem (uso avançado)|
| `definir_timeout(seg)`         | timeout de leitura no socket TCP                 |
| `medir_latencia()`             | envia PING e retorna o RTT em ms                 |
| `id_jogador_confirmado`        | seu id definitivo (preenchido no `BEM_VINDO`)    |
| `latencia_ms`                  | última latência medida                           |
| `fechar()`                     | fecha os sockets e para a escuta                 |
