from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing      import TYPE_CHECKING, Iterable, Iterator, Literal, Mapping, Sequence

from ..game  import NumberSumsGame
from ..utils import Hint, NoSolutionError


Coordinate  = tuple  [int, int]
DomainValue = Literal[0  , 1  ]

Domains     = dict   [Coordinate, set[int]]
Assumptions = Mapping[Coordinate, int     ]

StepKind    = Literal[
    "propagation"  ,
    "decision"     ,
    "contradiction",
    "backtrack"    ,
    "solution"     ,
]


@dataclass(frozen=True, slots=True)
class SumConstraint:
    """Tabular constraint equivalent to a weighted sum"""

    name          : str
    target        : int
    variables     : tuple[Coordinate, ...]
    weights       : tuple[int       , ...]
    allowed_masks : tuple[int       , ...]


@dataclass(frozen=True, slots=True)
class CSPStep:
    """An observable step of propagation or search"""

    kind  : StepKind
    depth : int

    cell  : Coordinate  | None
    value : DomainValue | None

    removed_values : tuple[DomainValue, ...]
    reason         : str


@dataclass(frozen=True, slots=True)
class CSPStats:
    """Counters of a solver execution"""

    nodes        : int
    backtracks   : int
    propagations : int


@dataclass(frozen=True, slots=True)
class CSPResult:
    """Solution accompanied by the full search trace"""

    solution : frozenset[Coordinate  ]
    steps    : tuple    [CSPStep, ...]
    stats    : CSPStats


@dataclass(slots=True)
class _MutableStats:
    nodes        : int = 0
    backtracks   : int = 0
    propagations : int = 0

    def freeze(self) -> CSPStats:
        return CSPStats(self.nodes, self.backtracks, self.propagations)


class NumberSumsCSPSolver:
    """
    Solves Number Sums using constraint propagation and backtracking.

    Args:
        board          : Square matrix of positive integers.
        row_targets    : Target for each row.
        column_targets : Target for each column.

    Use :meth:`from_game` to construct the solver from a game instance. The
    solving methods do not modify the game or retain state between searches.
    """

    REMOVE : DomainValue = 0
    KEEP   : DomainValue = 1

    MAX_SIZE = 8

    def __init__(
        self,
        board          : Sequence[Sequence[int]],
        row_targets    : Sequence[int],
        column_targets : Sequence[int],
        *,
        game: NumberSumsGame | None = None,
    ) -> None:
        self._board          = tuple(tuple(row) for row in board)
        self._row_targets    = tuple(row_targets   )
        self._column_targets = tuple(column_targets)

        self._validate_problem()

        self._game = game

        self._variables   = tuple(
            (row, column)
            for row    in range(self.size)
            for column in range(self.size)
        )
        self._constraints = self._build_constraints()

        constraints_by_variable: dict[Coordinate, list[int]] = {
            variable : [] for variable in self._variables
        }
        for index, constraint in enumerate(self._constraints):
            for variable in constraint.variables:
                constraints_by_variable[variable].append(index)

        self._constraints_by_variable = {
            variable : tuple(indices)
            for variable, indices in constraints_by_variable.items()
        }

        self._neighbors = {
            variable : frozenset(
                neighbor
                for index    in self._constraints_by_variable[variable]
                for neighbor in self._constraints[index].variables
                if  neighbor != variable
            )
            for variable in self._variables
        }

    @classmethod
    def from_game(cls, game: NumberSumsGame) -> NumberSumsCSPSolver:
        """Creates a solver linked to the game so that hints use its current state"""

        return cls(
            game.board         ,
            game.row_targets   ,
            game.column_targets,

            game=game,
        )

    @property
    def size(self) -> int:
        return len(self._board)

    @property
    def variables(self) -> tuple[Coordinate, ...]:
        return self._variables

    @property
    def constraints(self) -> tuple[SumConstraint, ...]:
        return self._constraints

    @property
    def neighbors(self) -> Mapping[Coordinate, frozenset[Coordinate]]:
        return self._neighbors.copy()

    @property
    def domains(self) -> Mapping[Coordinate, frozenset[DomainValue]]:
        """Initial CSP domains, exposed as immutable copies"""

        return {
            variable : frozenset((self.REMOVE, self.KEEP))
            for variable in self._variables
        }
