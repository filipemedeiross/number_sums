from __future__ import annotations

from typing      import Any
from dataclasses import dataclass

from .controller import NumberSumsController

import pygame


class PygameUnavailableError(RuntimeError):
    """Indicates that the optional interface dependency is not installed"""


@dataclass(frozen=True, slots=True)
class BoardLayout:
    """Grid geometry, independent of Pygame"""

    size   : int = 8
    left   : int = 38
    top    : int = 130
    pixels : int = 480

    def __post_init__(self) -> None:
        if (
            not isinstance(self.size, int )
            or  isinstance(self.size, bool)
            or  self.size <= 0
        ):
            raise ValueError("Size must be a positive integer.")

        if not isinstance(self.pixels, int) or self.pixels < self.size:
            raise ValueError("Pixels must be an integer greater than or equal to size.")

    @property
    def cell_size(self) -> int:
        return self.pixels // self.size

    @property
    def width(self) -> int:
        return self.cell_size * self.size

    @property
    def right(self) -> int:
        return self.left + self.width

    @property
    def bottom(self) -> int:
        return self.top + self.width

    def cell_at(self, position: tuple[int, int]) -> tuple[int, int] | None:
        """Converts a point in the window to board coordinates"""

        x, y = position
        if not self.left <= x < self.right or \
           not self.top  <= y < self.bottom:
            return None

        return (y - self.top) // self.cell_size, (x - self.left) // self.cell_size

    def cell_box(self, row: int, column: int) -> tuple[int, int, int, int]:
        """Returns the ``x, y, width, height`` of a cell"""

        if not 0 <= row    < self.size or \
           not 0 <= column < self.size:
            raise IndexError("Cell outside the grid.")

        return (
            self.left + column * self.cell_size,
            self.top  + row    * self.cell_size,
            self.cell_size,
            self.cell_size,
        )


