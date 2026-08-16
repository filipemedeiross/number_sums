# NUMBER SUMS — CSP SEARCH

Biblioteca Python, resolvedor por satisfação de restrições e jogo em Pygame
para gerar, jogar e solucionar tabuleiros de **Number Sums** (também conhecido
como **Sumplete**).

Em cada partida, o jogador deve remover células até que a soma dos números
restantes seja exatamente igual à meta de cada linha e de cada coluna.

<p align="center">
  <img
    src="docs/game.png"
    alt="Interface do Number Sums com tabuleiro 8 por 8, metas, botões e cronômetro"
    width="430"
  >
</p>

<p align="center"><em>Interface Pygame do tabuleiro padrão 8 × 8.</em></p>

A organização desta documentação e a identidade visual do jogo usam como
referência o projeto
[solving_sudoku](https://github.com/filipemedeiross/solving_sudoku), adaptando
a abordagem de busca CSP às restrições de soma do Number Sums.

## Sumário

- [Sobre o projeto](#sobre-o-projeto)
- [Interface e controles](#interface-e-controles)
- [Roteiro de instalação e execução](#roteiro-de-instalação-e-execução)
- [Uso da biblioteca](#uso-da-biblioteca)
- [Modelagem como CSP](#modelagem-como-csp)
- [Como o solver funciona](#como-o-solver-funciona)
- [Geração e validação das partidas](#geração-e-validação-das-partidas)
- [Organização do projeto](#organização-do-projeto)
- [Notebook](#notebook)
- [Testes](#testes)
- [Referências](#referências)
- [Licença](#licença)

## Sobre o projeto

O projeto separa a regra do jogo, o algoritmo de resolução e a interface
gráfica:

- `NumberSumsGame` mantém o tabuleiro, as metas, as decisões e o histórico;
- `NumberSumsCSPSolver` modela e resolve o problema como um CSP;
- `NumberSumsController` coordena ações, dicas e contadores sem depender do
  Pygame;
- `NumberSumsPygameApp` converte eventos do mouse em operações do controlador.

Principais recursos:

- tabuleiros quadrados de `2 × 2` até `8 × 8`, com `8 × 8` como padrão;
- geração aleatória reproduzível por `seed`;
- solução única por padrão na geração;
- células indecisas, removidas ou marcadas para permanecer;
- histórico com restauração, desmarcação e `undo`;
- validação de cada decisão por existência de uma solução compatível;
- dicas de remoção ou permanência calculadas a partir do estado atual;
- propagação GAC, busca com MRV/LCV e backtracking;
- enumeração de soluções, trace completo e estatísticas da busca;
- interface Pygame e notebook interativo.

## Interface e controles

A interface é operada somente pelo mouse:

| Entrada | Ação |
|---|---|
| Clique esquerdo em uma célula | Remove ou restaura a célula |
| Clique direito em uma célula | Marca ou desmarca a célula que deve permanecer |
| `DICA` | Calcula e destaca o próximo movimento, sem aplicá-lo |
| `RESET` | Reinicia o tabuleiro atual |
| `NOVO` | Gera uma nova partida |
| Fechar a janela | Encerra o jogo |

Não há atalhos de teclado. Depois de solicitar uma dica, o jogador ainda
precisa executar o movimento indicado: clique esquerdo para remover ou clique
direito para manter.

Os indicadores exibidos acima e ao lado do tabuleiro usam o formato
`META/SOMA`. O primeiro valor é a meta; o segundo é a soma das células
explicitamente marcadas para permanecer. Por isso, uma nova partida começa com
a segunda parcela igual a zero.

Uma célula marcada recebe contorno verde. Uma célula removida permanece
identificável, mas fica translúcida. Se uma jogada eliminar todas as soluções
compatíveis, ela é rejeitada sem alterar o tabuleiro e o contador
`MOVIMENTOS ERRADOS` é incrementado.

## Roteiro de instalação e execução

Fluxo recomendado:

```text
clonar → criar ambiente virtual → pip install . → instalar requirements → executar
```

### 1. Pré-requisitos

- [Python 3.10 ou mais recente](https://www.python.org/downloads/);
- `pip`;
- Git, caso o projeto ainda não tenha sido baixado.

### 2. Clonar o repositório

```bash
git clone https://github.com/filipemedeiross/number_sums.git
cd number_sums
```

### 3. Criar e ativar um ambiente virtual

Linux ou macOS:

```bash
python -m venv .venv
source .venv/bin/activate
```

Windows PowerShell:

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
```

Atualize o instalador do ambiente:

```bash
python -m pip install --upgrade pip
```

### 4. Instalar a biblioteca

A partir da raiz do repositório:

```bash
python -m pip install .
```

Esse comando instala a distribuição `sumplete`, disponibiliza o pacote Python
`number_sums` e cria o executável `sumplete-game`. A biblioteca e o solver não
dependem do Pygame para uso programático.

### 5. Instalar o Pygame

A interface importa o Pygame incondicionalmente. Instale a versão registrada no
arquivo [requirements.txt](requirements.txt):

```bash
python -m pip install -r requirements.txt
```

Esse passo é obrigatório para abrir a interface e para executar a suíte
completa, que inclui um smoke test gráfico em modo headless.

### 6. Executar o jogo

Depois das duas instalações:

```bash
sumplete-game
```

Entradas equivalentes:

```bash
python -m number_sums
python main.py
```

### Instalação para desenvolvimento

`pip install .` copia o pacote para `site-packages`. Alterações posteriores no
código-fonte só aparecem após uma nova instalação:

```bash
python -m pip install --force-reinstall .
```

Durante o desenvolvimento, prefira uma instalação editável:

```bash
python -m pip install -e ".[dev]"
```

Nesse modo, o ambiente aponta para `src/` e as alterações locais passam a ser
usadas sem reinstalar o pacote. O extra `dev` também instala Pygame, pytest e
JupyterLab.

## Uso da biblioteca

### Criar e resolver uma partida

```python
from number_sums import NumberSumsGame

game = NumberSumsGame.random(
    size=4,
    seed=42,
)

print(game)

# Retorna as coordenadas que devem ser removidas sem alterar o jogo.
solution = game.solve()
print(solution)

# Aplica a solução e atualiza o estado.
game.apply_solution(solution)
assert game.is_won()
```

`NumberSumsGame.random()` usa `8 × 8` por padrão e tenta produzir uma instância
com solução única. Use `unique_solution=False` quando soluções alternativas
forem aceitáveis.

### Solicitar uma dica

```python
game = NumberSumsGame.random(seed=42)

hint = game.next_hint()

if hint is not None:
    print(hint.action, hint.coordinate, hint.reason)

    if hint.action == "remove":
        game.remove_cell(hint.row, hint.column)
    else:
        game.mark_cell(hint.row, hint.column)
```

`next_hint()` considera as remoções e marcações atuais, mas apenas sugere a
próxima ação. Os métodos `NumberSumsGame.solve()` e `find_solutions()` resolvem
o problema original e não aplicam automaticamente as decisões atuais como
hipóteses. Para controlar hipóteses explicitamente, use o solver diretamente.

### API principal do jogo

| API | Finalidade |
|---|---|
| `NumberSumsGame.random(...)` | Gera uma partida solucionável |
| `remove_cell(row, column)` | Remove uma célula, se a decisão for consistente |
| `restore_cell(row, column)` | Libera uma remoção |
| `mark_cell(row, column)` | Confirma que uma célula deve permanecer |
| `unmark_cell(row, column)` | Libera uma confirmação |
| `undo()` | Desfaz a última alteração |
| `reset()` | Restaura o estado inicial |
| `next_hint()` | Sugere uma única ação compatível com o estado |
| `find_solutions(limit=None)` | Enumera soluções do tabuleiro |
| `solve(apply=False)` | Retorna a primeira solução e, opcionalmente, aplica-a |
| `is_won()` | Verifica todas as metas de linhas e colunas |

Uma solução é representada por um `frozenset` de coordenadas `(row, column)`
das células que devem ser removidas.

## Modelagem como CSP

Considere um tabuleiro quadrado `n × n`, com valores `a[r,c]`, metas de linha
`row_target[r]` e metas de coluna `column_target[c]`.

Cada célula possui uma variável booleana:

$$
x_{r,c} \in \{0,1\}
$$

onde:

- $x_{r,c}=1$ significa manter o número;
- $x_{r,c}=0$ significa remover o número.

Para cada linha `r`:

$$
\sum_{c=0}^{n-1} a_{r,c}x_{r,c} = row\_target_r
$$

Para cada coluna `c`:

$$
\sum_{r=0}^{n-1} a_{r,c}x_{r,c} = column\_target_c
$$

O modelo contém:

- `n²` variáveis booleanas;
- `n` restrições de linha;
- `n` restrições de coluna;
- `2n` restrições n-árias no total.

No tabuleiro padrão `8 × 8`, isso corresponde a 64 variáveis e 16 restrições.

## Como o solver funciona

### 1. Restrições tabulares

Cada soma de linha ou coluna é compilada como uma tabela de máscaras válidas.
Para uma restrição com `n` células, o solver examina as `2ⁿ` combinações de
manter/remover e armazena somente as que atingem exatamente a meta.

Uma máscara armazenada é uma atribuição que oferece suporte aos valores das
variáveis daquela restrição. Esse pré-processamento transforma as verificações
de soma em consultas sobre combinações já validadas.

### 2. Propagação com GAC

Antes de tomar decisões, o solver aplica **Generalized Arc Consistency (GAC)**
às restrições tabulares:

1. mantém apenas as máscaras compatíveis com os domínios atuais;
2. verifica se cada valor de cada variável aparece em alguma máscara válida;
3. remove valores que não possuem suporte;
4. recoloca na fila as restrições afetadas;
5. repete até chegar a um ponto fixo ou encontrar uma contradição.

Por exemplo, se nenhuma máscara válida de uma linha mantiver determinada
célula, `1` é removido de seu domínio e a célula fica forçada a `0`.

A GAC pode resolver diretamente instâncias com muitas decisões forçadas.
Entretanto, consistência local não garante uma solução global; quando ainda
existem domínios `{0, 1}`, começa a busca.

### 3. MRV, LCV e backtracking

A busca mantém a propagação ativa após cada decisão:

- **MRV — Minimum Remaining Values:** seleciona uma variável com o menor
  domínio;
- **pressão das restrições:** desempata priorizando células envolvidas em menos
  máscaras ainda compatíveis;
- **LCV — Least Constraining Value:** tenta primeiro o valor que preserva mais
  suportes nas restrições incidentes;
- **backtracking:** restaura os domínios quando um ramo leva a uma contradição;
- **trilha reversível:** registra somente os domínios alterados, evitando uma
  cópia completa a cada nó.

Como os domínios são binários, as variáveis não decididas geralmente empatam
no MRV. Na prática, a pressão das restrições é um desempate importante, e a LCV
é uma aproximação baseada na quantidade de máscaras compatíveis.

### 4. Solução, trace e dicas

`solve()` retorna a primeira solução. `find_solutions()` pode enumerar todas ou
parar em um `limit`. `solve_with_trace()` também registra:

- `propagation`: remoção de valor sem suporte;
- `decision`: escolha feita pela busca;
- `contradiction`: ramo inconsistente;
- `backtrack`: restauração de um ramo;
- `solution`: atribuição completa que satisfaz as metas.

O resultado inclui contadores de nós, backtracks e propagações.
`next_step()` devolve somente a próxima ação observável; quando precisa propor
uma decisão, pode realizar uma busca limitada como look-ahead para evitar um
ramo sem solução. `next_hint()` converte o passo em uma ação de `remove` ou
`mark` para a interface.

### API do solver

| API | Resultado |
|---|---|
| `NumberSumsCSPSolver(board, rows, columns)` | Cria um solver independente |
| `NumberSumsCSPSolver.from_game(game)` | Associa o solver a uma partida |
| `infer(assumptions=...)` | Executa somente GAC e retorna os domínios |
| `solve(assumptions=...)` | Retorna a primeira solução compatível |
| `find_solutions(limit=..., assumptions=...)` | Enumera soluções |
| `is_consistent(assumptions=...)` | Verifica se alguma solução existe |
| `solve_with_trace(assumptions=...)` | Retorna solução, passos e estatísticas |
| `next_step(assumptions=...)` | Retorna uma propagação ou decisão acionável |
| `next_hint()` | Converte o próximo passo em uma dica para o jogo |

Exemplo com hipóteses e trace:

```python
from number_sums import NumberSumsCSPSolver

solver = NumberSumsCSPSolver(
    board=((1, 2), (3, 4)),
    row_targets=(1, 4),
    column_targets=(1, 4),
)

domains = solver.infer(
    assumptions={
        (0, 0): 1,  # manter
        (0, 1): 0,  # remover
    }
)
print(domains)

result = solver.solve_with_trace()
print(result.solution)
print(result.stats)

for step in result.steps:
    print(step.kind, step.cell, step.value, step.reason)
```

Os métodos do solver não modificam o jogo.

### Limites e complexidade

O tamanho máximo é `8 × 8`. Para dimensão `n`:

- cada restrição possui no máximo `2ⁿ` máscaras;
- a construção das tabelas custa `O(n² × 2ⁿ)` em tempo;
- uma revisão de restrição custa até `O(n × 2ⁿ)`;
- a busca completa continua exponencial no pior caso, chegando a
  `O(2^(n²))` atribuições.

Para `n=8`, cada tabela possui no máximo 256 máscaras. Ainda assim, evite
`find_solutions()` sem limite quando somente uma ou poucas soluções forem
necessárias.

## Geração e validação das partidas

A geração cria valores aleatórios e uma máscara não trivial de células mantidas.
As metas são calculadas a partir dessa máscara. Por padrão, o gerador solicita
até duas soluções ao solver e aceita apenas tabuleiros com uma única solução.

Além da geração, o solver protege a regra do jogo:

- o construtor rejeita metas que não admitem solução;
- cada remoção (`0`) ou marcação de permanência (`1`) é testada antes de ser
  registrada;
- uma decisão incompatível levanta `InvalidMoveError` sem alterar o estado;
- dicas são recalculadas a partir das decisões ativas;
- a vitória depende apenas das somas atuais, portanto qualquer solução válida é
  aceita.

A validação é existencial: uma jogada é permitida se ainda houver pelo menos uma
solução compatível, inclusive em tabuleiros configurados para admitir soluções
alternativas.

## Organização do projeto

```text
number_sums/
├── docs/
│   └── game.png
├── notebooks/
│   └── 1_game_logic.ipynb
├── src/
│   └── number_sums/
│       ├── __init__.py
│       ├── __main__.py
│       ├── controller.py
│       ├── game.py
│       ├── pygame_app.py
│       ├── utils.py
│       └── solvers/
│           ├── __init__.py
│           └── csp.py
├── tests/
│   ├── test_controller.py
│   ├── test_csp_solver.py
│   ├── test_game.py
│   └── test_pygame_app.py
├── main.py
├── pyproject.toml
└── requirements.txt
```

## Notebook

O notebook [`1_game_logic.ipynb`](notebooks/1_game_logic.ipynb) demonstra a
geração, a resolução e uma partida textual.

Instale as dependências de desenvolvimento e abra-o com:

```bash
python -m pip install -e ".[dev]"
jupyter lab notebooks/1_game_logic.ipynb
```

Na partida textual, os comandos são `row column`, `keep row column`, `hint`,
`step`, `undo` e `quit`.

## Testes

Instale primeiro o Pygame por meio de `requirements.txt`. Para executar a suíte
com `unittest`:

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

Executar apenas um módulo:

```bash
PYTHONPATH=src python -m unittest -v tests.test_csp_solver
```

Executar uma classe ou um teste específico:

```bash
PYTHONPATH=src python -m unittest -v \
  tests.test_csp_solver.NumberSumsCSPSolverTests

PYTHONPATH=src python -m unittest -v \
  tests.test_csp_solver.NumberSumsCSPSolverTests.test_limit_and_assumptions
```

Em um ambiente sem servidor gráfico:

```bash
SDL_VIDEODRIVER=dummy \
PYTHONPATH=src \
python -m unittest discover -s tests -v
```

## Referências

- [filipemedeiross/solving_sudoku](https://github.com/filipemedeiross/solving_sudoku):
  referência de organização, interface e uso de busca CSP em jogos.
- Stuart Russell e Peter Norvig,
  [*Artificial Intelligence: A Modern Approach*](https://aima.cs.berkeley.edu/):
  CSP, propagação, backtracking, MRV e LCV.
- David Poole e Alan Mackworth,
  [*Artificial Intelligence: Foundations of Computational Agents — Generalized
  Arc Consistency*](https://www.cs.ubc.ca/~poole/aibook/3e/html/ArtInt3e.Ch4.S3.html).
- Alan K. Mackworth,
  [“Consistency in Networks of Relations”](https://www.cs.ubc.ca/~mack/Publications/b2hd-AI77.html),
  *Artificial Intelligence*, 8(1), 1977.
- [Documentação do Pygame](https://www.pygame.org/docs/).
- [pip — instalação de projetos locais](https://pip.pypa.io/en/stable/topics/local-project-installs/).
- [Python — ambientes virtuais](https://docs.python.org/3/library/venv.html).

## Licença

Distribuído sob a licença MIT. Consulte [LICENSE](LICENSE).
