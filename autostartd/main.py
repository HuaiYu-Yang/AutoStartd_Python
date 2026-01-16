#!/usr/bin/env python3
import itertools
import json
import os
import platform
import subprocess
import sys
import time

RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
WHITE = "\033[37m"
RESET = "\033[0m"

LANGUAGE = None
CONFIG_PATH = os.path.join(os.path.expanduser("~"), ".autostartd", "config.json")


def safe_print(msg, end="\n"):
    try:
        print(msg, end=end)
    except UnicodeEncodeError:
        encoding = sys.stdout.encoding or "utf-8"
        safe_msg = msg.encode(encoding, errors="replace").decode(encoding, errors="replace")
        print(safe_msg, end=end)


def _supports_chinese():
    encoding = sys.stdout.encoding or "utf-8"
    try:
        "中文".encode(encoding)
        return True
    except Exception:
        return False


def _init_language():
    global LANGUAGE
    if LANGUAGE is not None:
        return
    LANGUAGE = _load_language() or ("zh" if _supports_chinese() else "en")


def _load_language():
    try:
        if not os.path.exists(CONFIG_PATH):
            return None
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        lang = data.get("language")
        if lang in ("zh", "en"):
            return lang
    except Exception:
        return None
    return None


def _save_language():
    try:
        os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
        data = {"language": LANGUAGE}
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=True, indent=2)
    except Exception:
        pass


def set_language(lang):
    global LANGUAGE
    if lang in ("zh", "en"):
        LANGUAGE = lang
        _save_language()


def get_language():
    _init_language()
    return LANGUAGE


def tr(cn, en):
    _init_language()
    return cn if LANGUAGE == "zh" else en


def select_language():
    current = get_language()
    safe_print(tr("请选择语言:", "Select language:"))
    safe_print("1. 中文")
    safe_print("2. English")
    choice = safe_input(tr("请输入数字选择: ", "Select option: ")).strip()
    if is_quit(choice):
        return False
    if choice == "1":
        set_language("zh")
        return current != "zh"
    if choice == "2":
        set_language("en")
        return current != "en"
    print_error(tr("无效选择，请重新输入", "Invalid choice, please try again"))
    return False


def safe_input(prompt):
    try:
        return input(prompt)
    except UnicodeEncodeError:
        safe_print(prompt, end="")
        return input()


def is_quit(value):
    return value is not None and value.strip().lower() == "q"


def print_ok(msg, use_color=True):
    safe_print(f"{GREEN}{msg}{RESET}" if use_color else msg)


def print_error(msg, use_color=True):
    safe_print(f"{RED}{msg}{RESET}" if use_color else msg)


def print_warn(msg, use_color=True):
    safe_print(f"{YELLOW}{msg}{RESET}" if use_color else msg)


def print_info(msg, use_color=True):
    safe_print(f"{WHITE}{msg}{RESET}" if use_color else msg)


def run(cmd, capture=True, shell=None):
    if shell is None:
        shell = not isinstance(cmd, (list, tuple))
    if capture:
        return subprocess.run(cmd, shell=shell, capture_output=True, text=True)
    return subprocess.run(cmd, shell=shell)


def input_nonempty(prompt, max_attempts=3):
    for attempt in range(max_attempts):
        val = safe_input(prompt).strip()
        if is_quit(val):
            return None
        if val:
            return val
        print_error(
            tr(
                f"输入不能为空，请重新输入 ({attempt + 1}/{max_attempts})",
                f"Input cannot be empty ({attempt + 1}/{max_attempts})",
            ),
            use_color=True,
        )
    print_error(tr("超过最大尝试次数，程序退出", "Too many attempts, exiting"), use_color=True)
    sys.exit(1)


def spinner_delay(seconds, message):
    frames = "|/-\\"
    end_time = time.time() + seconds
    for ch in itertools.cycle(frames):
        if time.time() >= end_time:
            break
        safe_print(f"\r{message} {ch}", end="")
        time.sleep(0.12)
    safe_print(f"\r{message} {tr('完成', 'Done')} ")


def get_python_executable():
    return sys.executable or "/usr/bin/python3"


def run_menu(platform_module, title):
    while True:
        print_info(title, use_color=True)
        actions = platform_module.get_actions()
        for idx, (_, label, _) in enumerate(actions, start=1):
            safe_print(f"{idx}. {label}")
        lang_idx = len(actions) + 1
        safe_print(tr(f"{lang_idx}. 切换语言", f"{lang_idx}. Switch Language"))
        safe_print(tr("输入 q 退出", "Press q to quit"))
        choice = safe_input(tr("请输入数字选择: ", "Select option: ")).strip()
        if is_quit(choice):
            break
        if not choice.isdigit():
            print_error(tr("无效选择，请重新输入", "Invalid choice, please try again"), use_color=True)
            continue
        choice_num = int(choice)
        if 1 <= choice_num <= len(actions):
            _, _, handler = actions[choice_num - 1]
            handler()
            continue
        if choice_num == lang_idx:
            if select_language():
                print_info(
                    tr("语言已切换，请手动重新运行脚本", "Language switched, please rerun the script"),
                    use_color=True,
                )
                break
            continue
        print_error(tr("无效选择，请重新输入", "Invalid choice, please try again"), use_color=True)


def main():
    system = platform.system().lower()
    if system == "windows":
        from . import windows

        run_menu(windows, windows.get_menu_title())
        return
    if system == "linux":
        from . import linux

        run_menu(linux, linux.get_menu_title())
        return

    print_error(tr(f"不支持的系统: {system}", f"Unsupported OS: {system}"), use_color=True)


if __name__ == "__main__":
    main()
