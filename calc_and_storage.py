import json
import math
import os
import re
import tempfile


DATA_FILE = os.path.join(os.path.dirname(__file__), "data", "users.json")


def load_data():
    # 讀取使用者資料；檔案不存在時建立空的 users 結構。
    if not os.path.exists(DATA_FILE):
        data = {"users": {}}
        save_data(data)
        return data

    with open(DATA_FILE, "r", encoding="utf-8") as file:
        try:
            data = json.load(file)
        except json.JSONDecodeError as error:
            raise ValueError("data/users.json 的 JSON 格式損壞，未覆蓋原始資料。") from error

    if not isinstance(data, dict) or not isinstance(data.get("users"), dict):
        raise ValueError('data/users.json 格式錯誤，最外層必須包含 "users" dict。')
    return data


def save_data(data):
    # 確認資料結構後，以暫存檔取代正式檔，降低寫入中斷造成損壞的風險。
    if not isinstance(data, dict) or not isinstance(data.get("users"), dict):
        raise ValueError('資料格式錯誤：最外層必須包含 "users" dict。')

    directory = os.path.dirname(DATA_FILE)
    os.makedirs(directory, exist_ok=True)
    temporary_path = None

    try:
        file_descriptor, temporary_path = tempfile.mkstemp(
            dir=directory,
            prefix=".users_",
            suffix=".tmp",
        )
        with os.fdopen(file_descriptor, "w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=4)
            file.flush()
            os.fsync(file.fileno())

        os.replace(temporary_path, DATA_FILE)
        temporary_path = None
    finally:
        if temporary_path is not None and os.path.exists(temporary_path):
            os.remove(temporary_path)


def parse_weights(tokens):
    # 將「項目名稱+整數配分」解析成 dict；格式不符時以 ValueError 說明原因。
    if not isinstance(tokens, list) or not tokens:
        raise ValueError("配分項目必須是非空的清單。")

    grading = {}
    for token in tokens:
        if not isinstance(token, str):
            raise ValueError("每個配分項目都必須是文字，例如「作業20」。")

        if re.search(r"\d\.\d", token):
            raise ValueError(f"配分必須是整數：「{token}」不是有效的整數配分。")

        match = re.fullmatch(r"(.+?)(-?\d+)", token)
        if match is None:
            raise ValueError(f"配分格式錯誤：「{token}」，請使用項目名稱加整數，例如「作業20」。")

        name = match.group(1)
        number_text = match.group(2)
        if not name.strip() or any(character.isspace() for character in name):
            raise ValueError("配分項目名稱不可為空，也不可包含空白。")

        weight = int(number_text)
        if weight < 0:
            raise ValueError(f"「{name}」的配分不可為負數。")
        if name in grading:
            raise ValueError(f"配分項目「{name}」重複，請移除重複項目。")

        grading[name] = weight

    return grading


def validate_weights(grading):
    # 檢查各項配分與總和；超過 100% 時保留原值並回傳確認警告。
    if not isinstance(grading, dict) or not grading:
        return False, "配分資料必須是非空的 dict。"

    total = 0
    for name, weight in grading.items():
        if not isinstance(name, str) or not name.strip():
            return False, "配分項目名稱不可為空。"
        if any(character.isspace() for character in name):
            return False, f"「{name}」的配分項目名稱不可包含空白。"
        if isinstance(weight, bool) or not isinstance(weight, int):
            return False, f"「{name}」的配分必須是整數。"
        if weight < 0 or weight > 100:
            return False, f"「{name}」的配分必須介於 0% 到 100%。"
        total += weight

    if total < 100:
        return False, f"配分總和不足 100%，目前為 {total}%，請補齊配分。"
    if total > 100:
        return (
            True,
            f"警告：目前配分總和為 {total}%，超過 100%。請確認是否包含額外加分項目。",
        )
    return True, "配分總和為 100%，格式正確"


def _is_finite_number(value):
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and (not isinstance(value, float) or math.isfinite(value))
    )


