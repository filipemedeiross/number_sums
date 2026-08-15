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

    @classmethod
    def random(
        cls,
        *  ,

        size : int                                          = DEFAULT_SIZE,
        seed : int | float | str | bytes | bytearray | None = None        ,
        min_value : int = 1,
        max_value : int = 9,

        keep_probability : float = 0.5  ,
        unique_solution  : bool  = True ,
        max_attempts     : int   = 1_000,
    ) -> NumberSumsGame:
        """
        Creates a random board that has at least one solution.

        The targets are calculated from a random mask of kept cells.
        By default, the generator also uses the solver to reject boards
        with more than one solution.

        ``seed`` allows reproducing exactly one generation. ``size`` is 8
        by default, as in the format requested for the game.
        """

        if not cls._is_int(size) or not 2 <= size <= cls.MAX_SIZE:
            raise ValueError(f"Size must be an integer between 2 and {cls.MAX_SIZE}.")

        if not cls._is_int(min_value) or not cls._is_int(max_value):
            raise ValueError("Min_value and max_value must be integers.")
        if min_value <= 0 or max_value < min_value:
            raise ValueError("Use 0 < min_value <= max_value.")

        if isinstance(keep_probability, bool) or not isinstance(keep_probability, (int, float)):
            raise ValueError("Keep_probability must be a number between 0 and 1.")
        if not 0 < keep_probability < 1:
            raise ValueError("Keep_probability must be strictly between 0 and 1.")

        if not isinstance(unique_solution, bool):
            raise ValueError("Unique_solution must be a boolean.")
        if not cls._is_int(max_attempts) or max_attempts <= 0:
            raise ValueError("Max_attempts must be a positive integer.")

        random = Random(seed)

        for _ in range(max_attempts):
            board = tuple(
                tuple(
                    random.randint(min_value, max_value)
                    for _ in range(size)
                )
                for _ in range(size)
            )
            kept  = cls._random_keep_mask(
                random, size, keep_probability
            )

            row_targets = tuple(
                sum(
                    board[row][column]
                    for column in range(size)
                    if  kept[row][column]
                )
                for row in range(size)
            )
            column_targets = tuple(
                sum(
                    board[row][column]
                    for row in range(size)
                    if  kept[row][column]
                )
                for column in range(size)
            )

            game = cls(board, row_targets, column_targets)

            if not unique_solution or len(game.find_solutions(limit=2)) == 1:
                game._known_solvable = True

                return game

        raise RuntimeError(
            f"Could not generate a valid board in {max_attempts} attempts. "
             "Increase max_attempts or disable unique_solution."
        )

    @staticmethod
    def _random_keep_mask(
        random      : Random,
        size        : int   ,
        probability : float ,
    ) -> tuple[tuple[bool, ...], ...]:
        """Generates a non-trivial mask for every row and column"""

        for _ in range(10_000):
            mask = tuple(
                tuple(
                    random.random() < probability
                    for _ in range(size)
                )
                for _ in range(size)
            )

            rows_are_mixed    = all(any(row) and not all(row) for row in mask)
            columns_are_mixed = all(
                any(mask[row][column] for row in range(size)) and not
                all(mask[row][column] for row in range(size))
                for column in range(size)
            )

            if rows_are_mixed and columns_are_mixed:
                return mask

        raise RuntimeError("Could not generate a non-trivial mask.")

    @staticmethod
    def _is_int(value: object) -> bool:
        return isinstance(value, int) and not isinstance(value, bool)

    @property
    def size(self) -> int:
        """Number of rows and columns in the board"""

        return len(self._board)

    @property
    def board(self) -> tuple[tuple[int, ...], ...]:
        """Original board, without hiding removed cells."""

        return self._board

    @property
    def row_targets(self) -> tuple[int, ...]:
        return self._row_targets

    @property
    def column_targets(self) -> tuple[int, ...]:
        return self._column_targets

    @property
    def known_solvable(self) -> bool:
        """Indicates that the board has passed the solvability check"""

        return self._known_solvable

    @property
    def visible_board(self) -> tuple[tuple[int | None, ...], ...]:
        """Visible board; removed cells are represented by ``None``"""

        return tuple(
            tuple(
                None
                if   self._decisions.get((row, column)) == 0
                else self._board[row][column]
                for column in range(self.size)
            )
            for row in range(self.size)
        )

    @property
    def removed_cells(self) -> tuple[Cell, ...]:
        """Removed cells, in the order they were removed"""

        return tuple(
            Cell(
                row   ,
                column,
                self._board[row][column],
            )
            for (row, column), decision in self._decisions.items()
            if  decision == 0
        )

    @property
    def marked_cells(self) -> tuple[Cell, ...]:
        """Marked cells, in the order they were marked"""

        return tuple(
            Cell(
                row   ,
                column,
                self._board[row][column],
            )
            for (row, column), decision in self._decisions.items()
            if  decision == 1
        )

    @property
    def decisions(self) -> tuple[tuple[Coordinate, DecisionValue], ...]:
        """Active decisions in the order they were made by the player"""

        return tuple(self._decisions.items())

    @property
    def history(self) -> tuple[Move, ...]:
        """Immutable history of changes made since the last reset"""

        return tuple(self._history)

    def is_removed(self, row: int, column: int) -> bool:
        """Indicates if the cell is removed"""

        self._validate_coordinate(row, column)

        return self._decisions.get((row, column)) == 0

    def is_marked(self, row: int, column: int) -> bool:
        """Indicates if the cell is marked"""

        self._validate_coordinate(row, column)

        return self._decisions.get((row, column)) == 1

    def _ensure_consistent_decision(
        self,
        coordinate : Coordinate   ,
        decision   : DecisionValue,
    ) -> None:
        """Validates a new assignment without changing the state or history"""

        assumptions = dict(self._decisions)

        assumptions[coordinate] = decision
        if NumberSumsCSPSolver.from_game(self).is_consistent(assumptions):
            return

        action : Literal["remove", "mark"] = "remove" if decision == 0 else "mark"
        reason                             = (
            "The removal eliminates all compatible solutions"
            if   decision == 0
            else "The marking eliminates all compatible solutions"
        )

        raise InvalidMoveError(action, coordinate, reason)

    def _validate_coordinate(self, row: object, column: object) -> None:
        if not self._is_int(row) or not self._is_int(column):
            raise TypeError("Row and column must be integers.")

        if not 0 <= row < self.size or not 0 <= column < self.size:
            raise IndexError(f"Coordinates must be between 0 and {self.size - 1}.")