class NumberSumsPygameApp:
    """Minimal Pygame application, operated exclusively by the mouse."""

    WIDTH  = 640
    HEIGHT = 820
    FPS    = 60

    COLOR_TOP      = (245,  45, 155)
    COLOR_BOTTOM   = ( 70,  43, 145)
    COLOR_PANEL    = (120,  30, 120)
    COLOR_TILE     = (183,  30, 112)
    COLOR_TILE_ALT = (168,  25, 104)
    COLOR_LINE     = (218, 112, 214)
    COLOR_SELECT   = (200, 200, 255)
    COLOR_TEXT     = (255, 246, 252)
    COLOR_GREEN    = (101, 235, 155)
    COLOR_RED      = (255, 112, 132)
    COLOR_HINT     = (255, 211,  92)
    COLOR_MARKED   = ( 83, 244, 166)

    REMOVED_ALPHA = 100

    def __init__(
        self, controller: NumberSumsController | None = None
    ) -> None:
        self._require_pygame()

        pygame.display.init()
        pygame.font   .init()

        self.controller = controller or NumberSumsController()
        self.layout     = BoardLayout(size=self.controller.game.size)

        self.screen = pygame.display.set_mode(
            (
                self.WIDTH ,
                self.HEIGHT,
            )
        )
        pygame.display.set_caption("Number Sums")

        self.clock = pygame.time.Clock()

        self.font_title    = self._make_font(34, bold=True)
        self.font_subtitle = self._make_font(15)
        self.font_button   = self._make_font(17, bold=True)
        self.font_cell     = self._make_font(28, bold=True)
        self.font_target   = self._make_font(18, bold=True)
        self.font_status   = self._make_font(16)
        self.font_metric   = self._make_font(28, bold=True)
        self.font_win      = self._make_font(34, bold=True)

        self.background = self._make_gradient()
        self.buttons    = self._make_buttons ()

        self._started_at              = pygame.time.get_ticks()
        self._finished_at: int | None = None

    def run(self, *, max_frames: int | None = None) -> None:
        """
        Runs the main loop.

        ``max_frames`` is intended for headless smoke tests;
        during normal use, leave it as ``None``.
        """

        if max_frames is not None and (
            not isinstance(max_frames, int )
            or  isinstance(max_frames, bool)
            or  max_frames <= 0
        ):
            raise ValueError("Max_frames must be None or a positive integer.")

        running = True
        frames  = 0
        try:
            while running:
                for event in pygame.event.get():
                    if not self.handle_event(event):
                        running = False
                        break

                self.draw()

                frames += 1
                if max_frames is not None and frames >= max_frames:
                    break

                self.clock.tick(self.FPS)
        finally:
            pygame.display.quit()
            pygame.font   .quit()

    def handle_event(self, event: Any) -> bool:
        """Processes an event and returns whether the application should continue."""

        if event.type == pygame.QUIT:
            return False

        if self.controller.won:
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                for action in ("new", "reset"):
                    if self.buttons[action].collidepoint(event.pos):
                        self._perform_action(action)
                        break

            return True

        if event.type == pygame.MOUSEBUTTONDOWN and event.button in (1, 3):
            if event.button == 1:
                for action, rect in self.buttons.items():
                    if rect.collidepoint(event.pos):
                        self._perform_action(action)
                        return True

            coordinate = self.layout.cell_at(event.pos)

            if coordinate is not None:
                if event.button == 1:
                    self.controller.toggle_cell(*coordinate)
                else:
                    self.controller.toggle_mark(*coordinate)

            return True

        return True

    def draw(self) -> None:
        """Draws a complete frame."""

        self.screen.blit(self.background, (0, 0))

        self._draw_header ()
        self._draw_board  ()
        self._draw_toolbar()
        self._draw_footer ()

        if self.controller.won:
            self._draw_win_overlay()

        pygame.display.flip()

    def _elapsed_seconds(self) -> int:
        now = pygame.time.get_ticks()

        if self.controller.won:
            if self._finished_at is None:
                self._finished_at = now

            end = self._finished_at
        else:
            self._finished_at = None
            end               = now

        return max(0, end - self._started_at) // 1000

    def _restart_timer(self) -> None:
        self._started_at  = pygame.time.get_ticks()
        self._finished_at = None

    def _make_gradient(self) -> Any:
        surface = pygame.Surface((self.WIDTH, self.HEIGHT))

        for y in range(self.HEIGHT):
            ratio = y / max(1, self.HEIGHT - 1)

            color = tuple  (
                round(top + (bottom - top) * ratio)
                for top, bottom in zip(
                    self.COLOR_TOP, self.COLOR_BOTTOM
                )
            )

            pygame.draw.line(surface, color, (0, y), (self.WIDTH, y))

        return surface

    @staticmethod
    def _footer_cards() -> tuple[Any, Any]:
        return (
            pygame.Rect(100, 722, 210, 60),
            pygame.Rect(330, 722, 210, 60),
        )

    @staticmethod
    def _make_font(size: int, *, bold: bool = False) -> Any:
        """Uses the font bundled with Pygame, without relying on system fonts."""

        font = pygame.font.Font(None, size)
        font.set_bold(bold)

        return font

    @staticmethod
    def _sum_text(target: int, current: int) -> str:
        """Formats the target first and the reserved sum afterward."""

        return f"{target}/{current}"

    @staticmethod
    def _require_pygame() -> None:
        if pygame is None:
            raise PygameUnavailableError(
                "Pygame is not installed. Run: python -m pip install -e '.[ui]'"
            )

    @staticmethod
    def _make_buttons() -> dict[str, Any]:
        width = 140
        gap   = 14
        left  = 96

        return {
            action : pygame.Rect(
                left + index * (width + gap), 659, width, 42
            )
            for index, action in enumerate(
                ("new", "reset", "hint")
            )
        }


def main() -> int:
    """Entry point for the ``number-sums-game`` command"""

    try:
        NumberSumsPygameApp().run()
    except PygameUnavailableError as error:
        print(error)

        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
