# Declaração de uso de Inteligência Artificial

Projeto: **Quiz Cabo de Guerra em Tempo Real (Duelo 1v1)** — Redes de Computadores
Integrantes: Gabriel Vieira, Lucas Bitencourt
Ferramenta usada: Kiro (assistente de programação com IA), em setembro de 2026

Este documento descreve, de forma transparente, onde a IA foi usada no
desenvolvimento e o que é código autoral (feito pelos integrantes sem IA).

## Resumo

A estrutura inicial do projeto foi criada pelos integrantes. Depois, uma
parte grande da implementação (refatoração do servidor, correções de bugs,
interface gráfica, animações, medição de ping, testes e documentação) foi
escrita com a IA, sob direção dos integrantes, que definiram as regras do jogo
e as decisões de design, testaram o jogo manualmente e relataram os problemas
encontrados.

Medição feita com `git blame` sobre a versão atual. Contam as linhas de código
não vazias; linhas que são só comentário (`# ...`) não entram:

| Parte | Linhas | Escrito com IA | Autoral |
|---|---|---|---|
| Código da aplicação (`src/` + `iniciar_jogo.bat`) | 2712 | 82,2% | 17,8% |
| Testes automatizados (`tests/`) | 1085 | 67,6% | 32,4% |
| Documentação e dados | 341 | 51,9% | 48,1% |

Linhas originais que foram depois modificadas pela IA contam como "escrito com IA".

**Commits feitos com a IA** (todos com a identidade `Gabriel-Vieira-Data`):
`3201e27`, `1480be2`, `069b2c4` e todo commit cuja mensagem começa com `ia:`.
Os demais commits são dos integrantes, feitos sem IA.

