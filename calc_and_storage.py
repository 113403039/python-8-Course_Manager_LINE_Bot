import json
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
