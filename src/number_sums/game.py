from __future__ import annotations

from random      import Random
from dataclasses import dataclass
from typing      import Iterable, Literal, Sequence

from .solvers    import NumberSumsCSPSolver


Coordinate    = tuple  [int, int]
DecisionValue = Literal[0  , 1  ]


class NoSolutionError (RuntimeError):
    """Indicates that the targets of a board admit no solution."""


class InvalidMoveError(ValueError  ):
    """
    Indicates that an action cannot preserve a valid game state.

    The exception carries structured data so that controllers and interfaces
    can present their own message without having to interpret the text.
    """

    def __init__(
        self,
        action     : Literal["remove", "mark"],
        coordinate : Coordinate,
        reason     : str       ,
    ) -> None:
        self.action           = action
        self.coordinate       = coordinate
        self.row, self.column = coordinate
        self.reason           = reason

        verb = "remove" if action == "remove" else "mark"

        super().__init__(
            f"Cannot {verb} R{self.row + 1} C{self.column + 1}: {reason}."
        )


@dataclass(frozen=True, slots=True)
class Cell:
    """A board cell using zero-based coordinates"""

    row    : int
    column : int
    value  : int


@dataclass(frozen=True, slots=True)
class Move:
    """A change made by the player"""

    action : Literal["remove", "restore", "mark", "unmark"]
    cell   : Cell

    removed_position : int | None = None  # position of the decision in the chronological state


@dataclass(frozen=True, slots=True)
class Hint:
    """Next move suggested by a solver."""

    row    : int
    column : int
    value  : int

    action : Literal["remove", "mark"    ]
    kind   : Literal["forced", "decision"]
    reason : str

    @property
    def coordinate(self) -> Coordinate:
        return self.row, self.column


class NumberSumsGame:
    """
    Represents a Number Sums board and the current game state.

    The board and its targets are immutable and must admit at least one solution.
    Removals and confirmations of permanence are maintained in a separate state,
    in chronological order, and are only accepted when they preserve a compatible
    solution. They can be queried, reverted, and used as assignments by CSP.

    Args:
        board          : Square matrix containing positive integers.
        row_targets    : Expected sum of the remaining numbers in each row.
        column_targets : Expected sum of the remaining numbers in each column.
    """

    DEFAULT_SIZE = 8
    MAX_SIZE     = 8

    def __init__(
        self,
        board          : Sequence[Sequence[int]],
        row_targets    : Sequence[int],
        column_targets : Sequence[int],
    ) -> None:
        values = tuple(tuple(row) for row in board)

        if not values:
            raise ValueError("The board cannot be empty.")

        size = len(values)

        if size > self.MAX_SIZE:
            raise ValueError(f"The board can have at most {self.MAX_SIZE} rows and columns.")
        if any(len(row) != size for row in values):
            raise ValueError("The board must be square.")
        if any(not self._is_int(value) or value <= 0 for row in values for value in row):
            raise ValueError("All cells must contain positive integers.")

        rows    = tuple(row_targets   )
        columns = tuple(column_targets)

        if len(rows) != size or len(columns) != size:
            raise ValueError("There must be exactly one target per row and column.")
        if any(not self._is_int(target) or target < 0 for target in (*rows, *columns)):
            raise ValueError("All targets must be non-negative integers.")

        row_totals    = tuple(sum(row) for row in values)
        column_totals = tuple(
            sum(
                values[row][column]
                for row in range(size)
            )
            for column in range(size)
        )

        if any(target > total for target, total in zip(rows   , row_totals   )):
            raise ValueError("A row target is greater than the sum of the numbers in that row."      )
        if any(target > total for target, total in zip(columns, column_totals)):
            raise ValueError("A column target is greater than the sum of the numbers in that column.")

        if not NumberSumsCSPSolver(values, rows, columns).is_consistent():
            raise NoSolutionError("The specified targets do not admit any solution.")

        self._board          = values
        self._row_targets    = rows
        self._column_targets = columns

        self._known_solvable = True

        self._decisions : dict[Coordinate, DecisionValue] = {}
        self._history   : list[Move                     ] = []
