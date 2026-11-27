"""本機終端機互動 Demo，呼叫指令處理器，不連接 LINE API。"""

import argparse

import commands


def main():
    parser = argparse.ArgumentParser(description="課程管家本機互動 Demo（不連接 LINE API）")
    parser.add_argument("--user-id", default="DEMO_USER", help="本次操作使用者 ID")
    args = parser.parse_args()

    print(f"課程管家本機 Demo - user_id: {args.user_id}，輸入 說明 查看指令，輸入 exit 離開。")
    while True:
        try:
            text = input("> ")
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if text.strip().lower() in {"exit", "quit"}:
            break
        print(commands.handle_text(args.user_id, text))


if __name__ == "__main__":
    main()
