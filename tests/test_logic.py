import os
import tempfile
import unittest
from unittest.mock import patch

import calc_and_storage


class TestStorage(unittest.TestCase):
    def test_load_data_creates_missing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            data_file = os.path.join(directory, "data", "users.json")
            with patch.object(calc_and_storage, "DATA_FILE", data_file):
                self.assertEqual(calc_and_storage.load_data(), {"users": {}})
                self.assertTrue(os.path.isfile(data_file))

    def test_save_data_can_be_loaded_again_with_chinese_course_name(self):
        with tempfile.TemporaryDirectory() as directory:
            data_file = os.path.join(directory, "data", "users.json")
            data = {
                "users": {
                    "DEMO_USER": {
                        "courses": {
                            "統計學": {
                                "grading": {"作業": 20},
                                "grades": {},
                                "events": [],
                            }
                        },
                        "pending": None,
                    }
                }
            }
            with patch.object(calc_and_storage, "DATA_FILE", data_file):
                calc_and_storage.save_data(data)
                self.assertEqual(calc_and_storage.load_data(), data)

            with open(data_file, "r", encoding="utf-8") as file:
                self.assertIn("統計學", file.read())

    def test_save_data_rejects_invalid_structure(self):
        with self.assertRaises(ValueError):
            calc_and_storage.save_data({"courses": {}})

    def test_corrupt_json_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            data_file = os.path.join(directory, "users.json")
            original_content = '{"users": '
            with open(data_file, "w", encoding="utf-8") as file:
                file.write(original_content)

            with patch.object(calc_and_storage, "DATA_FILE", data_file):
                with self.assertRaisesRegex(ValueError, "格式損壞"):
                    calc_and_storage.load_data()

            with open(data_file, "r", encoding="utf-8") as file:
                self.assertEqual(file.read(), original_content)


class TestWeights(unittest.TestCase):
    def test_parse_weights_returns_dictionary(self):
        self.assertEqual(
            calc_and_storage.parse_weights(["作業20", "期中考30", "期末考40", "出席10"]),
            {"作業": 20, "期中考": 30, "期末考": 40, "出席": 10},
        )

    def test_parse_weights_rejects_negative_weight(self):
        with self.assertRaisesRegex(ValueError, "不可為負數"):
            calc_and_storage.parse_weights(["作業-5"])

    def test_parse_weights_rejects_duplicate_item(self):
        with self.assertRaisesRegex(ValueError, "重複"):
            calc_and_storage.parse_weights(["作業20", "作業30"])

    def test_parse_weights_rejects_malformed_input(self):
        for tokens in (["作業"], [" 作業20"], ["作業 20"], ["作業20.5"], [], "作業20"):
            with self.subTest(tokens=tokens):
                with self.assertRaises(ValueError):
                    calc_and_storage.parse_weights(tokens)

    def test_validate_weights_accepts_total_of_100(self):
        self.assertEqual(
            calc_and_storage.validate_weights({"作業": 20, "期中考": 30, "期末考": 40, "出席": 10}),
            (True, "配分總和為 100%，格式正確"),
        )

    def test_validate_weights_warns_for_total_of_110(self):
        valid, message = calc_and_storage.validate_weights(
            {"作業": 20, "期中考": 30, "期末考": 40, "出席": 10, "加分": 10}
        )
        self.assertTrue(valid)
        self.assertIn("110%", message)
        self.assertIn("額外加分項目", message)

    def test_validate_weights_rejects_total_of_90(self):
        valid, message = calc_and_storage.validate_weights({"作業": 20, "期中考": 30, "期末考": 40})
        self.assertFalse(valid)
        self.assertIn("不足 100%", message)

    def test_validate_weights_rejects_negative_and_over_100_items(self):
        for grading in ({"作業": -1}, {"加分": 101}):
            with self.subTest(grading=grading):
                valid, message = calc_and_storage.validate_weights(grading)
                self.assertFalse(valid)
                self.assertIn("介於 0% 到 100%", message)

    def test_validate_weights_rejects_non_integer_values(self):
        valid, message = calc_and_storage.validate_weights({"作業": 20.5, "期末考": 80})
        self.assertFalse(valid)
        self.assertIn("整數", message)

    def test_validate_weights_rejects_item_names_with_spaces(self):
        valid, message = calc_and_storage.validate_weights({"期中 考": 100})
        self.assertFalse(valid)
        self.assertIn("不可包含空白", message)


class TestScores(unittest.TestCase):
    def test_validate_score_accepts_normal_score(self):
        self.assertEqual(calc_and_storage.validate_score(85), (True, "成績格式正確"))

    def test_validate_score_warns_without_changing_score_over_100(self):
        valid, message = calc_and_storage.validate_score(105)
        self.assertTrue(valid)
        self.assertIn("105", message)
        self.assertIn("確認", message)

    def test_validate_score_rejects_negative_non_finite_and_non_numeric_values(self):
        for score in (-1, float("nan"), float("inf"), "90", True):
            with self.subTest(score=score):
                valid, _ = calc_and_storage.validate_score(score)
                self.assertFalse(valid)


