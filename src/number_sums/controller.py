from __future__ import annotations

from collections.abc import Callable

from .game    import NumberSumsGame
from .solvers import NumberSumsCSPSolver
from .utils   import Hint, InvalidMoveError, NoSolutionError


GameFactory   = Callable[[              ], NumberSumsGame     ]
SolverFactory = Callable[[NumberSumsGame], NumberSumsCSPSolver]


class NumberSumsController:
    """
    Coordinates gameplay, selection, and hints without depending on Pygame.

    This separation makes it possible to test all game interactions in headless
    environments. The visual layer only translates events into calls to these methods.
    """

    def __init__(
        self,
        game : NumberSumsGame | None = None,
        *,
        game_factory   : GameFactory   | None = None,
        solver_factory : SolverFactory | None = None,
    ) -> None:
        self._game_factory   = game_factory   or NumberSumsGame     .random
        self._solver_factory = solver_factory or NumberSumsCSPSolver.from_game

        self.game = game or self._create_game()

        self.selected               = (0, 0)
        self.hint     : Hint | None = None

        self.move_count           = 0
        self.forbidden_move_count = 0
        self.csp_step_count       = 0

    def toggle_cell(self, row: int, column: int) -> bool:
        """Toggles a cell and returns whether the game state changed"""

        self._validate_coordinate(row, column)
        self.selected          = (row, column)

        if self.game.is_won():
            return False

        if self.game .is_removed  (row, column):
            self.game.restore_cell(row, column)
        else:
            try:
                self.game.remove_cell(row, column)
            except InvalidMoveError:
                return self._forbid()

        self.move_count += 1
        self.hint        = None

        return True

    def toggle_mark(self, row: int, column: int) -> bool:
        """Marks/unmarks KEEP, blocking incompatible commitments"""

        self._validate_coordinate(row, column)
        self.selected          = (row, column)

        if self.game.is_won():
            return False

        if self.game .is_marked  (row, column):
            self.game.unmark_cell(row, column)
        else:
            try:
                self.game.mark_cell(row, column)
            except InvalidMoveError:
                return self._forbid()

        self.move_count += 1
        self.hint        = None

        return True

    def request_hint(self) -> Hint | None:
        """Calculates and returns a single next move without applying it"""

        if self.game.is_won():
            self.hint = None

            return None

        try:
            self.hint = self._solver_factory(self.game).next_hint()
        except NoSolutionError:
            self.hint = None

            return None

        if self.hint is None:
            return None

        self.selected = self.hint.coordinate

        return self.hint

    def apply_hint(self) -> bool:
        """Applies exactly one hint, useful for demonstrating the solver step by step"""

        hint = self.request_hint()
        if hint is None:
            return False

        operations = {
            "remove" : self.game.remove_cell,
            "mark"   : self.game.mark_cell  ,
        }

        changed = operations[hint.action](hint.row, hint.column)

        self.hint = None
        if changed:
            self.move_count     += 1
            self.csp_step_count += 1

        return changed

    def undo(self) -> bool:
        """Undoes the last change made to the board"""

        changed   = self.game.undo()
        self.hint = None

        if changed:
            self.move_count = max(0, self.move_count - 1)

        return changed

    def reset(self) -> None:
        """Resets the current board"""

        self.game.reset()

        self.selected = (0, 0)
        self.hint     = None

        self.move_count           = 0
        self.forbidden_move_count = 0
        self.csp_step_count       = 0

    def new_game(self) -> NumberSumsGame:
        """Replaces the current game with a new board produced by the factory"""

        self.game = self._create_game()

        self.selected = (0, 0)
        self.hint     = None

        self.move_count           = 0
        self.forbidden_move_count = 0
        self.csp_step_count       = 0

        return self.game

    @property
    def won(self) -> bool:
        return self.game.is_won()

    @property
    def prohibited_move_count(self) -> int:
        return self.forbidden_move_count

    def _create_game(self) -> NumberSumsGame:
        game = self._game_factory()

        if not isinstance(game, NumberSumsGame):
            raise TypeError("Game_factory must return a NumberSumsGame.")

        return game

    def _forbid(self) -> bool:
        """Records an invalid attempt without changing the game state"""

        self.forbidden_move_count += 1

        return False

    def _validate_coordinate(self, row: int, column: int) -> None:
        if not isinstance(row   , int) or isinstance(row   , bool):
            raise TypeError("Row and column must be integers.")
        if not isinstance(column, int) or isinstance(column, bool):
            raise TypeError("Row and column must be integers.")

        if not 0 <= row < self.game.size or not 0 <= column < self.game.size:
            raise IndexError("The selected cell is outside the grid.")
