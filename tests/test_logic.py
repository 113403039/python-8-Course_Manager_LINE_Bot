import contextlib
import io
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

import calc_and_storage
import commands
import local_demo


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


class TestGradeCommands(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        data_file = os.path.join(self.temporary_directory.name, "users.json")
        patcher = patch.object(calc_and_storage, "DATA_FILE", data_file)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.user_id = "GRADE_COMMAND_TEST_USER"

    def send(self, text):
        return commands.handle_text(self.user_id, text)

    def create_course(self):
        preview = self.send(
            "配分 統計學 作業20 期中考30 期末考40 出席10"
        )
        self.assertIn("配分預覽", preview)
        return self.send("確認")

    def get_course(self):
        return calc_and_storage.load_data()["users"][self.user_id]["courses"]["統計學"]

    def test_week_one_grading_flow_still_works(self):
        result = self.create_course()
        self.assertIn("配分已建立", result)

        query = self.send("查配分 統計學")
        self.assertIn("作業：20%", query)
        self.assertIn("期中考：30%", query)
        self.assertIn("期末考：40%", query)
        self.assertIn("出席：10%", query)

    def test_normal_score_is_pending_until_confirmation_then_saved(self):
        self.create_course()

        preview = self.send("成績 統計學 期中考 85")
        self.assertIn("課程「統計學」", preview)
        self.assertIn("項目：期中考", preview)
        self.assertIn("分數：85 分", preview)
        self.assertEqual(self.get_course()["grades"], {})

        result = self.send("確認")
        self.assertIn("已儲存為 85 分", result)
        self.assertEqual(self.get_course()["grades"]["期中考"], 85)

    def test_score_over_100_warns_and_preserves_original_value(self):
        self.create_course()

        preview = self.send("成績 統計學 期中考 105")
        self.assertIn("警告", preview)
        self.assertIn("105", preview)
        self.assertEqual(self.get_course()["grades"], {})

        self.send("確認")
        self.assertEqual(self.get_course()["grades"]["期中考"], 105)

    def test_negative_and_non_numeric_scores_are_rejected(self):
        self.create_course()

        negative_result = self.send("成績 統計學 期中考 -5")
        self.assertIn("不可為負數", negative_result)
        self.assertIsNone(
            calc_and_storage.load_data()["users"][self.user_id]["pending"]
        )

        non_numeric_result = self.send("成績 統計學 期中考 abc")
        self.assertIn("不是數字", non_numeric_result)
        self.assertIn("例如：成績 統計學 期中考 85", non_numeric_result)
        self.assertIsNone(
            calc_and_storage.load_data()["users"][self.user_id]["pending"]
        )
        self.assertEqual(self.get_course()["grades"], {})

    def test_cancel_does_not_save_score(self):
        self.create_course()
        self.send("成績 統計學 作業 90")

        result = self.send("取消")
        self.assertIn("已取消", result)
        self.assertEqual(self.get_course()["grades"], {})

    def test_query_shows_known_and_unknown_scores_without_zeroes(self):
        self.create_course()
        self.send("成績 統計學 期中考 88.5")
        self.send("確認")

        query = self.send("查成績 統計學")
        self.assertIn("期中考：88.5 分", query)
        self.assertIn("作業：尚未輸入", query)
        self.assertIn("期末考：尚未輸入", query)
        self.assertIn("出席：尚未輸入", query)
        self.assertNotIn("尚未輸入：0", query)


    def enter_grade(self, item, score):
        self.send(f"成績 統計學 {item} {score}")
        return self.send("確認")

    def test_total_with_all_grades_missing(self):
        self.create_course()
        result = self.send("總成績 統計學")
        self.assertIn("目前已知加權累計：0 分", result)
        self.assertIn("尚未輸入：作業、期中考、期末考、出席", result)
        self.assertIn("不是最終總成績", result)
        self.assertNotIn("封頂後的最終成績", result)

    def test_total_with_partial_grades_lists_contributions_and_missing_items(self):
        self.create_course()
        self.enter_grade("作業", 90)
        self.enter_grade("期中考", 100)
        result = self.send("總成績 統計學")
        self.assertIn("目前已知加權累計：48 分", result)
        self.assertIn("作業：90 分 × 20% = 18 分", result)
        self.assertIn("期中考：100 分 × 30% = 30 分", result)
        self.assertIn("尚未輸入：期末考、出席", result)
        self.assertIn("不是最終總成績", result)

    def test_complete_total_below_100_uses_calculation_helpers(self):
        self.create_course()
        for item in ("作業", "期中考", "期末考", "出席"):
            self.enter_grade(item, 90)
        result = self.send("總成績 統計學")
        self.assertIn("原始總分：90 分", result)
        self.assertIn("封頂後的最終成績：90 分", result)

    def test_complete_total_over_100_is_capped_without_mutating_scores(self):
        self.create_course()
        for item in ("作業", "期中考", "期末考", "出席"):
            self.enter_grade(item, 110)
        before = self.get_course()["grades"].copy()
        result = self.send("總成績 統計學")
        self.assertIn("原始總分：110 分", result)
        self.assertIn("封頂後的最終成績：100 分", result)
        self.assertIn("封頂為 100 分", result)
        self.assertEqual(self.get_course()["grades"], before)


    def test_trial_calculates_required_score_with_stored_and_assumed_grades(self):
        self.create_course()
        self.enter_grade("作業", 90)
        with open(calc_and_storage.DATA_FILE, "rb") as file:
            before = file.read()
        result = self.send("試算 統計學 目標 85 項目 期末考 假設 期中考 100 出席 100")
        self.assertIn("目標總成績：85 分", result)
        self.assertIn("作業 90 分", result)
        self.assertIn("期中考：100 分", result)
        self.assertIn("出席：100 分", result)
        self.assertIn("所需分數：67.5 分", result)
        with open(calc_and_storage.DATA_FILE, "rb") as file:
            self.assertEqual(file.read(), before)
        self.assertEqual(self.get_course()["grades"], {"作業": 90})

    def test_trial_accepts_zero_assumptions(self):
        self.create_course()
        result = self.send("試算 統計學 目標 40 項目 期末考 假設 作業 0 期中考 0 出席 0")
        self.assertIn("作業：0 分", result)
        self.assertIn("所需分數：100 分", result)

    def test_trial_accepts_100_assumptions(self):
        self.create_course()
        result = self.send("試算 統計學 目標 85 項目 期末考 假設 作業 100 期中考 100 出席 100")
        self.assertIn("所需分數：62.5 分", result)

    def test_trial_warns_when_required_score_exceeds_100(self):
        self.create_course()
        result = self.send("試算 統計學 目標 85 項目 期末考 假設 作業 0 期中考 0 出席 0")
        self.assertIn("所需分數：212.5 分", result)
        self.assertIn("目前需要超過 100 分，代表單靠該項目無法達成目標，可能需要額外加分。", result)

    def test_trial_reports_when_target_is_already_met(self):
        self.create_course()
        for item in ("作業", "期中考", "出席"):
            self.enter_grade(item, 100)
        result = self.send("試算 統計學 目標 60 項目 期末考")
        self.assertIn("目前已達成目標", result)
        self.assertNotIn("所需分數", result)

    def test_trial_rejects_invalid_assumption_score(self):
        self.create_course()
        result = self.send("試算 統計學 目標 85 項目 期末考 假設 作業 -1 期中考 90 出席 90")
        self.assertIn("無法試算", result)
        self.assertIn("不可為負數", result)

    def test_trial_lists_all_missing_assumptions_for_multiple_unknown_items(self):
        self.create_course()
        self.enter_grade("作業", 90)
        result = self.send("試算 統計學 目標 85 項目 期末考")
        self.assertIn("資料不足", result)
        self.assertIn("期中考、出席", result)


    def test_add_exam_date_validates_and_saves_only_after_confirmation(self):
        self.create_course()
        preview = self.send("考試 統計學 期中考 2026-12-25")
        self.assertIn("統計學", preview)
        self.assertIn("期中考", preview)
        self.assertIn("2026-12-25", preview)
        self.assertEqual(self.get_course()["events"], [])
        confirmed = self.send("確認")
        self.assertIn("2026-12-25", confirmed)
        self.assertEqual(
            self.get_course()["events"],
            [{"name": "期中考", "date": "2026-12-25"}],
        )

    def test_exam_date_rejects_malformed_and_impossible_dates(self):
        self.create_course()
        malformed = self.send("考試 統計學 期中考 2026/12/25")
        self.assertIn("YYYY-MM-DD", malformed)
        self.assertIn("2026-12-25", malformed)
        impossible = self.send("考試 統計學 期中考 2026-02-30")
        self.assertIn("日期無效", impossible)
        self.assertEqual(self.get_course()["events"], [])

    def test_duplicate_exam_date_and_name_for_same_course_is_rejected(self):
        self.create_course()
        self.send("考試 統計學 期中考 2026-12-25")
        self.send("確認")
        duplicate = self.send("考試 統計學 其他考試 2026-12-25")
        self.assertIn("已登記", duplicate)
        self.assertEqual(len(self.get_course()["events"]), 1)

    def test_cancel_exam_date_does_not_save_event(self):
        self.create_course()
        self.send("考試 統計學 期末考 2026-12-26")
        self.assertEqual(self.get_course()["events"], [])
        self.send("取消")
        self.assertEqual(self.get_course()["events"], [])

    def test_query_date_returns_all_matching_exams(self):
        self.create_course()
        self.send("考試 統計學 期中考 2026-12-25")
        self.send("確認")
        self.send("配分 物理 作業20 期中考30 期末考40 出席10")
        self.send("確認")
        self.send("考試 物理 期末考 2026-12-25")
        self.send("確認")
        result = self.send("查日期 2026-12-25")
        self.assertIn("期中考", result)
        self.assertIn("期末考", result)
        self.assertIn("統計學", result)
        self.assertIn("物理", result)

    def test_query_date_without_exams_shows_empty_message(self):
        result = self.send("查日期 2026-12-25")
        self.assertEqual(result, "當天沒有已登記的考試")

    def test_query_date_rejects_invalid_format(self):
        result = self.send("查日期 2026/12/25")
        self.assertIn("YYYY-MM-DD", result)
        self.assertIn("2026-12-25", result)

    def test_exam_dates_are_isolated_between_users(self):
        other = "OTHER_EXAM_USER"
        commands.handle_text(other, "配分 統計學 作業20 期中考30 期末考40 出席10")
        commands.handle_text(other, "確認")
        commands.handle_text(other, "考試 統計學 他人考試 2026-12-25")
        commands.handle_text(other, "確認")
        own_query = self.send("查日期 2026-12-25")
        self.assertEqual(own_query, "當天沒有已登記的考試")

        self.create_course()
        self.send("考試 統計學 自己考試 2026-12-25")
        self.send("確認")
        own_query = self.send("查日期 2026-12-25")
        self.assertIn("自己考試", own_query)
        self.assertNotIn("他人考試", own_query)


    def test_help_lists_all_commands_with_examples(self):
        help_text = self.send("說明")
        commands_to_check = (
            "配分", "查配分", "成績", "查成績",
            "總成績", "試算", "考試", "查日期",
            "確認", "取消",
        )
        for number, command in enumerate(commands_to_check, 1):
            with self.subTest(command=command):
                self.assertIn(f"{number}. {command}", help_text)
        self.assertIn("例如：", help_text)
        self.assertIn("2026-12-25", help_text)

    def test_local_demo_runs_week_one_and_two_workflow_without_line_api(self):
        inputs = [
            "說明",
            "配分 統計學 作業20 期中考30 期末考40 出席10",
            "確認",
            "查配分 統計學",
            "成績 統計學 期中考 85",
            "確認",
            "查成績 統計學",
            "總成績 統計學",
            "試算 統計學 目標 85 項目 期末考 假設 作業 90 出席 100",
            "考試 統計學 期中考 2026-12-25",
            "確認",
            "查日期 2026-12-25",
            "考試 統計學 補考 2027-01-01",
            "取消",
            "查日期 2027-01-01",
            "exit",
        ]
        with patch.object(calc_and_storage, "DATA_FILE", os.path.join(self.temporary_directory.name, "demo.json")):
            with patch("builtins.input", side_effect=inputs), patch.object(
                sys, "argv", ["local_demo.py", "--user-id", self.user_id]
            ), contextlib.redirect_stdout(io.StringIO()) as output:
                local_demo.main()

        transcript = output.getvalue()
        self.assertIn("配分已建立", transcript)
        self.assertIn("期中考：30%", transcript)
        self.assertIn("尚未輸入", transcript)
        self.assertIn("目前已知加權累計", transcript)
        self.assertIn("所需分數", transcript)
        self.assertIn("2026-12-25", transcript)
        self.assertIn("當天沒有已登記的考試", transcript)
        with patch.object(calc_and_storage, "DATA_FILE", os.path.join(self.temporary_directory.name, "demo.json")):
            saved = calc_and_storage.load_data()["users"][self.user_id]["courses"]["統計學"]
        self.assertEqual(saved["events"], [{"name": "期中考", "date": "2026-12-25"}])


    def test_pending_grading_does_not_enter_formal_course_until_confirmation(self):
        preview = self.send("配分 統計學 作業20 期中考30 期末考40 出席10")
        self.assertIn("配分預覽", preview)
        stored_user = calc_and_storage.load_data()["users"][self.user_id]
        self.assertNotIn("統計學", stored_user["courses"])
        self.assertEqual(stored_user["pending"]["type"], "grading")

        self.send("確認")
        self.assertIn("統計學", calc_and_storage.load_data()["users"][self.user_id]["courses"])


    def test_trial_requires_explicit_target_and_assumption_labels(self):
        self.create_course()
        result = self.send("試算 統計學 85 期末考")
        self.assertIn("正確格式：試算 課程名稱 目標 分數", result)
        self.assertIn("例如：試算 統計學 目標 85 項目 期末考 假設", result)


if __name__ == "__main__":
    unittest.main()
