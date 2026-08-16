from __future__ import annotations

import unittest

from number_sums import NoSolutionError, NumberSumsController, NumberSumsGame


def make_game() -> NumberSumsGame:
    return NumberSumsGame(
        board=(
            (1, 2),
            (3, 4),
        ),

        row_targets   =(1, 4),
        column_targets=(1, 4),
    )


class NumberSumsControllerTests(unittest.TestCase):
    def test_toggle_clears_hint_tracks_selection_and_wins(self) -> None:
        controller = NumberSumsController(make_game())

        controller.request_hint()

        self.assertIsNotNone(controller.hint)

        self.assertTrue  (controller.toggle_cell(0, 1))
        self.assertIsNone(controller.hint)

        self.assertEqual(controller.selected  , (0, 1))
        self.assertEqual(controller.move_count, 1     )

        controller.toggle_cell(1, 0)

        self.assertTrue (controller.won)
        self.assertFalse(controller.toggle_cell(0, 0))

    def test_hint_is_returned_then_applied_one_step_at_a_time(self) -> None:
        controller = NumberSumsController(make_game())

        first = controller.request_hint()

        self.assertIsNotNone(first)
        self.assertEqual    (controller.game.removed_cells, ())

        self.assertTrue  (controller.apply_hint())
        self.assertIsNone(controller.hint)
        self.assertFalse (controller.won )

        self.assertEqual(len(controller.game.decisions), 1)

        while not controller.won:
            before = len(controller.game.decisions)

            self.assertTrue (controller.apply_hint()      )
            self.assertEqual(len(controller.game.decisions), before + 1)

        self.assertTrue (controller.won)
        self.assertEqual(controller.csp_step_count, controller.move_count)

    def test_invalid_move_is_counted_without_becoming_a_hint(self) -> None:
        controller = NumberSumsController(make_game())

        self.assertFalse(controller.toggle_cell(0, 0))

        self.assertEqual(controller.forbidden_move_count, 1 )
        self.assertEqual(controller.game.decisions      , ())

        hint = controller.request_hint()

        self.assertIsNotNone(hint)
        self.assertIn       (hint.action, ("remove", "mark"))

    def test_undo_reset_and_new_game(self) -> None:
        created: list[NumberSumsGame] = []

        def factory() -> NumberSumsGame:
            game = make_game()

            created.append(game)

            return game

        controller = NumberSumsController(make_game(), game_factory=factory)

        controller.toggle_cell(0, 1)

        self.assertTrue (controller.undo()               )
        self.assertFalse(controller.game.is_removed(0, 1))
        self.assertEqual(controller.move_count, 0        )

        controller.toggle_cell(0, 1)
        controller.reset      ()

        self.assertEqual(controller.game.removed_cells, ())
        self.assertEqual(controller.move_count        , 0 )

        old_game = controller.game
        new_game = controller.new_game()

        self.assertIsNot(new_game, old_game   )
        self.assertIs   (new_game, created[-1])

    def test_unsatisfiable_game_is_rejected_before_reaching_controller(self) -> None:
        with self.assertRaises(NoSolutionError):
            NumberSumsGame(
                board=(
                    (1, 1),
                    (1, 1),
                ),

                row_targets   =(1, 1),
                column_targets=(1, 2),
            )

    def test_every_hint_is_a_forward_decision(self) -> None:
        controller = NumberSumsController(make_game())

        while not controller.won:
            hint = controller.request_hint()

            self.assertIsNotNone(hint)

            self.assertIn  (hint.action, ("remove", "mark"    ))
            self.assertIn  (hint.kind  , ("forced", "decision"))
            self.assertTrue(controller.apply_hint())


if __name__ == "__main__":
    unittest.main()