class TestGradeCalculations(unittest.TestCase):
    def test_weighted_total_preserves_over_100_score_contribution(self):
        self.assertEqual(
            calc_and_storage.weighted_total({"期中考": 30}, {"期中考": 105}),
            31.5,
        )

    def test_weighted_total_handles_large_finite_score(self):
        self.assertEqual(
            calc_and_storage.weighted_total({"期中考": 100}, {"期中考": 1e308}),
            1e308,
        )

    def test_weighted_total_rejects_unrepresentable_accumulation(self):
        with self.assertRaisesRegex(ValueError, "加權總分超出可計算範圍"):
            calc_and_storage.weighted_total(
                {"期中考": 100, "期末考": 100},
                {"期中考": 1e308, "期末考": 1e308},
            )

    def test_weighted_total_counts_only_known_grades(self):
        self.assertEqual(
            calc_and_storage.weighted_total(
                {"作業": 20, "期中考": 30, "期末考": 50},
                {"作業": 90, "期中考": 100},
            ),
            48.0,
        )

    def test_weighted_total_rejects_grades_for_unknown_items(self):
        with self.assertRaisesRegex(ValueError, "不在配分中"):
            calc_and_storage.weighted_total({"作業": 100}, {"期中考": 90})

    def test_final_total_caps_only_at_100(self):
        self.assertEqual(calc_and_storage.final_total(106), 100)
        self.assertEqual(calc_and_storage.final_total(86.5), 86.5)

    def test_weighted_raw_total_of_106_is_capped_to_100(self):
        raw_total = calc_and_storage.weighted_total(
            {"作業": 20, "期中考": 30, "期末考": 40, "出席": 10, "加分": 10},
            {"作業": 100, "期中考": 100, "期末考": 100, "出席": 100, "加分": 60},
        )
        self.assertEqual(raw_total, 106)
        self.assertEqual(calc_and_storage.final_total(raw_total), 100)

    def test_required_score_matches_spec_example(self):
        self.assertEqual(
            calc_and_storage.required_score(
                {"作業": 20, "期中考": 30, "出席": 10, "期末考": 40},
                {"作業": 90, "期中考": 100, "出席": 100},
                "期末考",
                85,
            ),
            67.5,
        )

    def test_required_score_requires_assumptions_for_other_unknown_items(self):
        grading = {"作業": 20, "期中考": 30, "出席": 10, "期末考": 40}
        grades = {"期中考": 100}
        with self.assertRaisesRegex(ValueError, "作業、出席"):
            calc_and_storage.required_score(grading, grades, "期末考", 85)

        self.assertEqual(
            calc_and_storage.required_score(
                grading,
                grades,
                "期末考",
                85,
                assumptions={"作業": 90, "出席": 100},
            ),
            67.5,
        )

    def test_required_score_does_not_count_existing_target_grade(self):
        self.assertEqual(
            calc_and_storage.required_score(
                {"作業": 50, "期末考": 50},
                {"作業": 80, "期末考": 100},
                "期末考",
                70,
            ),
            60.0,
        )

    def test_required_score_ignores_overflow_from_existing_target_grade(self):
        self.assertEqual(
            calc_and_storage.required_score(
                {"作業": 100, "期末考": 100},
                {"作業": 1e308, "期末考": 1e308},
                "期末考",
                85,
            ),
            0.0,
        )

    def test_required_score_rejects_zero_weight_target(self):
        with self.assertRaisesRegex(ValueError, "配分為 0"):
            calc_and_storage.required_score(
                {"作業": 100, "加分": 0},
                {"作業": 80},
                "加分",
                85,
            )

    def test_required_score_does_not_cap_requirement_at_100(self):
        self.assertEqual(
            calc_and_storage.required_score(
                {"作業": 50, "期末考": 50},
                {"作業": 80},
                "期末考",
                95,
            ),
            110.0,
        )

    def test_required_score_rejects_target_total_above_100(self):
        with self.assertRaisesRegex(ValueError, "目標學期成績不可超過 100"):
            calc_and_storage.required_score(
                {"作業": 50, "期末考": 50},
                {"作業": 80},
                "期末考",
                110,
            )

    def test_required_score_returns_zero_when_target_is_already_met(self):
        self.assertEqual(
            calc_and_storage.required_score(
                {"作業": 80, "期末考": 20},
                {"作業": 100},
                "期末考",
                60,
            ),
            0.0,
        )


if __name__ == "__main__":
    unittest.main()