A coluna "Autoral" corresponde aos commits feitos pelos integrantes sem o Kiro,
**exceto** os trechos listados em
["Trechos da base inicial gerados com IA"](#trechos-da-base-inicial-gerados-com-ia),
que foram gerados com auxílio de IA e estão somados na coluna "Escrito com IA".

## Código autoral (feito sem IA)

- **Base inicial do sistema**: protocolo de mensagens, camada de rede TCP/UDP
  com sockets, fila de espera, criação de sala, fluxo de rodada, banco de
  perguntas e os primeiros testes — exceto os trechos gerados com IA listados abaixo.
- **Banco de perguntas** (`data/perguntas_redes.json` e quase todo
  `src/common/banco_perguntas.py`), incluindo o carregamento com validação.
- **Melhorias de interface e de rede** feitas sem IA: efeito de hover nos
  botões, atalhos de teclado, retângulos arredondados, timeout de leitura nos
  sockets e limite de tamanho das mensagens.
- **Regras e decisões de design** passadas à IA: vitória por diferença de 3
  (cabo de guerra real), limite de 10 tipos de mensagem, sem partidas
  simultâneas, nome obrigatório com limite de 20 caracteres, rematch sem
  reconectar, embaralhamento das opções, animações de fim de jogo, uso das
  mensagens UDP (PING/PONG) na interface.
- **Testes manuais e relato de bugs**, que guiaram as correções:
  - resposta atrasada de uma rodada anterior dando vitória indevida;
  - jogador que acertou não pontuando quando o outro não respondia;
  - "Jogar novamente" iniciando a partida antes do adversário aceitar;
  - alerta indevido ao conectar e resposta certa sempre na 1ª opção;
  - layout cortando elementos na tela.

## O que foi escrito com IA

### Trechos da base inicial gerados com IA

Trechos dos commits anteriores ao Kiro que foram gerados com auxílio de IA.
No código, estão marcados com `# [IA - base inicial]`:

- **Geração de id único com expressão regular** — função
  `_gerar_id_jogador_disponivel` em `src/server/server.py`: separa nome e
  número do id com `re.fullmatch(r"(.+?)-?(\d+)?")`, testa candidatos e usa
  timestamp como último recurso.
- **Enquadramento das mensagens TCP** — cabeçalho de 4 bytes big-endian e
  leitura com modo de compatibilidade (aceita mensagem com ou sem cabeçalho):
  - `codificar_mensagem` e `decodificar_mensagem` em `src/common/protocol.py`;
  - `_extrair_mensagens_do_buffer` em `src/client/client.py`;
  - `_processar_buffer_cliente` e o buffer de `processar_mensagens_de_conexao`
    em `src/server/server.py`.
- **Trava reentrante `threading.RLock`** — criação em `ServidorQuiz.__init__`
  e os blocos `with self._lock` em `src/server/server.py`.
- **Herança `class TipoMensagem(str, Enum)`** em `src/common/protocol.py`.

### Servidor — `src/server/server.py` (655 de 746 linhas, incluindo os trechos acima)
- Integração do estado do jogo com o servidor (placar, posição da corda, fim de jogo).
- Mensagens `BEM_VINDO`, `ATUALIZAR_BARRA` e `FIM_JOGO` no fluxo real.
- Validação de `rodada_id` para descartar respostas atrasadas.
- Timeout de rodada que pontua quem já acertou.
- Reentrada no mesmo socket ("Jogar novamente") e limpeza imediata da sala.
- Correção do registro do socket (id renomeado), `SO_KEEPALIVE`, limites de tamanho de campos.
- Embaralhamento das opções e limite de 20 caracteres no apelido.
- Resposta ao `PING` com `PONG` pelo UDP.

### Cliente de rede — `src/client/client.py` (141 de 163 linhas, incluindo os trechos acima)
- Leitura resiliente de mensagens TCP.
- `PING`/`PONG` por UDP com medição da latência (RTT) e descarte de PONGs atrasados.

### Lógica do jogo — `src/common/game_logic.py` (89 de 98 linhas)
- Reescrita da regra de vitória para diferença de 3 (`vantagem_para_vencer`, `LIMITE_BARRA`).

### Protocolo — `src/common/protocol.py` (118 de 134 linhas, incluindo os trechos acima)
- Documentação do formato de cada mensagem, enum com os 10 tipos, parser resiliente.

### Interface gráfica — `src/client/gui.py` (1141 de 1298 linhas)
- Layout completo: cartões dos jogadores, corda desenhada em Canvas, painel da
  pergunta, barra de tempo, histórico colorido, área rolável.
- Campo de nome obrigatório com contador e validação de 20 caracteres.
- "Jogar novamente" reaproveitando a conexão.
- Animações: balanço da corda, bonecos puxando, efeito elástico do nó e telas
  de vitória, derrota e empate.
- Indicador "Ping: N ms", atualizado a cada 2 s por uma thread que envia `PING` pelo UDP.

### Outros
- `iniciar_jogo.bat` (script para abrir servidor e clientes).
- Testes novos: `test_melhorias_rede_jogo.py`, `test_bug_rodada_atrasada.py`,
  `test_timeout_com_acerto.py`, `test_validacao_perguntas.py`, a nova versão de
  `test_ping_udp.py` e `test_fluxo_pergunta_resposta.py`, e ajustes nos existentes.
- Documentação: a maior parte do `README.md`.
- Limpeza: remoção de código sem uso e de funções que existiam só para testes
  antigos (e dos testes que dependiam delas).

## Marcação no código

A origem também está indicada diretamente no código-fonte:

- `# [Origem: IA]` ou `# [Origem: autoral]` acima de cada classe, função e
  método (em `src/`) e no topo de cada arquivo de teste. Quando a função
  mistura origens, o comentário mostra a porcentagem de cada uma, ex.:
  `# [Origem: IA 55% · autoral 45%]`. O rótulo único é usado quando uma origem
  tem 90% ou mais das linhas.
- `# [IA - base inicial]` nos trechos da base inicial que foram gerados com IA
  (lista na seção acima).
- `iniciar_jogo.bat` tem a marcação no cabeçalho (`REM [Origem: IA]`).

Os comentários explicativos (docstrings e comentários sobre sockets, buffer
TCP, threads, UDP e animações) também foram escritos com IA.

## Como a IA foi usada

A IA recebeu os requisitos e os relatos de bugs dos integrantes, propôs e
escreveu as mudanças e rodou os testes automatizados. Os integrantes testaram
cada versão jogando pela interface, aprovaram ou pediram ajustes, e decidiram o
que entrava no projeto.
