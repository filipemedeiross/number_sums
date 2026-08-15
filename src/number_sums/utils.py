from __future__ import annotations

from typing      import Literal
from dataclasses import dataclass


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
