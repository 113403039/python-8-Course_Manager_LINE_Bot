import calc_and_storage


def set_pending(user_data, pending_data):
    # 將操作暫存在使用者資料中，尚未修改正式課程。
    user_data["pending"] = pending_data


def confirm_pending(user_data):
    # 確認目前待辦，並把配分或成績寫入正式課程。
    pending = user_data.get("pending")
    if not pending:
        return "目前沒有待確認的資料。"

    pending_type = pending.get("type")
    if pending_type == "grading":
        course_name = pending["course"]
        courses = user_data.setdefault("courses", {})

        # 重設課程配分時，依規格清除舊成績與考試。
        courses[course_name] = {
            "grading": pending["grading"],
            "grades": {},
            "events": [],
        }
        result = f"課程「{course_name}」的配分已建立。"

    elif pending_type == "grade":
        course_name = pending.get("course")
        item = pending.get("item")
        course = user_data.get("courses", {}).get(course_name)
        grading = course.get("grading", {}) if course is not None else {}
        if not isinstance(grading, dict) or item not in grading:
            return "待確認的課程或成績項目已不存在，無法儲存。"

        score = pending.get("score")
        is_valid, validation_message = calc_and_storage.validate_score(score)
        if not is_valid:
            return f"待確認的成績無效：{validation_message}"

        course.setdefault("grades", {})[item] = score
        result = f"課程「{course_name}」的成績項目「{item}」已儲存為 {score} 分。"

    elif pending_type == "event":
        course_name = pending.get("course")
        exam_name = pending.get("name")
        event_date = pending.get("date")
        course = user_data.get("courses", {}).get(course_name)
        if course is None:
            return f"待確認的課程「{course_name}」不存在，無法儲存考試。"
        is_valid, validation_message = calc_and_storage.valid_date(event_date)
        if not is_valid:
            return validation_message
        added, result = calc_and_storage.add_event(course, exam_name, event_date)
        if not added:
            return result
        result = f"課程「{course_name}」{result}"

    else:
        return "待確認資料格式不正確，無法儲存。"

    user_data["pending"] = None
    return result


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
            "可用指令：\n"
            "1. 配分 課程名稱 項目配分...：建立課程配分\n"
            "   例如：配分 統計學 作業20 期中考30 期末考40 出席10\n"
            "2. 查配分 課程名稱：查看課程配分\n"
            "   例如：查配分 統計學\n"
            "3. 成績 課程名稱 項目名稱 分數：輸入成績，待確認\n"
            "   例如：成績 統計學 期中考 85\n"
            "4. 查成績 課程名稱：查看已輸入和待輸入成績\n"
            "   例如：查成績 統計學\n"
            "5. 總成績 課程名稱：查看加權總分與封頂成績\n"
            "   例如：總成績 統計學\n"
            "6. 試算 課程名稱 目標 分數 項目 目標項目 [假設 項目 分數 ...]：試算目標項目所需分數\n"
            "   例如：試算 統計學 目標 85 項目 期末考 假設 期中考 100 出席 100\n"
            "7. 考試 課程名稱 考試名稱 YYYY-MM-DD：新增考試日期，待確認\n"
            "   例如：考試 統計學 期中考 2026-12-25\n"
            "8. 查日期 YYYY-MM-DD：查詢當日考試\n"
            "   例如：查日期 2026-12-25\n"
            "9. 確認：儲存目前待確認的配分、成績或考試\n"
            "   例如：確認\n"
            "10. 取消：放棄目前待確認的操作\n"
            "    例如：取消"
        )

    elif command == "考試":
        usage = (
            "正確格式：考試 課程名稱 考試名稱 YYYY-MM-DD\n"
            "例如：考試 統計學 期中考 2026-12-25"
        )
        if len(parts) != 4:
            return usage

        course_name, exam_name, event_date = parts[1], parts[2], parts[3]
        is_valid, date_message = calc_and_storage.valid_date(event_date)
        if not is_valid:
            return f"{date_message}\n{usage}"
        course = user_data["courses"].get(course_name)
        if course is None:
            return f"找不到課程「{course_name}」。請先建立課程配分。"
        if not exam_name.strip():
            return usage
        events = course.get("events", [])
        if any(
            isinstance(event, dict)
            and event.get("date") == event_date
            for event in events
        ):
            return f"這門課已登記 {event_date} 的「{exam_name}」考試。"

        set_pending(
            user_data,
            {"type": "event", "course": course_name, "name": exam_name, "date": event_date},
        )
        calc_and_storage.save_data(data)
        return "\n".join(
            [
                f"考試日期預覽：課程「{course_name}」",
                f"考試名稱：{exam_name}",
                f"日期：{event_date}",
                "請輸入「確認」儲存，或輸入「取消」放棄。",
            ]
        )

    elif command == "查日期":
        if len(parts) != 2:
            return "正確格式：查日期 YYYY-MM-DD\n例如：查日期 2026-12-25"
        event_date = parts[1]
        is_valid, date_message = calc_and_storage.valid_date(event_date)
        if not is_valid:
            return f"{date_message}\n正確格式：查日期 YYYY-MM-DD\n例如：查日期 2026-12-25"
        try:
            events = calc_and_storage.query_events_by_date(user_data, event_date)
        except ValueError as error:
            return str(error)
        if not events:
            return "當天沒有已登記的考試"
        lines = [f"{event_date} 的考試："]
        for event in events:
            lines.append(f"{event['course']}：{event['name']}")
        return "\n".join(lines)

    elif command == "試算":
        usage = (
            "正確格式：試算 課程名稱 目標 分數 項目 目標項目 [假設 項目 分數 ...]\n"
            "例如：試算 統計學 目標 85 項目 期末考 假設 期中考 100 出席 100"
        )
        if (
            len(parts) < 6
            or parts[2] != "目標"
            or parts[4] != "項目"
            or (
                len(parts) != 6
                and (
                    len(parts) < 9
                    or parts[6] != "假設"
                    or (len(parts) - 7) % 2 != 0
                )
            )
        ):
            return usage

        course_name, target_text, target_item = parts[1], parts[3], parts[5]
        try:
            target_score = float(target_text)
        except ValueError:
            return f"目標總分必須是數字。\n{usage}"

        assumptions = {}
        try:
            for index in range(7, len(parts), 2):
                item, score_text = parts[index], parts[index + 1]
                if item in assumptions:
                    return f"假設項目「{item}」重複輸入。\n{usage}"
                assumptions[item] = float(score_text)
        except ValueError:
            return f"假設分數必須是數字。\n{usage}"

        course = user_data["courses"].get(course_name)
        if course is None:
            return f"找不到課程「{course_name}」。請先建立課程配分。"

        grading = course.get("grading", {})
        if not isinstance(grading, dict) or not grading:
            return f"課程「{course_name}」尚未設定配分，無法試算。"
        grades = course.get("grades", {})
        if not isinstance(grades, dict):
            grades = {}
        if target_item not in grading:
            return f"目標項目「{target_item}」不在課程配分中。可用項目：{'、'.join(grading)}"

        missing_assumptions = [
            item for item in grading
            if item != target_item and item not in grades and item not in assumptions
        ]
        if missing_assumptions:
            return (
                "資料不足，請提供其他未知項目的假設分數："
                + "、".join(missing_assumptions) + f"\n{usage}"
            )

        try:
            required = calc_and_storage.required_score(
                grading, grades, target_item, target_score, assumptions
            )
            target_valid, target_message = calc_and_storage.validate_score(target_score)
            if not target_valid:
                return f"目標總分無效：{target_message}\n{usage}"
            assumption_messages = []
            for item, score in assumptions.items():
                valid, message = calc_and_storage.validate_score(score)
                if not valid:
                    return f"假設項目「{item}」分數無效：{message}\n{usage}"
                assumption_messages.append(f"{item}：{score:g} 分")
        except (ValueError, TypeError, OverflowError) as error:
            return f"無法試算：{error}"

        lines = [
            f"課程「{course_name}」目標總成績：{target_score:g} 分",
            "目前已知成績："
            + ("、".join(f"{item} {score:g} 分" for item, score in grades.items()) if grades else "無"),
            "假設分數：" + ("、".join(assumption_messages) if assumption_messages else "無"),
        ]
        if required == 0:
            lines.append("目前已達成目標。")
        else:
            lines.append(f"目標項目「{target_item}」所需分數：{required:g} 分")
            if required > 100:
                lines.append("目前需要超過 100 分，代表單靠該項目無法達成目標，可能需要額外加分。")
        return "\n".join(lines)

    elif command == "總成績":
        if len(parts) != 2:
            return "格式錯誤。請輸入：總成績 課程名稱\n例如：總成績 統計學"

        course_name = parts[1]
        course = user_data["courses"].get(course_name)
        if course is None:
            return f"找不到課程「{course_name}」。請先建立課程配分。"

        grading = course.get("grading", {})
        if not isinstance(grading, dict) or not grading:
            return f"課程「{course_name}」尚未設定配分，請先輸入配分指令。"

        grades = course.get("grades", {})
        if not isinstance(grades, dict):
            grades = {}
        missing_items = [item for item in grading if item not in grades]

        try:
            raw_total = calc_and_storage.weighted_total(grading, grades)
            if missing_items:
                lines = [f"課程「{course_name}」目前已知加權累計：{raw_total:g} 分"]
                lines.append("已輸入成績及加權貢獻：")
                if grades:
                    for item, score in grades.items():
                        contribution = score * (grading[item] / 100)
                        lines.append(
                            f"{item}：{score} 分 × {grading[item]}% = {contribution:g} 分"
                        )
                else:
                    lines.append("目前沒有已輸入的成績。")
                lines.append("尚未輸入：" + "、".join(missing_items))
                lines.append("目前結果不是最終總成績。")
                return "\n".join(lines)

            final = calc_and_storage.final_total(raw_total)
        except (ValueError, TypeError, KeyError) as error:
            return f"無法計算總成績：{error}"

        lines = [
            f"課程「{course_name}」原始總分：{raw_total:g} 分",
            f"封頂後的最終成績：{final:g} 分",
        ]
        if raw_total > 100:
            lines.append("原始總分超過 100，最終成績已封頂為 100 分。")
        return "\n".join(lines)

    elif command == "查成績":
        if len(parts) != 2:
            return "格式錯誤。請輸入：查成績 課程名稱\n例如：查成績 統計學"

        course_name = parts[1]
        course = user_data["courses"].get(course_name)
        if course is None:
            return f"找不到課程「{course_name}」。請先建立課程配分。"

        grading = course.get("grading", {})
        if not grading:
            return f"課程「{course_name}」尚未設定配分，請先輸入配分指令。"

        grades = course.get("grades", {})
        if not isinstance(grades, dict):
            grades = {}
        lines = [f"課程「{course_name}」的成績："]
        for item in grading:
            if item in grades:
                lines.append(f"{item}：{grades[item]} 分")
            else:
                lines.append(f"{item}：尚未輸入")
        return "\n".join(lines)

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

    elif command == "成績":
        if len(parts) != 4:
            return (
                "格式錯誤。請輸入：成績 課程名稱 項目名稱 分數\n"
                "例如：成績 統計學 期中考 85"
            )

        course_name, item, score_text = parts[1], parts[2], parts[3]
        course = user_data["courses"].get(course_name)
        if course is None:
            return f"找不到課程「{course_name}」。請先建立課程配分。"

        grading = course.get("grading", {})
        if not grading:
            return f"課程「{course_name}」尚未設定配分，請先輸入配分指令。"
        if item not in grading:
            return (
                f"課程「{course_name}」沒有「{item}」這個配分項目。\n"
                f"可輸入項目：{'、'.join(grading)}"
            )

        try:
            # 整數文字保留為 int；其他可解析的數字使用 float。
            if score_text.lstrip("+-").isdigit():
                score = int(score_text)
            else:
                score = float(score_text)
        except ValueError:
            return (
                f"分數格式錯誤：「{score_text}」不是數字。\n"
                "格式：成績 課程名稱 項目名稱 分數\n"
                "例如：成績 統計學 期中考 85 或 成績 統計學 期中考 87.5"
            )

        is_valid, validation_message = calc_and_storage.validate_score(score)
        if not is_valid:
            return f"{validation_message}\n例如：成績 統計學 期中考 85"

        set_pending(
            user_data,
            {
                "type": "grade",
                "course": course_name,
                "item": item,
                "score": score,
            },
        )
        calc_and_storage.save_data(data)

        return "\n".join(
            [
                f"成績預覽：課程「{course_name}」",
                f"項目：{item}",
                f"分數：{score_text} 分",
                validation_message,
                "請輸入「確認」儲存，或輸入「取消」放棄。",
            ]
        )

    else:
        return (
            "無法辨識這個指令。請依照以下格式輸入：\n"
            "建立配分：配分 課程名稱 項目配分...\n"
            "輸入成績：成績 課程名稱 項目名稱 分數\n"
            "查詢成績：查成績 課程名稱\n"
            "查詢配分：查配分 課程名稱（也可輸入：查詢配分 課程名稱）\n"
            "例如：配分 統計學 作業20 期中考30 期末考40 出席10；"
            "成績 統計學 期中考 85"
        )
