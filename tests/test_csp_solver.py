from __future__ import annotations

import itertools
import unittest

from unittest.mock import patch

from number_sums import NoSolutionError, NumberSumsCSPSolver, NumberSumsGame


def brute_force_solutions(game: NumberSumsGame) -> set[frozenset[tuple[int, int]]]:
    coordinates = tuple(
        (row, column)
        for row    in range(game.size)
        for column in range(game.size)
    )

    solutions: set[frozenset[tuple[int, int]]] = set()
    for kept_values in itertools.product((0, 1), repeat=len(coordinates)):
        removed = frozenset(
            coordinate
            for coordinate, kept in zip(coordinates, kept_values)
            if  not kept
        )

        row_sums = tuple(
            sum(
                game.board[row][column]
                for column in range(game.size)
                if (row, column) not in removed
            )
            for row in range(game.size)
        )
        column_sums = tuple(
            sum(
                game.board[row][column]
                for row in range(game.size)
                if (row, column) not in removed
            )
            for column in range(game.size)
        )

        if row_sums == game.row_targets and column_sums == game.column_targets:
            solutions.add(removed)

    return solutions


class NumberSumsCSPSolverTests(unittest.TestCase):
    def make_unique_game(self) -> NumberSumsGame:
        return NumberSumsGame(
            board=(
                (1, 2),
                (3, 4),
            ),

            row_targets   =(1, 4),
            column_targets=(1, 4),
        )

    def test_csp_model_contains_boolean_variables_and_sum_constraints(self) -> None:
        solver = NumberSumsCSPSolver.from_game(self.make_unique_game())

        self.assertEqual(len(solver.variables  ), 4)
        self.assertEqual(len(solver.constraints), 4)

        self.assertTrue(
            all(
                domain == frozenset((0, 1))
                for domain in solver.domains.values()
            )
        )

        self.assertEqual(solver.constraints[0].name  , "Linha 1")
        self.assertEqual(solver.constraints[0].target, 1        )
        self.assertEqual(solver.neighbors  [(0, 0)  ], frozenset({(0, 1), (1, 0)}))

        exposed_neighbors = solver.neighbors

        assert isinstance(exposed_neighbors, dict)

        exposed_neighbors.clear()

        self.assertEqual(len(solver.neighbors), 4)

        with self.assertRaises(ValueError):
            NumberSumsCSPSolver(
                tuple(
                    tuple(1 for _ in range(9))
                    for _ in range(9)
                ),

                (1,) * 9,
                (1,) * 9,
            )

    def test_gac_solves_forced_problem_without_search_decisions(self) -> None:
        solver = NumberSumsCSPSolver.from_game(self.make_unique_game())

        domains = solver.infer()
        result  = solver.solve_with_trace()

        self.assertEqual(domains[(0, 0)], frozenset((1,)))
        self.assertEqual(domains[(0, 1)], frozenset((0,)))
        self.assertEqual(result.solution, frozenset({(0, 1), (1, 0)}))

        self.assertNotIn("decision"   , {step.kind for step in result.steps})
        self.assertIn   ("propagation", {step.kind for step in result.steps})

        self.assertEqual(result.steps[-1].kind, "solution")

    def test_backtracking_mrv_lcv_enumerates_multiple_solutions(self) -> None:
        game   = NumberSumsGame(
            board=(
                (1, 1),
                (1, 1),
            ),

            row_targets   =(1, 1),
            column_targets=(1, 1),
        )
        solver = NumberSumsCSPSolver.from_game(game)

        solutions = solver.find_solutions  ()
        traced    = solver.solve_with_trace()
        hint      = solver.next_hint       ()

        self.assertEqual(
            set(solutions),
            {
                frozenset({(0, 0), (1, 1)}),
                frozenset({(0, 1), (1, 0)}),
            },
        )

        self.assertEqual(len(solutions), len(set(solutions)))

        self.assertIn     ("decision"        , {step.kind for step in traced.steps})
        self.assertGreater(traced.stats.nodes, 1)

        self.assertIsNotNone(hint)
        self.assertEqual    (hint.kind  , "decision"        )
        self.assertIn       (hint.action, ("remove", "mark"))

    def test_gac_detects_subset_sum_hole(self) -> None:
        solver = NumberSumsCSPSolver(
            board=(
                (2, 2),
                (2, 2),
            ),

            row_targets   =(1, 1),
            column_targets=(1, 1),
        )

        self.assertEqual(solver.find_solutions(), [])

        with self.assertRaises(NoSolutionError):
            solver.infer()
        with self.assertRaises(NoSolutionError):
            solver.solve()

    def test_solver_matches_independent_brute_force(self) -> None:
        for seed in range(12):
            with self.subTest(seed=seed):
                game = NumberSumsGame.random(
                    size=3, seed=seed, unique_solution=False
                )

                expected = brute_force_solutions(game)
                actual   = set(
                    NumberSumsCSPSolver.from_game(game).find_solutions()
                )

                self.assertEqual(actual, expected)

    def test_limit_and_assumptions(self) -> None:
        game   = NumberSumsGame(
            board=(
                (1, 1),
                (1, 1),
            ),

            row_targets   =(1, 1),
            column_targets=(1, 1),
        )
        solver = NumberSumsCSPSolver.from_game(game)

        one        = solver.find_solutions(limit=1)
        compatible = solver.solve         (assumptions={(0, 0): 0})

        self.assertEqual(len(one), 1)
        self.assertIn   ((0, 0)  , compatible)

        with self.assertRaises(ValueError):
            solver.find_solutions(limit=0)
        with self.assertRaises(ValueError):
            solver.solve(assumptions={(0, 0): 2})

    def test_hint_guides_execution_decisions_without_mutating_game(self) -> None:
        game   = self               .make_unique_game()
        solver = NumberSumsCSPSolver.from_game       (game)

        before_history = game  .history
        first          = solver.next_hint()

        self.assertIsNotNone(first)
        self.assertEqual    (first.kind  , "forced"          )
        self.assertIn       (first.action, ("remove", "mark"))

        self.assertEqual(game.removed_cells, ())
        self.assertEqual(game.marked_cells , ())
        self.assertEqual(game.history      , before_history)

        if first.action == "remove":
            game.remove_cell(first.row, first.column)
        else:
            game.mark_cell  (first.row, first.column)

        second = solver.next_hint()

        self.assertIsNotNone(second)
        self.assertNotEqual (second.coordinate, first.coordinate)

    def test_hint_raises_for_an_inconsistent_external_state(self) -> None:
        game                    = self.make_unique_game()
        game._decisions[(0, 0)] = 0

        solver = NumberSumsCSPSolver.from_game(game)

        with self.assertRaises(NoSolutionError):
            solver.next_hint()

    def test_hint_is_none_after_win(self) -> None:
        game = self.make_unique_game()

        game.solve(apply=True)

        self.assertIsNone(game.next_hint())

    def test_trace_is_deterministic(self) -> None:
        game   = NumberSumsGame(
            board=(
                (1, 1),
                (1, 1),
            ),

            row_targets   =(1, 1),
            column_targets=(1, 1),
        )
        solver = NumberSumsCSPSolver.from_game(game)

        first  = solver.solve_with_trace()
        second = solver.solve_with_trace()

        self.assertEqual(first, second)

    def test_forced_next_step_stops_before_complete_search(self) -> None:
        solver = NumberSumsCSPSolver.from_game(self.make_unique_game())

        with patch.object(
            solver      ,
            "_backtrack",
            side_effect=AssertionError("The complete search should not be executed."),
        ):
            step = solver.next_step()
            hint = solver.next_hint()

        self.assertIsNotNone(step)
        self.assertIsNotNone(hint)

        self.assertEqual(step.kind, "propagation")

    def test_search_step_skips_an_lcv_branch_that_would_backtrack(self) -> None:
        solver = NumberSumsCSPSolver(
            board=(
                (5, 6, 8, 3, 2, 7),
                (7, 8, 7, 1, 2, 9),
                (1, 7, 6, 6, 2, 3),
                (1, 2, 3, 3, 1, 7),
                (9, 9, 3, 8, 1, 7),
                (9, 7, 9, 5, 2, 6),
            ),

            row_targets   =(13, 17, 12, 8, 18, 15),
            column_targets=(14, 16, 15, 9,  4, 25),
        )
        assumptions = {
            (5, 3): 0,
            (5, 5): 1,
            (0, 0): 1,
            (1, 5): 1,
            (2, 5): 1,
            (0, 3): 0,
            (0, 5): 0,
            (1, 4): 0,
            (2, 4): 1,
        }

        step = solver.next_step(assumptions=assumptions)

        self.assertIsNotNone(step)

        self.assertEqual(
            (step.kind , step.cell, step.value),
            ("decision", (0, 2)   , 1         ),
        )
        self.assertTrue (
            solver.is_consistent(
                {**assumptions, step.cell: step.value}
            )
        )


if __name__ == "__main__":
    unittest.main()
