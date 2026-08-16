from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing      import Iterable, Literal, Mapping, Sequence

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
    variables     : tuple[Coordinate, ...]
    weights       : tuple[int       , ...]
    target        : int
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

    def infer(
        self,
        assumptions : Assumptions | None = None,
    ) -> Mapping[Coordinate, frozenset[DomainValue]]:
        """
        Applies only GAC and returns the resulting domains.

        ``assumptions`` may fix cells to ``0`` (remove) or ``1`` (keep).
        A contradiction raises :class:`NoSolutionError`.
        """

        domains = self._initial_domains(assumptions)

        trail : list[tuple[Coordinate, frozenset[int]]] = []
        stats                                           = _MutableStats()

        if not self._propagate(
            domains                      ,
            range(len(self._constraints)),

            trail,
            None ,
            0    ,
            stats,
        ):
            raise NoSolutionError("The provided assignments make the CSP inconsistent.")

        return {
            variable : frozenset(domain)
            for variable, domain in domains.items()
        }

    def find_solutions(
        self,
        limit       : int         | None = None,
        *,
        assumptions : Assumptions | None = None,
    ) -> list[frozenset[Coordinate]]:
        """Enumerates solutions as sets of coordinates to remove"""

        self._validate_limit(limit)

        solutions, _, _ = self._run(
            limit, assumptions, capture_trace=False
        )

        return solutions

    def solve(
        self,
        *   ,
        assumptions : Assumptions | None = None,
    ) -> frozenset[Coordinate]:
        """Returns a CSP solution without modifying the game"""

        solutions = self.find_solutions(limit=1, assumptions=assumptions)

        if not solutions:
            raise NoSolutionError("The board has no solution for the given state.")

        return solutions[0]

    def solve_with_trace(
        self,
        *   ,
        assumptions : Assumptions | None = None,
    ) -> CSPResult:
        """Returns a solution and all propagation and search steps"""

        solutions, steps, stats = self._run(1, assumptions, capture_trace=True)

        if not solutions:
            raise NoSolutionError("The board has no solution for the given state.")

        return CSPResult(solutions[0], tuple(steps), stats.freeze())

    def is_consistent(self, assumptions: Assumptions | None = None) -> bool:
        """Returns whether there exists at least one solution for the given decisions"""

        return bool(self.find_solutions(limit=1, assumptions=assumptions))

    def _compatible_masks(
        self,
        constraint : SumConstraint,
        domains    : Domains      ,
        *,
        override : tuple[Coordinate, int] | None = None,
    ) -> tuple[int, ...]:
        override_variable, override_value = override or (None, None)

        compatible : list[int] = []
        for mask in constraint.allowed_masks:
            for position, variable in enumerate(constraint.variables):
                value  = (mask >> position) & 1
                domain = (
                    {override_value}
                    if   variable == override_variable
                    else domains[variable]
                )

                if value not in domain:
                    break
            else:
                compatible.append(mask)

        return tuple(compatible)

    def _is_complete_solution(self, domains: Domains) -> bool:
        return all(
            any(
                all(
                    next(iter(domains[variable])) == ((mask >> position) & 1)
                    for position, variable in enumerate(constraint.variables)
                )
                for mask in constraint.allowed_masks
            )
            for constraint in self._constraints
        )

    def _initial_domains(self, assumptions: Assumptions | None) -> Domains:
        domains = {
            variable : {self.REMOVE, self.KEEP}
            for variable in self._variables
        }

        if assumptions is None:
            return domains
        if not isinstance(assumptions, Mapping):
            raise TypeError("Assumptions must map coordinates to 0 or 1.")

        for variable, value in assumptions.items():
            self._validate_variable(variable)

            if not isinstance(value, int ) \
               or  isinstance(value, bool) \
               or  value not in (0, 1):
                raise ValueError("Each assumption must use 0 (remove) or 1 (keep).")

            domains[variable] = {value}

        return domains

    def _build_constraints(self) -> tuple[SumConstraint, ...]:
        constraints : list[SumConstraint] = []

        for row in range(self.size):
            variables = tuple(
                (row, column)
                for column in range(self.size)
            )

            constraints.append(
                self._make_constraint(
                    f"Linha {row + 1}",
                    variables             ,
                    self._board[row]      ,
                    self._row_targets[row],
                )
            )

        for column in range(self.size):
            variables = tuple((row, column)            for row in range(self.size))
            weights   = tuple(self._board[row][column] for row in range(self.size))

            constraints.append(
                self._make_constraint(
                    f"Coluna {column + 1}",
                    variables                   ,
                    weights                     ,
                    self._column_targets[column],
                )
            )

        return tuple(constraints)

    def _validate_problem(self) -> None:
        if not self._board:
            raise ValueError("The CSP board cannot be empty.")

        size = len(self._board)
        if size > self.MAX_SIZE:
            raise ValueError(f"The CSP supports boards of up to {self.MAX_SIZE}×{self.MAX_SIZE}.")

        if any(len(row) != size for row in self._board):
            raise ValueError("The CSP board must be square.")
        if len(self._row_targets) != size or len(self._column_targets) != size:
            raise ValueError("The CSP requires a target for each row and column.")

        if any(
            not isinstance(value, int )
            or  isinstance(value, bool)
            or  value <= 0
            for row   in self._board
            for value in row
        ):
            raise ValueError("The CSP cells must be positive integers.")
        if any(
            not isinstance(target, int )
            or  isinstance(target, bool)
            or  target < 0
            for target in (*self._row_targets, *self._column_targets)
        ):
            raise ValueError("The CSP targets must be non-negative integers.")

    def _validate_variable(self, variable: object) -> None:
        if (
            not isinstance(variable, tuple)
            or  len       (variable) != 2
            or  any(
                not isinstance(index, int )
                or  isinstance(index, bool)
                for index in variable
            )
        ):
            raise ValueError("Each variable must be a coordinate (row, column).")

        row, column = variable
        if not 0 <= row < self.size or not 0 <= column < self.size:
            raise ValueError("A coordinate in the assumptions is outside the board.")

    @staticmethod
    def _validate_limit(limit: int | None) -> None:
        if limit is not None and (
            not isinstance(limit, int )
            or  isinstance(limit, bool)
            or  limit <= 0
        ):
            raise ValueError("Limit must be None or a positive integer.")

    @staticmethod
    def _make_constraint(
        name      : str,
        variables : tuple[Coordinate, ...],
        weights   : tuple[int       , ...],
        target    : int,
    ) -> SumConstraint:
        allowed_masks = tuple(
            mask
            for mask in range(1 << len(variables))
            if  sum(
                weight
                for position, weight in enumerate(weights)
                if  mask & (1 << position)
            ) == target
        )

        return SumConstraint(name, variables, weights, target, allowed_masks)

    @staticmethod
    def _restore(
        domains : Domains                                ,
        trail   : list[tuple[Coordinate, frozenset[int]]],
        marker  : int,
    ) -> None:
        while len(trail) > marker:
            variable, old_domain = trail.pop()

            domains[variable] = set(old_domain)

    @staticmethod
    def _record(
        trace : list[CSPStep] | None,

        kind           : StepKind,
        depth          : int     ,
        cell           : Coordinate  | None,
        value          : DomainValue | None,
        removed_values : tuple[DomainValue, ...],
        reason         : str                    ,
    ) -> None:
        if trace is not None:
            trace.append(
                CSPStep(
                    kind          ,
                    depth         ,
                    cell          ,
                    value         ,
                    removed_values,
                    reason        ,
                )
            )
