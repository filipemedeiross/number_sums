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

    def remove_cell(self, row: int, column: int) -> bool:
        """
        Removes a cell and saves its position and value.

        Returns ``True`` when the state changed or ``False`` if the cell was
        already removed. An incompatible removal raises
        :class:`InvalidMoveError` without changing the game.
        """

        self._validate_coordinate(row, column)

        coordinate = (row, column)
        decision   = self._decisions.get(coordinate)

        if decision == 0:
            return False
        if decision == 1:
            raise InvalidMoveError(
                "remove"  ,
                coordinate,
                "The cell is marked; unmark it before removing it",
            )

        self._ensure_consistent_decision(coordinate, 0)

        value = self._board[row][column]

        self._decisions[coordinate] = 0
        self._history.append(
            Move(
                "remove",
                Cell(row, column, value)
            )
        )

        return True

    def restore_cell(self, row: int, column: int) -> bool:
        """Restores a previously removed cell"""

        self._validate_coordinate(row, column)

        coordinate = (row, column)
        if self._decisions.get(coordinate) != 0:
            return False

        removed_position = tuple(self._decisions).index(coordinate)
        value            = self._board[row][column]

        self._decisions.pop   (coordinate)
        self._history  .append(
            Move(
                "restore"               ,
                Cell(row, column, value),
                removed_position        ,
            )
        )

        return True

    def mark_cell(self, row: int, column: int) -> bool:
        """
        Marks a visible cell as confirmed to remain.

        An incompatible mark raises :class:`InvalidMoveError`
        without changing the game.
        """

        self._validate_coordinate(row, column)

        coordinate = (row, column)
        decision   = self._decisions.get(coordinate)

        if decision == 1:
            return False
        if decision == 0:
            raise InvalidMoveError(
                "mark"    ,
                coordinate,
                "The cell is removed; restore it before marking it",
            )

        self._ensure_consistent_decision(coordinate, 1)

        value = self._board[row][column]

        self._decisions[coordinate] = 1
        self._history.append(
            Move(
                "mark",
                Cell(row, column, value)
            )
        )

        return True

    def unmark_cell(self, row: int, column: int) -> bool:
        """Removes a confirmation that a cell should remain"""

        self._validate_coordinate(row, column)

        coordinate = (row, column)
        if self._decisions.get(coordinate) != 1:
            return False

        position = tuple(self._decisions).index(coordinate)
        value    = self._board[row][column]

        self._decisions.pop   (coordinate)
        self._history  .append(
            Move(
                "unmark"                ,
                Cell(row, column, value),
                position                ,
            )
        )

        return True

    def toggle_mark(self, row: int, column: int) -> bool:
        """Toggles the mark of a cell; returns the final state of the mark"""

        if self.is_marked(row, column):
            self.unmark_cell(row, column)

            return False

        self.mark_cell(row, column)

        return True

    def toggle_cell(self, row: int, column: int) -> bool:
        """
        Toggles a cell between removed and visible.

        Returns ``True`` when the cell ends up removed
        and ``False`` when it ends up visible.
        """

        if self.is_removed(row, column):
            self.restore_cell(row, column)

            return False

        if self.is_marked(row, column):
            raise InvalidMoveError(
                "remove"     ,
                (row, column),
                "The cell is marked; unmark it before removing it",
            )

        self.remove_cell(row, column)

        return True

    def undo(self) -> bool:
        """Undoes the last removal, restoration, mark, or unmark"""

        if not self._history:
            return False

        move       = self._history.pop()
        coordinate = (
            move.cell.row   ,
            move.cell.column,
        )

        if move.action in ("remove", "mark"):
            self._decisions.pop(coordinate)
        else:
            items    = list(self._decisions.items())
            position = move.removed_position

            if position is None:
                position = len(items)

            decision : DecisionValue = 0 if move.action == "restore" else 1

            items.insert(
                position,
                (
                    coordinate,
                    decision  ,
                )
            )

            self._decisions.clear ()
            self._decisions.update(items)

        return True

    def reset(self) -> None:
        """Restores the entire board and clears the history"""

        self._decisions.clear()
        self._history  .clear()

    def current_row_sums(self) -> tuple[int, ...]:
        """Calculates the current sums of the rows"""

        return tuple(
            sum(
                self._board[row][column]
                for column in range(self.size)
                if  self._decisions.get((row, column)) != 0
            )
            for row in range(self.size)
        )

    def current_column_sums(self) -> tuple[int, ...]:
        """Calculates the current sums of the columns"""

        return tuple(
            sum(
                self._board[row][column]
                for row in range(self.size)
                if  self._decisions.get((row, column)) != 0
            )
            for column in range(self.size)
        )

    def marked_row_sums(self) -> tuple[int, ...]:
        """
        Calculates the sums of only the marked cells in each row.

        Different from :meth:`current_row_sums`, this accumulated starts at
        zero and only increases when the player marks a cell as KEEP.
        """

        return tuple(
            sum(
                self._board[row][column]
                for column in range(self.size)
                if  self._decisions.get((row, column)) == 1
            )
            for row in range(self.size)
        )

    def marked_column_sums(self) -> tuple[int, ...]:
        """Calculates the sums of only the marked cells in each column"""

        return tuple(
            sum(
                self._board[row][column]
                for row in range(self.size)
                if  self._decisions.get((row, column)) == 1
            )
            for column in range(self.size)
        )

    def reserved_row_sums(self) -> tuple[int, ...]:
        """Semantic alias of :meth:`marked_row_sums` for the interface"""

        return self.marked_row_sums()

    def reserved_column_sums(self) -> tuple[int, ...]:
        """Semantic alias of :meth:`marked_column_sums` for the interface"""

        return self.marked_column_sums()

    def is_won(self) -> bool:
        """
        Returns whether all row and column targets have been met.

        This is the victory formula encapsulated by the model: the sum of the unremoved
        cells must be equal to the corresponding target in each row and in each column.
        """

        return (
            self.current_row_sums   () == self._row_targets    and
            self.current_column_sums() == self._column_targets
        )

    def find_solutions(self, limit: int | None = None) -> list[frozenset[Coordinate]]:
        """
        Finds solutions via CSP and returns the cells to remove.

        The solver uses generalized arc consistency over the sums,
        followed by backtracking with the MRV and LCV heuristics.
        The current state of the game is not altered.
        """

        solutions = NumberSumsCSPSolver.from_game(self).find_solutions(limit)

        if solutions:
            self._known_solvable = True
        else:
            self._known_solvable = False

        return solutions

    def next_hint(self) -> Hint | None:
        """Suggests the next move using the current state in the CSP solver"""

        return NumberSumsCSPSolver.from_game(self).next_hint()

    def solve(self, *, apply: bool = False) -> frozenset[Coordinate]:
        """Finds a solution, optionally applying it to the current board"""

        solutions = self.find_solutions(limit=1)

        if not solutions:
            raise NoSolutionError("The board has no solution.")

        solution = solutions[0]
        if apply:
            self.apply_solution(solution)

        return solution

    def apply_solution(
        self,
        solution : Iterable[Coordinate] | None = None,
    ) -> frozenset[Coordinate]:
        """
        Restores the board and removes all cells from a solution.

        When ``solution`` is not provided, a solution is calculated by the object itself.
        An external solution is only applied if its coordinates really satisfy all the targets.
        """

        if solution is None:
            selected = self.solve()
        else:
            try:
                selected = frozenset(solution)
            except TypeError as error:
                raise ValueError("Solution must be an iterable of coordinates.") from error

            for coordinate in selected:
                if not isinstance(coordinate, tuple) or len(coordinate) != 2:
                    raise ValueError("Each item in the solution must be a tuple (row, column).")

                self._validate_coordinate(*coordinate)

            if not self._coordinates_win(selected):
                raise ValueError("The provided coordinates do not form a valid solution.")

        self.reset()
        for row, column in sorted(selected):
            self.remove_cell(row, column)

        self._known_solvable = True

        return selected

    def render(self) -> str:
        """Formats the board, its targets and current sums for the terminal"""

        row_sums    = self.current_row_sums   ()
        column_sums = self.current_column_sums()

        cell_width = max(
            2,

              len(str(self.size)),
            *(len(str(value    )) for row in self._board for value in row),

            *(
                len(str(self._display_value(row, column)))
                for row    in range(self.size)
                for column in range(self.size)
            ),

            *(len(str(value)) for value in self._column_targets),
            *(len(str(value)) for value in column_sums         ),
        )
        sum_width = max(
            4,

            *(len(str(value)) for value in self._row_targets),
            *(len(str(value)) for value in row_sums         ),
        )
        label_width = max(2, len(str(self.size)))

        indent = " " * (label_width + 3)
        header = indent + " ".join(
            f"{column + 1:>{cell_width}}"
            for column in range(self.size)
        )

        separator = " " * (label_width + 1) + "+" + "-" * ((cell_width + 1) * self.size + 1) + "+"

        lines = [
            header + "   meta (atual)",
            separator                 ,
        ]
        for row in range(self.size):
            cells = " ".join(
                f"{self._display_value(row, column):>{cell_width}}"
                for column in range(self.size)
            )

            lines.append(
                f"{row + 1:>{label_width}} | {cells} | "
                f"{self._row_targets[row]:>{sum_width}} ({row_sums[row]:>{sum_width}})"
            )

        lines.append(separator)

        targets = " ".join(f"{target:>{cell_width}}" for target in self._column_targets)
        current = " ".join(f"{total:>{cell_width }}" for total  in column_sums         )

        lines.append(f"{indent}{targets}   metas" )
        lines.append(f"{indent}{current}   atuais")

        return "\n".join(lines)

    def __str__(self) -> str:
        return self.render()

    def _display_value(self, row: int, column: int) -> int | str:
        coordinate = (row, column)

        if self._decisions.get(coordinate) == 0:
            return "·"
        if self._decisions.get(coordinate) == 1:
            return f"{self._board[row][column]}*"

        return self._board[row][column]

    def _coordinates_win(self, removed: frozenset[Coordinate]) -> bool:
        row_sums = tuple(
            sum(
                self._board[row][column]
                for column in range(self.size)
                if (row, column) not in removed
            )
            for row in range(self.size)
        )
        column_sums = tuple(
            sum(
                self._board[row][column]
                for row in range(self.size)
                if (row, column) not in removed
            )
            for column in range(self.size)
        )

        return row_sums == self._row_targets and column_sums == self._column_targets

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
