from __future__ import annotations

import unittest

from number_sums import (
    Cell            ,
    InvalidMoveError,
    NoSolutionError ,

    NumberSumsGame     ,
    NumberSumsCSPSolver,
)


class NumberSumsGameTests(unittest.TestCase):
    def make_small_game(self) -> NumberSumsGame:
        return NumberSumsGame(
            board=(
                (1, 2),
                (3, 4),
            ),

            row_targets   =(1, 4),
            column_targets=(1, 4),
        )

    def test_random_creates_reproducible_8_by_8_board(self) -> None:
        first  = NumberSumsGame.random(seed=2025)
        second = NumberSumsGame.random(seed=2025)

        self.assertEqual(first.size, 8)
        self.assertTrue (
            all(
                len(row) == 8
                for row in first.board
            )
        )

        self.assertEqual(first.board         , second.board         )
        self.assertEqual(first.row_targets   , second.row_targets   )
        self.assertEqual(first.column_targets, second.column_targets)

        self.assertEqual(len(first.find_solutions(limit=2)), 1)

    def test_board_size_is_limited_to_game_scope(self) -> None:
        with self.assertRaises(ValueError):
            NumberSumsGame.random(size=9)

        with self.assertRaises(ValueError):
            NumberSumsGame(
                board=tuple(
                    tuple(1 for _ in range(9))
                    for _ in range(9)
                ),

                row_targets   =(1,) * 9,
                column_targets=(1,) * 9,
            )

    def test_remove_restore_toggle_and_saved_cells(self) -> None:
        game = self.make_small_game()

        self.assertTrue  (game.remove_cell  (0, 1))
        self.assertFalse (game.remove_cell  (0, 1))
        self.assertIsNone(game.visible_board[0][1])
        self.assertEqual (game.removed_cells, (Cell(0, 1, 2),))

        self.assertFalse(game.toggle_cell(0, 1))
        self.assertEqual(game.removed_cells, ())

        self.assertTrue (game.toggle_cell (0, 1))
        self.assertTrue (game.restore_cell(0, 1))
        self.assertFalse(game.restore_cell(0, 1))

    def test_undo_and_reset(self) -> None:
        game = self.make_small_game()
        game.remove_cell (0, 1)
        game.restore_cell(0, 1)

        self.assertTrue (game.undo())
        self.assertTrue (game.is_removed(0, 1))
        self.assertTrue (game.undo())
        self.assertFalse(game.is_removed(0, 1))
        self.assertFalse(game.undo())

        game.remove_cell(1, 0)
        game.reset      ()

        self.assertEqual(game.removed_cells, ())
        self.assertEqual(game.history      , ())

    def test_reserved_sums_start_at_zero_and_only_include_marked_cells(self) -> None:
        game = self.make_small_game()

        self.assertEqual(game.reserved_row_sums   (), (0, 0))
        self.assertEqual(game.reserved_column_sums(), (0, 0))

        game.remove_cell(0, 1)

        self.assertEqual(game.reserved_row_sums(), (0, 0))

        game.mark_cell(0, 0)
        game.mark_cell(1, 1)

        self.assertEqual(game.reserved_row_sums   (), (1, 4))
        self.assertEqual(game.reserved_column_sums(), (1, 4))

        game.unmark_cell(0, 0)

        self.assertEqual(game.reserved_row_sums(), (0, 4))

        game.reset()

        self.assertEqual(game.reserved_row_sums   (), (0, 0))
        self.assertEqual(game.reserved_column_sums(), (0, 0))

    def test_undo_restore_preserves_removed_cell_order(self) -> None:
        game = NumberSumsGame(
            board=(
                (1, 2),
                (3, 4),
            ),

            row_targets   =(0, 0),
            column_targets=(0, 0),
        )

        game.remove_cell(0, 0)
        game.remove_cell(0, 1)

        expected = game.removed_cells

        game.restore_cell(0, 0)

        self.assertTrue (game.undo())
        self.assertEqual(game.removed_cells, expected)

    def test_solver_finds_cells_without_changing_game(self) -> None:
        game = self.make_small_game()

        self.assertTrue(game.known_solvable)

        solution = game.solve()

        self.assertEqual(solution          , frozenset({(0, 1), (1, 0)}))
        self.assertEqual(game.removed_cells, ())

        self.assertFalse(game.is_won())

    def test_apply_solution_and_win_formula(self) -> None:
        game = self.make_small_game()

        applied = game.apply_solution()

        self.assertEqual(applied                , frozenset({(0, 1), (1, 0)}))
        self.assertEqual(len(game.removed_cells), 2)

        self.assertEqual(game.current_row_sums   (), game.row_targets   )
        self.assertEqual(game.current_column_sums(), game.column_targets)

        self.assertTrue(game.is_won())

    def test_invalid_external_solution_is_not_applied(self) -> None:
        game = self.make_small_game()

        game.remove_cell(0, 1)

        with self.assertRaises(ValueError):
            game.apply_solution({(0, 0)})

        self.assertEqual(game.removed_cells, (Cell(0, 1, 2),))

    def test_unsatisfiable_board(self) -> None:
        with self.assertRaises(NoSolutionError):
            NumberSumsGame(
                board=(
                    (1, 1),
                    (1, 1),
                ),

                row_targets   =(1, 1),
                column_targets=(0, 0),
            )

    def test_incompatible_decisions_are_rejected_atomically(self) -> None:
        remove_game = self.make_small_game()

        remove_before = (remove_game.decisions,
                         remove_game.history  )

        with self.assertRaises(InvalidMoveError) as remove_context:
            remove_game.remove_cell(0, 0)

        self.assertEqual(remove_context.exception.action             , "remove"     )
        self.assertEqual(remove_context.exception.coordinate         , (0, 0)       )
        self.assertEqual((remove_game.decisions, remove_game.history), remove_before)

        self.assertIn(
            "The removal eliminates all compatible solutions", remove_context.exception.reason
        )

        mark_game = self.make_small_game()

        mark_before = (mark_game.decisions,
                       mark_game.history  )

        with self.assertRaises(InvalidMoveError) as mark_context:
            mark_game.mark_cell(0, 1)

        self.assertEqual(mark_context.exception.action           , "mark"     )
        self.assertEqual(mark_context.exception.coordinate       , (0, 1)     )
        self.assertEqual((mark_game.decisions, mark_game.history), mark_before)

    def test_relaxations_and_undo_preserve_the_consistency_invariant(self) -> None:
        game = self.make_small_game()

        def assert_consistent() -> None:
            solver = NumberSumsCSPSolver.from_game(game)

            self.assertTrue(
                solver.is_consistent(dict(game.decisions))
            )

        game.mark_cell   (0, 0), assert_consistent()
        game.remove_cell (0, 1), assert_consistent()
        game.unmark_cell (0, 0), assert_consistent()
        game.undo            (), assert_consistent()
        game.restore_cell(0, 1), assert_consistent()

        while game.undo():
            assert_consistent()

    def test_coordinates_are_validated(self) -> None:
        game = self.make_small_game()

        with self.assertRaises(IndexError):
            game.remove_cell ( 2, 0)
        with self.assertRaises(IndexError):
            game.restore_cell(-1, 0)

        with self.assertRaises(TypeError ):
            game.is_removed  (True, 0)

    def test_constructor_copies_input_and_validates_shape(self) -> None:
        board = [
            [1, 2],
            [3, 4],
        ]
        game = NumberSumsGame(board, [1, 4], [1, 4])

        board[0][0] = 99

        self.assertEqual(game.board[0][0], 1)

        with self.assertRaises(ValueError):
            NumberSumsGame(((1, 2),), (1,), (1,))

    def test_render_includes_targets_and_removed_marker(self) -> None:
        game = self.make_small_game()

        game.remove_cell(0, 1)

        rendered = game.render()

        self.assertIn("meta (atual)", rendered)
        self.assertIn("metas"       , rendered)
        self.assertIn("·"           , rendered)

    def test_render_aligns_multi_digit_column_values(self) -> None:
        game = NumberSumsGame(
            board=(
                (99, 99),
                (99, 99),
            ),

            row_targets   =(198, 198),
            column_targets=(198, 198),
        )

        lines = game.render().splitlines()

        self.assertIn("  1   2"         , lines[ 0])
        self.assertIn("198 198   metas" , lines[-2])
        self.assertIn("198 198   atuais", lines[-1])


if __name__ == "__main__":
    unittest.main()
