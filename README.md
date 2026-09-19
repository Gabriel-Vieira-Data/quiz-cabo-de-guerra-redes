# quiz-cabo-de-guerra-redes
Projeto de Redes de Computadores - Quiz 1v1 com Sockets em Python

## Como executar

### 1. Iniciar o servidor

```bash
python -m src.server.server
```

### 2. Abrir dois clientes

No terminal 1:

```bash
python - <<'PY'
from src.client.client import ClienteQuiz

cliente = ClienteQuiz(host='127.0.0.1', porta_tcp=5000, porta_udp=5002)
cliente.conectar()
cliente.enviar_entrada('player-1', 'Alice')
print(cliente.receber_mensagem())
PY
```

No terminal 2:

```bash
python - <<'PY'
from src.client.client import ClienteQuiz

cliente = ClienteQuiz(host='127.0.0.1', porta_tcp=5000, porta_udp=5003)
cliente.conectar()
cliente.enviar_entrada('player-2', 'Bob')
print(cliente.receber_mensagem())
PY
```

### 3. Enviar resposta

```python
cliente.enviar_resposta('player-1', 1, 'TCP')
```

### 4. Rodar testes

```bash
python -m pytest -q
```
