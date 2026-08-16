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
