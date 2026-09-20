# Quiz Cabo de Guerra — Redes de Computadores

Duelo de perguntas 1v1 em tempo real via sockets TCP/UDP em Python puro.

## Como jogar

Você precisa de **3 terminais** abertos na pasta do projeto.

---

### Terminal 1 — Servidor

```
python -m src.server.server
```

Aguarde aparecer:
```
[TCP] Servidor ouvindo em 0.0.0.0:5000
[UDP] Servidor ouvindo em 0.0.0.0:5001
Servidor pronto em 0.0.0.0:5000 (UDP: 5001)
```

---

### Terminal 2 — Jogador 1 (Alice)

```
python -m src.client.gui --id-jogador player-1 --apelido Alice --porta-udp 5002
```

---

### Terminal 3 — Jogador 2 (Bob)

```
python -m src.client.gui --id-jogador player-2 --apelido Bob --porta-udp 5003
```

Assim que os dois clientes clicarem em **Conectar**, a partida começa automaticamente.

---

## Regras

- 10 rodadas por partida
- Ambos recebem a mesma pergunta ao mesmo tempo
- Quem responder **corretamente primeiro** vence a rodada e puxa a barra para o seu lado
- A barra vai de **−5 a +5**: quem atingir ±5 vence por knockout antes das 10 rodadas
- Se terminar as 10 rodadas, vence quem estiver com a barra do seu lado (ou mais pontos em caso de empate)

---

## Protocolo de mensagens (9 tipos TCP + 1 UDP)

| Tipo             | Direção         | Descrição                                      |
|------------------|-----------------|------------------------------------------------|
| `ENTRAR`         | Cliente→Servidor | Jogador entra na fila com seu ID e apelido    |
| `PERGUNTA`       | Servidor→Cliente | Envia a pergunta, opções e tempo limite        |
| `RESPOSTA`       | Cliente→Servidor | Jogador envia sua resposta                     |
| `ATUALIZAR_BARRA`| Servidor→Cliente | Nova posição da barra e placar                 |
| `FIM_RODADA`     | Servidor→Cliente | Resultado da rodada (vencedor)                 |
| `FIM_JOGO`       | Servidor→Cliente | Resultado final da partida                     |
| `DESCONEXAO`     | Servidor→Cliente | Avisa que o adversário saiu                    |
| `PING`           | Cliente→Servidor | Verificação de latência (UDP)                  |
| `PONG`           | Servidor→Cliente | Resposta ao ping (UDP)                         |
| `PRONTO`         | —               | Reservado para uso futuro                      |

Formato wire: `[4 bytes big-endian: tamanho][payload JSON UTF-8]`

---

## Rodar os testes

```
python -m pytest -q
```
