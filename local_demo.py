"""第一週本機終端機介面。每次啟動可指定不同的 user_id。"""

import argparse

import commands


def main():
    parser = argparse.ArgumentParser(description="課程管家第一週本機 Demo")
    parser.add_argument("--user-id", default="DEMO_USER", help="本次操作使用者 ID")
    args = parser.parse_args()

    print(f"課程管家 Demo（user_id: {args.user_id}），輸入 exit 離開。")
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
