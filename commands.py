import calc_and_storage


def set_pending(user_data, pending_data):
    # 將操作暫存在使用者資料中，尚未修改正式課程。
    user_data["pending"] = pending_data


def confirm_pending(user_data):
    # 確認目前待辦，並把配分寫入正式課程。
    pending = user_data.get("pending")
    if not pending:
        return "目前沒有待確認的資料。"

    if pending.get("type") != "grading":
        return "待確認資料格式不正確，無法儲存。"

    course_name = pending["course"]
    courses = user_data.setdefault("courses", {})

    # 重設課程配分時，依規格清除舊成績與考試。
    courses[course_name] = {
        "grading": pending["grading"],
        "grades": {},
        "events": [],
    }
    user_data["pending"] = None
    return f"課程「{course_name}」的配分已建立。"


def cancel_pending(user_data):
    # 清除待辦，不碰正式課程資料。
    if not user_data.get("pending"):
        return "目前沒有待取消的資料。"
    user_data["pending"] = None
    return "已取消待確認操作，正式課程資料沒有變更。"


def handle_text(user_id, text):
    # 每次指令都從 JSON 載入資料，並依 LINE user_id 隔離使用者。
    data = calc_and_storage.load_data()
    users = data.setdefault("users", {})
    user_data = users.setdefault(user_id, {"courses": {}, "pending": None})
    user_data.setdefault("courses", {})
    user_data.setdefault("pending", None)

    # split() 同時去除首尾空白，並把連續空白整理成單一分隔符號。
    parts = text.split()
    if not parts:
        return (
            "請輸入有效指令，例如：\n"
            "配分 統計學 作業20 期中考30 期末考40 出席10\n"
            "查配分 統計學"
        )

    # 常見說法共用既有指令流程，不改變指令功能。
    aliases = {"查詢配分": "查配分"}
    command = aliases.get(parts[0], parts[0])
    parts[0] = command
    message = " ".join(parts)

    if message == "確認":
        result = confirm_pending(user_data)
        if result.startswith("課程「"):
            calc_and_storage.save_data(data)
        return result

    elif message == "取消":
        result = cancel_pending(user_data)
        # 只有使用者資料本身有待辦時才需要保存清除結果。
        if result.startswith("已取消"):
            calc_and_storage.save_data(data)
        return result

    elif message == "說明":
        return (
            "第一週支援指令：\n"
            "配分 課程名稱 項目配分...：建立或重設課程配分\n"
            "例如：配分 統計學 作業20 期中考30 期末考40 出席10\n"
            "確認：儲存待確認配分\n"
            "取消：放棄待確認配分\n"
            "查配分 課程名稱：查看課程配分"
        )

    elif command == "查配分":
        if len(parts) != 2 or not parts[1].strip():
            return "格式錯誤。請輸入：查配分 課程名稱\n例如：查配分 統計學（也可輸入：查詢配分 統計學）"

        course_name = parts[1]
        course = user_data["courses"].get(course_name)
        if course is None:
            return f"找不到課程「{course_name}」的配分。"

        grading = course.get("grading", {})
        if not grading:
            return f"課程「{course_name}」目前沒有配分資料。"

        lines = [f"課程「{course_name}」的配分："]
        for item, weight in grading.items():
            lines.append(f"{item}：{weight}%")
        return "\n".join(lines)

    elif command == "配分":
        if len(parts) < 3:
            return "格式錯誤。請輸入：配分 課程名稱 項目配分...\n例如：配分 統計學 作業20 期中考30 期末考40 出席10"

        course_name = parts[1]
        tokens = parts[2:]

        try:
            grading = calc_and_storage.parse_weights(tokens)
        except ValueError as error:
            return (
                f"{error}\n正確格式：配分 課程名稱 項目配分...\n"
                "例如：配分 統計學 作業20 期中考30 期末考40 出席10"
            )

        is_valid, validation_message = calc_and_storage.validate_weights(grading)
        if not is_valid:
            return validation_message

        pending_data = {
            "type": "grading",
            "course": course_name,
            "grading": grading,
        }
        set_pending(user_data, pending_data)
        calc_and_storage.save_data(data)

        lines = [f"配分預覽：課程「{course_name}」"]
        for item, weight in grading.items():
            lines.append(f"{item}：{weight}%")
        lines.append(validation_message)

        if course_name in user_data["courses"]:
            lines.append("警告：確認後會清除這門課原有的成績及考試。")

        lines.append("請輸入「確認」儲存，或輸入「取消」放棄。")
        return "\n".join(lines)

    else:
        return (
            "無法辨識這個指令。請依照以下格式輸入：\n"
            "建立配分：配分 課程名稱 項目配分...\n"
            "查詢配分：查配分 課程名稱（也可輸入：查詢配分 課程名稱）\n"
            "例如：配分 統計學 作業20 期中考30 期末考40 出席10"
        )
