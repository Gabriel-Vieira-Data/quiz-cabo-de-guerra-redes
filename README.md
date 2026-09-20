# quiz-cabo-de-guerra-redes
Projeto de Redes de Computadores - Quiz 1v1 com Sockets em Python

## Como executar

### 1. Iniciar o servidor

```bash
python -m src.server.server
```

### 2. Abrir a interface gráfica para testar o jogo

Primeiro terminal (jogador 1):

```bash
python -m src.client.gui --id-jogador player-1 --apelido Alice --porta-udp 5002
```

Segundo terminal (jogador 2):

```bash
python -m src.client.gui --id-jogador player-2 --apelido Bob --porta-udp 5003
```

Cada janela representa um jogador e usa sua própria porta UDP, permitindo testar o jogo em duas interfaces ao mesmo tempo no mesmo computador.

### 3. Rodar testes

```bash
python -m pytest -q
```
