# Guia do Backend — Quiz Cabo de Guerra

Documento para quem vai **mexer no backend** (ex.: expor novas funções para o
frontend). Explica a arquitetura, onde estender com segurança e o que evitar.

> Para apenas **consumir** o backend (contrato de mensagens), veja `PROTOCOLO.md`.

---

## 1. Mapa dos arquivos

```
src/
├── common/                 ← código compartilhado entre cliente e servidor
│   ├── protocol.py         ← tipos de mensagem + serialização (wire format)
│   ├── game_logic.py       ← regras puras do jogo (sem rede): EstadoJogo, barra, vitória
│   └── banco_perguntas.py  ← fonte das perguntas (JSON ou embutido)
├── server/
│   └── server.py           ← ServidorQuiz: sockets, salas, rodadas, timers
└── client/
    ├── client.py           ← ClienteQuiz: transporte + dispatcher (use no front)
    └── gui.py              ← interface Tkinter (referência de UI)
```

**Regra de ouro:** a lógica de jogo (`game_logic.py`) é **pura** — não conhece
sockets. A rede fica só no `server.py`/`client.py`. Se você criar uma nova regra
de jogo, coloque em `game_logic.py` e o servidor a usa.

---

## 2. As três camadas

### Camada 1 — Protocolo (`protocol.py`)
Define **o que** pode ser dito na rede. Se você adicionar uma mensagem nova:
1. Adicione o valor no enum `TipoMensagem`.
2. Documente os campos no docstring do topo do arquivo **e** no `PROTOCOLO.md`.
3. Trate-a no servidor (`processar_mensagem`) e/ou no cliente (dispatcher).

### Camada 2 — Regras do jogo (`game_logic.py`)
`EstadoJogo` guarda o estado de uma partida (barra, placar, rodada, vencedor).
Métodos-chave:
- `registrarResultadoRodada(vencedor)` — aplica o resultado de uma rodada
- `verificar_fim_de_jogo()` — decide o vencedor no fim (chame ANTES de `avancar_rodada`)
- `avancar_rodada()` — passa para a próxima rodada
- `terminou()` — booleano de conveniência

Estender aqui é **seguro**: são funções puras, fáceis de testar isoladamente.

### Camada 3 — Servidor (`server.py`)
`ServidorQuiz` orquestra tudo. Organizado em seções (procure pelos comentários
`# ---`): identificação de jogadores, fila/salas, perguntas, processamento de
mensagens, lógica de rodada, timeouts, rede (envio/recepção), inicialização.

---

## 3. Onde ESTENDER com segurança

Estes são os pontos de entrada certos para adicionar funcionalidade:

| Quero...                                   | Mexa em...                                    |
|--------------------------------------------|-----------------------------------------------|
| Adicionar um novo tipo de mensagem         | `protocol.py` (enum) + `processar_mensagem`   |
| Tratar uma mensagem nova do cliente        | `processar_mensagem()` → crie um `_handle_xxx`|
| Enviar algo novo para os jogadores da sala | `transmitir_para_sala(codigo, tipo, dados)`   |
| Enviar algo para todos os conectados       | `transmitir(tipo, dados)`                     |
| Mudar regra de vitória / barra             | `game_logic.EstadoJogo`                       |
| Mudar seleção de perguntas                 | `selecionar_pergunta_para_sala()`             |
| Mudar tempo de rodada / espera             | `self.tempo_limite_rodada`, `self.tempo_limite_espera` (no `__init__`) |
| Adicionar campo numa mensagem existente    | o método que a monta (`_resolver_rodada`, `_enviar_fim_jogo`, etc.) |

### Exemplo: adicionar uma mensagem "PLACAR" sob demanda