def validate_score(score):
    # 超過 100 分只警告，不修改原始分數。
    if not _is_finite_number(score):
        return False, "成績必須是有限的數字。"
    if score < 0:
        return False, "成績不可為負數。"
    if score > 100:
        return True, f"警告：成績為 {score}，超過 100 分，請確認是否為額外加分。"
    return True, "成績格式正確"


def weighted_total(grading, grades):
    # 只累計已輸入的成績，不把未知項目當作零分或完整總分。
    if not isinstance(grading, dict) or not grading:
        raise ValueError("配分資料必須是非空的 dict。")
    if not isinstance(grades, dict):
        raise ValueError("成績資料必須是 dict。")

    for name, weight in grading.items():
        if not isinstance(name, str) or not name.strip():
            raise ValueError("配分項目名稱不可為空。")
        if any(character.isspace() for character in name):
            raise ValueError(f"「{name}」的配分項目名稱不可包含空白。")
        if isinstance(weight, bool) or not isinstance(weight, int):
            raise ValueError(f"「{name}」的配分必須是整數。")
        if weight < 0 or weight > 100:
            raise ValueError(f"「{name}」的配分必須介於 0% 到 100%。")

    total = 0.0
    for item, score in grades.items():
        if item not in grading:
            raise ValueError(f"成績項目「{item}」不在配分中。")
        valid, message = validate_score(score)
        if not valid:
            raise ValueError(f"「{item}」的{message}")
        weight_ratio = grading[item] / 100
        try:
            contribution = score * weight_ratio
            updated_total = total + contribution
        except OverflowError as error:
            raise ValueError(f"「{item}」的加權成績超出可計算範圍。") from error
        if not math.isfinite(contribution) or not math.isfinite(updated_total):
            raise ValueError("加權總分超出可計算範圍。")
        total = updated_total
    return total


def final_total(raw_total):
    if not _is_finite_number(raw_total) or raw_total < 0:
        raise ValueError("原始總分必須是非負的有限數字。")
    return min(raw_total, 100)


def required_score(grading, grades, target_item, target_score, assumptions=None):
    valid, message = validate_weights(grading)
    if not valid:
        raise ValueError(message)
    if not isinstance(grades, dict):
        raise ValueError("成績資料必須是 dict。")
    if not isinstance(target_item, str) or target_item not in grading:
        raise ValueError("目標項目不在配分中。")
    if grading[target_item] == 0:
        raise ValueError(f"目標項目「{target_item}」的配分為 0，無法反推需求分數。")

    valid, message = validate_score(target_score)
    if not valid:
        raise ValueError(f"目標總分無效：{message}")
    if target_score > 100:
        raise ValueError("目標學期成績不可超過 100 分。")

    if assumptions is None:
        assumptions = {}
    if not isinstance(assumptions, dict):
        raise ValueError("假設分數必須是 dict。")

    for item, score in grades.items():
        if item not in grading:
            raise ValueError(f"成績項目「{item}」不在配分中。")
        valid, message = validate_score(score)
        if not valid:
            raise ValueError(f"「{item}」的{message}")

    unknown_items = [
        item for item in grading if item != target_item and item not in grades
    ]
    for item in assumptions:
        if item not in unknown_items:
            raise ValueError(f"假設項目「{item}」不是其他未知的配分項目。")
        valid, message = validate_score(assumptions[item])
        if not valid:
            raise ValueError(f"假設成績「{item}」無效：{message}")

    missing_items = [item for item in unknown_items if item not in assumptions]
    if missing_items:
        raise ValueError(
            "其他未知項目須提供假設分數：" + "、".join(missing_items)
        )

    trial_grades = {
        item: score for item, score in grades.items() if item != target_item
    }
    trial_grades.update(assumptions)
    other_contribution = weighted_total(grading, trial_grades)
    # 其他項目已達標時，目標項目最低只需 0 分。
    remaining_score = max(target_score - other_contribution, 0.0)
    return remaining_score / (grading[target_item] / 100)
