#!/usr/bin/env python3
import itertools
import os
import sys
import time
from pathlib import Path

from .main import (
    input_nonempty,
    print_error,
    print_info,
    print_ok,
    print_warn,
    tr,
    run,
    safe_input,
    safe_print,
    spinner_delay,
)

TASK_PREFIX = "AutoStartMgr__"


def _normalize_task_name(task_name):
    if task_name.startswith(TASK_PREFIX):
        return task_name
    return f"{TASK_PREFIX}{task_name}"


def _denormalize_task_name(task_name):
    if task_name.startswith(TASK_PREFIX):
        return task_name[len(TASK_PREFIX):]
    return task_name


def _format_schtasks_error(result):
    msg = result.stderr.strip() or result.stdout.strip()
    if not msg:
        return tr("操作失败", "Operation failed")
    return msg


def _build_task_command(script_path, extra_args=None, python_exe=None):
    target = Path(os.path.expanduser(script_path))
    suffix = target.suffix.lower()
    args = [str(arg) for arg in (extra_args or [])]

    if suffix == ".py":
        interpreter = python_exe or sys.executable
        parts = [f'"{interpreter}"', f'"{target}"']
    else:
        parts = [f'"{target}"']

    parts.extend(f'"{arg}"' for arg in args)
    return " ".join(parts)


def _create_or_update_task(task_name):
    script_path = input_nonempty(tr("请输入脚本或可执行文件绝对路径: ", "Absolute script/executable path: "))
    if script_path is None:
        return None, None, None
    script_path = os.path.expanduser(script_path)
    task_cmd = _build_task_command(script_path)
    python_exe = sys.executable if Path(script_path).suffix.lower() == ".py" else None

    if python_exe:
        print_warn(
            tr(f"将使用 Python: {python_exe}", f"Using Python: {python_exe}"),
            use_color=True,
        )
    else:
        print_warn(
            tr(f"将直接运行: {script_path}", f"Will run directly: {script_path}"),
            use_color=True,
        )

    args = [
        "schtasks",
        "/Create",
        "/SC",
        "ONLOGON",
        "/RL",
        "LIMITED",
        "/TN",
        task_name,
        "/TR",
        task_cmd,
        "/F",
    ]

    spinner_delay(1.2, tr("正在写入任务", "Writing task"))
    result = run(args, capture=True, shell=False)
    return result, script_path, python_exe


def _spinner_wait(seconds, message):
    frames = "|/-\\"
    end_time = time.time() + seconds
    for ch in itertools.cycle(frames):
        if time.time() >= end_time:
            break
        safe_print(f"\r{message} {ch}", end="")
        time.sleep(0.12)
    safe_print(f"\r{message} {tr('完成', 'Done')} ")


def _print_verification(task_name, script_path, python_exe):
    short_name = _denormalize_task_name(task_name)
    print_ok(tr("校验信息:", "Verification:"), use_color=True)
    safe_print(tr(f"- 任务名称: {short_name}", f"- Task name: {short_name}"))
    safe_print(tr(f"- 任务前缀: {TASK_PREFIX}", f"- Task prefix: {TASK_PREFIX}"))
    if python_exe:
        safe_print(tr(f"- Python 路径: {python_exe}", f"- Python path: {python_exe}"))
    safe_print(tr(f"- 脚本路径: {script_path}", f"- Script path: {script_path}"))
    safe_print(tr("- 触发条件: ONLOGON", "- Trigger: ONLOGON"))
    safe_print(tr("- 权限级别: LIMITED", "- Run level: LIMITED"))
    safe_print(tr("- 计划任务状态: ENABLED", "- Task state: ENABLED"))


def _task_exists(task_name):
    args = ["schtasks", "/Query", "/TN", task_name]
    result = run(args, capture=True, shell=False)
    return result.returncode == 0


def _resolve_task_name_for_create(raw_name):
    if raw_name is None:
        return None
    task_name = _normalize_task_name(raw_name)
    if not _task_exists(task_name):
        return task_name

    while True:
        safe_print(tr("任务已存在，请选择操作:", "Task exists. Choose action:"))
        safe_print(tr("1) 覆盖", "1) Overwrite"))
        safe_print(tr("2) 重命名", "2) Rename"))
        choice = safe_input(tr("请输入数字选择: ", "Select option: ")).strip()
        if choice.lower() == "q":
            return None
        if choice == "1":
            return task_name
        if choice == "2":
            new_name = input_nonempty(tr("请输入新的任务名称: ", "New task name: "))
            if new_name is None:
                return None
            task_name = _normalize_task_name(new_name)
            if _task_exists(task_name):
                print_error(tr("名称已存在，请换一个", "Name already exists"), use_color=True)
                continue
            return task_name
        print_error(tr("无效选择，请重新输入", "Invalid choice, please try again"), use_color=True)


