from __future__ import annotations

import os
import pygame
import unittest

from unittest.mock import Mock, patch
from types         import SimpleNamespace

from number_sums            import NumberSumsController, NumberSumsGame
from number_sums.pygame_app import BoardLayout         , NumberSumsPygameApp


os.environ.setdefault("SDL_VIDEODRIVER", "dummy")


class BoardLayoutTests(unittest.TestCase):
    def test_cell_at_maps_edges_and_rejects_outside_points(self) -> None:
        layout = BoardLayout()

        self.assertEqual(layout.cell_at((layout.left     , layout.top       )), (0, 0))
        self.assertEqual(layout.cell_at((layout.right - 1, layout.bottom - 1)), (7, 7))

        self.assertIsNone(layout.cell_at((layout.left  - 1, layout.top       )))
        self.assertIsNone(layout.cell_at((layout.right    , layout.bottom - 1)))
        self.assertIsNone(layout.cell_at((layout.right - 1, layout.bottom    )))

    def test_cell_box_uses_the_same_geometry(self) -> None:
        layout = BoardLayout    (size=8)
        box    = layout.cell_box(3, 5  )

        self.assertEqual(layout.cell_at((box[0], box[1])), (3, 5))

        with self.assertRaises(IndexError):
            layout.cell_box(8, 0)
        with self.assertRaises(ValueError):
            BoardLayout(size=0)


class PygameAppTests(unittest.TestCase):
    def tearDown(self) -> None:
        pygame.display.quit()
        pygame.font   .quit()

    def make_controller(self) -> NumberSumsController:
        return NumberSumsController(
            NumberSumsGame(
                board=(
                    (1, 2),
                    (3, 4),
                ),

                row_targets   =(1, 4),
                column_targets=(1, 4),
            )
        )

    def make_event_app(
        self,
        *,
        won: bool = False,
    ) -> tuple[NumberSumsPygameApp, Mock]:
        controller = Mock(
            spec_set=[
                "game",
                "won" ,
                "toggle_cell",
                "toggle_mark",
                "new_game"    ,
                "reset"       ,
                "request_hint",
            ]
        )

        controller.game = SimpleNamespace(size=2)
        controller.won  = won

        app = NumberSumsPygameApp.__new__(NumberSumsPygameApp)

        app.controller = controller
        app.layout     = BoardLayout(size=2)
        app.buttons    = NumberSumsPygameApp._make_buttons()

        return app, controller

    def test_app_draws_one_headless_frame(self) -> None:
        app = NumberSumsPygameApp(self.make_controller())

        pygame.event.clear()

        app.run(max_frames=1)

    def test_quit_stops_app_and_keyboard_is_ignored(self) -> None:
        app, controller = self.make_event_app()

        self.assertFalse(app.handle_event(SimpleNamespace(type=pygame.QUIT)))
        self.assertTrue (
            app.handle_event(
                SimpleNamespace(type=pygame.KEYDOWN, key=pygame.K_ESCAPE)
            )
        )

        controller.toggle_cell .assert_not_called()
        controller.toggle_mark .assert_not_called()
        controller.new_game    .assert_not_called()
        controller.reset       .assert_not_called()
        controller.request_hint.assert_not_called()

    def test_cell_clicks_are_routed_by_mouse_button(self) -> None:
        app, controller = self.make_event_app()

        first_box  = app.layout.cell_box(1, 0)
        second_box = app.layout.cell_box(0, 1)

        left_click = SimpleNamespace(
            type  =pygame.MOUSEBUTTONDOWN,
            button=1,
            pos   =(first_box[0] + 1, first_box[1] + 1),
        )
        right_click = SimpleNamespace(
            type  =pygame.MOUSEBUTTONDOWN,
            button=3,
            pos   =(second_box[0] + 1, second_box[1] + 1),
        )
        outside_click = SimpleNamespace(
            type  =pygame.MOUSEBUTTONDOWN,
            button=1,
            pos   =(0, 0),
        )

        self.assertTrue(app.handle_event(left_click   ))
        self.assertTrue(app.handle_event(right_click  ))
        self.assertTrue(app.handle_event(outside_click))

        controller.toggle_cell.assert_called_once_with(1, 0)
        controller.toggle_mark.assert_called_once_with(0, 1)

    def test_toolbar_clicks_call_the_corresponding_actions(self) -> None:
        app, controller = self.make_event_app()

        with patch.object(app, "_restart_timer") as restart_timer:
            for action in ("new", "reset", "hint"):
                with self.subTest(action=action):
                    event = SimpleNamespace(
                        type  =pygame.MOUSEBUTTONDOWN,
                        button=1,
                        pos   =app.buttons[action].center,
                    )

                    self.assertTrue(app.handle_event(event))

        controller.new_game    .assert_called_once_with()
        controller.reset       .assert_called_once_with()
        controller.request_hint.assert_called_once_with()

        self.assertEqual(restart_timer.call_count, 2)

    def test_won_game_only_allows_new_and_reset(self) -> None:
        app, controller = self.make_event_app(won=True)

        cell_box      = app.layout.cell_box(0, 0)
        cell_position = (cell_box[0] + 1, cell_box[1] + 1)

        ignored_events = (
            SimpleNamespace(
                type  =pygame.MOUSEBUTTONDOWN,
                button=1,
                pos   =cell_position,
            ),
            SimpleNamespace(
                type  =pygame.MOUSEBUTTONDOWN,
                button=3,
                pos   =cell_position,
            ),
            SimpleNamespace(
                type  =pygame.MOUSEBUTTONDOWN,
                button=1,
                pos   =app.buttons["hint"].center,
            ),
        )

        with patch.object(app, "_restart_timer") as restart_timer:
            for event in ignored_events:
                self.assertTrue(app.handle_event(event))

            for action in ("new", "reset"):
                event = SimpleNamespace(
                    type  =pygame.MOUSEBUTTONDOWN,
                    button=1,
                    pos   =app.buttons[action].center,
                )

                self.assertTrue(app.handle_event(event))

        controller.toggle_cell .assert_not_called()
        controller.toggle_mark .assert_not_called()
        controller.request_hint.assert_not_called()
        controller.new_game    .assert_called_once_with()
        controller.reset       .assert_called_once_with()

        self.assertEqual(restart_timer.call_count, 2)


if __name__ == "__main__":
    unittest.main()