```python
# 1. protocol.py
class TipoMensagem(str, Enum):
    ...
    PLACAR = "PLACAR"

# 2. server.py — dentro de processar_mensagem()
if tipo == TipoMensagem.PLACAR.value:
    return self._handle_pedido_placar(mensagem, socket_remetente)

# 3. server.py — novo handler
def _handle_pedido_placar(self, mensagem, socket_remetente):
    codigo = self._obter_codigo_sala_do_jogador(
        self.socket_para_jogador.get(id(socket_remetente))
    )
    estado = self.estado_por_sala.get(codigo)
    if estado:
        self._enviar_mensagem_socket(socket_remetente, TipoMensagem.PLACAR, {
            "pontuacao": estado.pontuacao_jogadores,
            "posicao": estado.posicao_barra,
        })
```

---

## 4. O que NÃO mexer (a menos que saiba o que faz)

Estas partes são delicadas por causa de concorrência (threads):

- **`self._lock` (RLock)** — protege o estado compartilhado. Qualquer leitura/
  escrita em `salas`, `estado_por_sala`, `rodadas_por_sala`, etc. deve estar
  dentro de `with self._lock:`. **Nunca** faça `sendall`/`transmitir` segurando
  o lock em loop longo — envie fora do lock (veja o padrão em `registrar_resposta_jogador`).
- **`_processar_buffer_cliente`** — o parser de framing TCP. Já trata rajada,
  fragmentação e lixo. Mexer aqui pode reintroduzir perda de mensagens.
- **`processar_mensagens_de_conexao`** — o loop de recepção por conexão. Roda
  em thread própria e trata desconexão no final.
- **Os `threading.Timer`** (`_agendar_timeout_rodada`, `_agendar_timeout_espera`,
  o timer de próxima rodada) — sempre cancele o antigo antes de criar um novo,
  senão vazam timers.

---

## 5. Código de compatibilidade (existe só para os testes)

Estes métodos **não** fazem parte do fluxo real de rede — existem apenas porque
os testes unitários os usam como atalho. Não construa o frontend em cima deles:

- `_EstadoJogoProxy` e `self.estado_jogo` — o estado real vive em
  `self.estado_por_sala[codigo]`, não no proxy global.
- No fim do `server.py`: `lidar_com_pergunta`, `processar_resposta`,
  `avancar_rodada` (versão do servidor), `registrar_pontuacao`,
  `iniciar_partida`, `criar_sala`, `registrar_jogador`, `remover_jogador`.

O código morto (métodos e aliases sem nenhum uso, além do módulo
`socket_utils.py`) já foi removido. O que sobrou de "compatibilidade" ainda é
usado ativamente pelos testes, então removê-lo exigiria reescrever os testes.

---

## 6. Estado interno do servidor (referência rápida)

| Atributo                 | O que guarda                                   |
|--------------------------|------------------------------------------------|
| `jogadores_conectados`   | `{ id_jogador: socket }`                       |
| `apelidos`               | `{ id_jogador: apelido }`                      |
| `socket_para_jogador`    | `{ id(socket): id_jogador }` (anti-trapaça)    |
| `fila_espera`            | lista de ids aguardando adversário             |
| `salas`                  | `{ codigo: {codigo, jogadores, estado, ...} }` |
| `partidas_ativas`        | `{ codigo: {rodada, estado, jogadores} }`      |
| `estado_por_sala`        | `{ codigo: EstadoJogo }` ← **estado real**     |
| `rodadas_por_sala`       | dados da rodada corrente (respostas, timeout)  |
| `perguntas_rodada`       | `{ codigo: pergunta_atual }` (com gabarito)    |

> Hoje há **uma sala por vez** (código fixo `"sala-1"`). Para suportar várias
> partidas simultâneas, `criar_sala_para_espera` precisaria gerar códigos únicos
> e parar de limpar salas anteriores.

---

## 7. Rodando e testando

```bash
# Servidor
python -m src.server.server

# Testes (55 no total)
python -m pytest -q
```

Ao adicionar funcionalidade, adicione um teste em `tests/`. Os testes usam
sockets fake (objetos com `recv`/`sendall`) para não depender de rede real —
veja `tests/test_melhorias_rede_jogo.py` como modelo.