def add_startup_task():
    raw_name = input_nonempty(tr("请输入任务名称: ", "Task name: "))
    if raw_name is None:
        return
    task_name = _resolve_task_name_for_create(raw_name)
    if task_name is None:
        return
    result, script_path, python_exe = _create_or_update_task(task_name)
    if result is None:
        return
    if result.returncode == 0:
        _spinner_wait(2.5, tr("正在校验任务", "Verifying task"))
        _print_verification(task_name, script_path, python_exe)
        short_name = _denormalize_task_name(task_name)
        print_ok(tr(f"已创建启动任务: {short_name}", f"Task created: {short_name}"), use_color=True)
        return
    print_error(
        _format_schtasks_error(result)
        + tr("；可尝试使用管理员权限或在任务计划程序中手动创建", " Try running as admin or create via Task Scheduler"),
        use_color=True,
    )


def _is_ours_task_line(line):
    return TASK_PREFIX in line


def _filter_our_tasks(list_output):
    blocks = list_output.split("\n\n")
    kept = []
    for block in blocks:
        if not block.strip():
            continue
        lines = [line for line in block.splitlines() if line.strip()]
        if any(_is_ours_task_line(line) for line in lines):
            kept.append(block)
    return "\n\n".join(kept).strip()


def _count_our_tasks(list_output):
    if not list_output.strip():
        return 0
    blocks = list_output.split("\n\n")
    count = 0
    for block in blocks:
        if not block.strip():
            continue
        lines = [line for line in block.splitlines() if line.strip()]
        if any(_is_ours_task_line(line) for line in lines):
            count += 1
    return count


def _format_task_list_output(output):
    lines = []
    for line in output.splitlines():
        if line.lstrip().startswith("任务名:"):
            prefix, value = line.split(":", 1)
            value = value.strip()
            if value.startswith("\\"):
                value = value[1:]
            value = _denormalize_task_name(value)
            lines.append(f"{prefix}:                             {value}")
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def _filter_tasks_by_keyword(output, keyword):
    if not keyword:
        return output
    blocks = output.split("\n\n")
    kept = []
    for block in blocks:
        if not block.strip():
            continue
        name = None
        for line in block.splitlines():
            if line.lstrip().startswith("任务名:"):
                _, value = line.split(":", 1)
                value = value.strip()
                if value.startswith("\\"):
                    value = value[1:]
                name = _denormalize_task_name(value)
                break
        if name and keyword.lower() in name.lower():
            kept.append(block)
    return "\n\n".join(kept).strip()


def query_startup_task():
    keyword = safe_input(tr("请输入任务名称关键字 (留空查询全部): ", "Keyword (empty for all): ")).strip()
    if keyword.lower() == "q":
        return
    args = ["schtasks", "/Query", "/FO", "LIST", "/V"]

    result = run(args, capture=True, shell=False)
    if result.returncode == 0:
        output = result.stdout.strip()
        total = _count_our_tasks(output)
        output = _filter_our_tasks(output)
        output = _filter_tasks_by_keyword(output, keyword)
        if not keyword:
            print_info(
                tr(f"总览: 本工具创建任务 {total} 条", f"Summary: {total} tasks created by this tool"),
                use_color=True,
            )
        if output:
            print_info(tr("查询结果:", "Results:"), use_color=True)
            safe_print(_format_task_list_output(output))
        else:
            print_info(tr("未找到本项目创建的任务", "No tasks created by this tool"), use_color=True)
        return
    print_error(_format_schtasks_error(result), use_color=True)


def update_startup_task():
    raw_name = input_nonempty(tr("请输入要修改的任务名称: ", "Task name to update: "))
    if raw_name is None:
        return
    task_name = _resolve_task_name_for_create(raw_name)
    if task_name is None:
        return
    result, script_path, python_exe = _create_or_update_task(task_name)
    if result is None:
        return
    if result.returncode == 0:
        _spinner_wait(2.0, tr("正在校验任务", "Verifying task"))
        _print_verification(task_name, script_path, python_exe)
        short_name = _denormalize_task_name(task_name)
        print_ok(tr(f"任务 {short_name} 已更新", f"Task updated: {short_name}"), use_color=True)
        return
    print_error(_format_schtasks_error(result), use_color=True)


def delete_startup_task():
    raw_name = input_nonempty(tr("请输入要删除的任务名称: ", "Task name to delete: "))
    if raw_name is None:
        return
    task_name = _normalize_task_name(raw_name)
    spinner_delay(1.0, tr("正在删除任务", "Deleting task"))
    args = ["schtasks", "/Delete", "/TN", task_name, "/F"]
    result = run(args, capture=True, shell=False)
    if result.returncode == 0:
        short_name = _denormalize_task_name(task_name)
        print_ok(tr(f"任务 {short_name} 已删除", f"Task deleted: {short_name}"), use_color=True)
        return
    print_error(_format_schtasks_error(result), use_color=True)


def get_menu_title():
    return tr("\n====== Windows 自启动管理 ======", "\n====== Windows Autostart ======")


def get_actions():
    return [
        ("add", tr("新增自启动任务", "Add autostart task"), add_startup_task),
        ("query", tr("查询自启动任务", "List tasks"), query_startup_task),
        ("delete", tr("删除自启动任务", "Delete task"), delete_startup_task),
        ("update", tr("修改自启动任务", "Update task"), update_startup_task),
    ]


if __name__ == "__main__":
    from . import main

    main.main()
