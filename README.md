# Quiz Cabo de Guerra — Redes de Computadores

Duelo de perguntas 1v1 em tempo real via sockets TCP/UDP em Python puro
(sem bibliotecas que escondam os sockets).

## Como jogar (jeito fácil — Windows)

Dê **duplo clique** no arquivo `iniciar_jogo.bat`. Ele detecta o Python
automaticamente e abre três janelas: o servidor e dois jogadores. Em cada janela
de jogador, digite seu nome (até 20 caracteres) e clique em **Conectar**. A
partida começa quando os dois estiverem conectados.

## Como jogar (manual — 3 terminais)

Abra 3 terminais na pasta do projeto.

**Terminal 1 — Servidor**

```
python -m src.server.server
```

Aguarde aparecer:

```
[TCP] Servidor ouvindo em 0.0.0.0:5000
[UDP] Servidor ouvindo em 0.0.0.0:5001
Servidor pronto em 0.0.0.0:5000 (UDP: 5001)
```

**Terminais 2 e 3 — Jogadores**

```
python -m src.client.gui --id-jogador player-1
python -m src.client.gui --id-jogador player-2
```

Para jogar em computadores diferentes, passe o IP do servidor com `--host`.

## Regras

- Ambos recebem a mesma pergunta ao mesmo tempo (até 10 rodadas, 30 s cada).
- Quem responder **corretamente primeiro** vence a rodada e puxa a corda para o seu lado.
- A corda mostra a **diferença** de rodadas vencidas: quando um jogador abre
  **3 de vantagem**, ele vence na hora.
- Se as 10 rodadas acabarem, vence quem estiver com a corda do seu lado; com a
  corda no centro, desempata por pontos ou termina empatado.
- Depois de cada pergunta, a resposta correta fica na tela por 2 segundos antes da próxima.
- Se um jogador cair no meio da partida, ela fica **em espera por 30 segundos**. Ele volta
  clicando em **Reconectar** (ou abrindo o jogo de novo com o mesmo `--id-jogador`) e a
  pergunta é reenviada aos dois. Se não voltar a tempo, a partida é encerrada. Se os dois
  caírem, cada um tem os seus 30 segundos.
- Ao fim da partida, **Jogar novamente** recomeça sem reconectar (quando os dois clicarem).

**Atalhos de teclado:** teclas `1`–`4` selecionam a opção e `Enter` envia a resposta.

## Protocolo de mensagens (10 tipos)

| Tipo              | Direção          | Transporte | Descrição                                        |
|-------------------|------------------|------------|--------------------------------------------------|
| `ENTRAR`          | Cliente→Servidor | TCP        | Entra na fila com id e apelido                   |
| `BEM_VINDO`       | Servidor→Cliente | TCP        | Confirma a entrada e envia o id definitivo       |
| `PERGUNTA`        | Servidor→Cliente | TCP        | Pergunta, opções e tempo limite (sem o gabarito) |
| `RESPOSTA`        | Cliente→Servidor | TCP        | Resposta do jogador para a rodada atual          |
| `FIM_RODADA`      | Servidor→Cliente | TCP        | Vencedor da rodada e resposta correta            |
| `ATUALIZAR_BARRA` | Servidor→Cliente | TCP        | Nova posição da corda e placar                   |
| `FIM_JOGO`        | Servidor→Cliente | TCP        | Resultado final (vencedor ou empate)             |
| `DESCONEXAO`      | Servidor→Cliente | TCP        | Adversário saiu ou ninguém entrou a tempo        |
| `PING`            | Cliente→Servidor | UDP        | Medição de latência, a cada 2 s                  |
| `PONG`            | Servidor→Cliente | UDP        | Resposta ao PING; a interface mostra "Ping: N ms"|

**Formato no TCP:** `[4 bytes big-endian: tamanho][payload JSON UTF-8]`. O
cabeçalho de tamanho é necessário porque o TCP é um fluxo de bytes: sem ele, o
receptor não saberia onde uma mensagem termina e a próxima começa.

**Formato no UDP:** datagrama JSON puro, sem cabeçalho (cada datagrama já chega inteiro).

Os campos de cada mensagem estão descritos no início de `src/common/protocol.py`.

## Estrutura

```
src/
├── common/
│   ├── protocol.py         tipos de mensagem e codificação
│   ├── game_logic.py       regras do jogo (corda, placar, vitória)
│   └── banco_perguntas.py  perguntas (data/perguntas_redes.json)
├── server/server.py        servidor: sockets, fila, sala, rodadas, timers
└── client/
    ├── client.py           sockets do cliente e enquadramento das mensagens
    └── gui.py              interface Tkinter
```

## Rodar os testes

```
python -m pytest -q
```

## Uso de IA

Veja `USO_DE_IA.md`.
