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


if __name__ == "__main__":
    unittest.main()
