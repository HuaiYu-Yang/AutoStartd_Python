import os
import platform
import sys

from . import linux, windows


def _normalize_path(path_value):
    return os.path.expanduser(path_value)


def set_autostart(name, script_path, overwrite=True, script_type=None, sudo_password=None):
    """Create or update an autostart entry for the current OS."""
    system = platform.system().lower()
    if system == "windows":
        return _set_autostart_windows(name, script_path, overwrite)
    if system == "linux":
        return _set_autostart_linux(name, script_path, overwrite, script_type, sudo_password)
    raise RuntimeError(f"Unsupported OS: {system}")


def remove_autostart(name, sudo_password=None):
    """Remove an autostart entry by name for the current OS."""
    system = platform.system().lower()
    if system == "windows":
        return _remove_autostart_windows(name)
    if system == "linux":
        return _remove_autostart_linux(name, sudo_password)
    raise RuntimeError(f"Unsupported OS: {system}")


def list_autostart(keyword=None, sudo_password=None):
    """List autostart entries for the current OS. Returns a list of names."""
    system = platform.system().lower()
    if system == "windows":
        return _list_autostart_windows(keyword)
    if system == "linux":
        return _list_autostart_linux(keyword, sudo_password)
    raise RuntimeError(f"Unsupported OS: {system}")


def _set_autostart_windows(name, script_path, overwrite):
    if not name:
        raise ValueError("name is required")
    if not script_path:
        raise ValueError("script_path is required")

    task_name = windows._normalize_task_name(name)
    if windows._task_exists(task_name) and not overwrite:
        raise RuntimeError("Task already exists")

    script_path = _normalize_path(script_path)
    python_exe = sys.executable
    task_cmd = f'"{python_exe}" "{script_path}"'

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
    ]
    if overwrite:
        args.append("/F")

    result = windows.run(args, capture=True, shell=False)
    if result.returncode != 0:
        raise RuntimeError(windows._format_schtasks_error(result))
    return True


def _remove_autostart_windows(name):
    if not name:
        raise ValueError("name is required")
    task_name = windows._normalize_task_name(name)
    args = ["schtasks", "/Delete", "/TN", task_name, "/F"]
    result = windows.run(args, capture=True, shell=False)
    if result.returncode != 0:
        raise RuntimeError(windows._format_schtasks_error(result))
    return True


def _extract_task_name(block):
    for line in block.splitlines():
        line_strip = line.strip()
        if line_strip.startswith("任务名:") or line_strip.lower().startswith("taskname:"):
            _, value = line.split(":", 1)
            value = value.strip()
            if value.startswith("\"):
                value = value[1:]
            return windows._denormalize_task_name(value)
    return None


def _list_autostart_windows(keyword):
    args = ["schtasks", "/Query", "/FO", "LIST", "/V"]
    result = windows.run(args, capture=True, shell=False)
    if result.returncode != 0:
        raise RuntimeError(windows._format_schtasks_error(result))

    output = result.stdout.strip()
    output = windows._filter_our_tasks(output)
    output = windows._filter_tasks_by_keyword(output, keyword)

    names = []
    for block in output.split("

"):
        block = block.strip()
        if not block:
            continue
        name = _extract_task_name(block)
        if name:
            names.append(name)
    return names


def _get_sudo_password(sudo_password):
    if sudo_password is None:
        raise RuntimeError("sudo_password is required for Linux API calls")
    return sudo_password


def _set_autostart_linux(name, script_path, overwrite, script_type, sudo_password):
    if not name:
        raise ValueError("name is required")
    if not script_path:
        raise ValueError("script_path is required")

    password = _get_sudo_password(sudo_password)
    if not linux.ensure_supervisor_once(password):
        raise RuntimeError("Supervisor not available")

    script_path = _normalize_path(script_path)
    if script_type is None:
        script_type = "python" if script_path.endswith(".py") else "ros"

    if linux._supervisor_conf_exists(name, password) and not overwrite:
        raise RuntimeError("Project already exists")

    conf_path = linux.generate_supervisor_conf(name, script_path, script_type)
    if not conf_path:
        raise RuntimeError("Failed to generate supervisor config")

    linux.sudo_run(f"mv {conf_path} {linux._supervisor_conf_path(name)}", password)
    linux.sudo_run("supervisorctl reread", password)
    linux.sudo_run("supervisorctl update", password)
    return True


def _remove_autostart_linux(name, sudo_password):
    if not name:
        raise ValueError("name is required")

    password = _get_sudo_password(sudo_password)
    if not linux.ensure_supervisor_once(password):
        raise RuntimeError("Supervisor not available")

    linux.sudo_run(f"rm -f {linux._supervisor_conf_path(name)}", password)
    linux.sudo_run("supervisorctl reread", password)
    linux.sudo_run("supervisorctl update", password)
    return True


def _list_autostart_linux(keyword, sudo_password):
    password = _get_sudo_password(sudo_password)
    if not linux.ensure_supervisor_once(password):
        raise RuntimeError("Supervisor not available")

    result = linux.sudo_run("supervisorctl status", password)
    if result.returncode != 0:
        raise RuntimeError("Failed to query supervisorctl")

    names = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        name = line.split()[0]
        if keyword and keyword.lower() not in name.lower():
            continue
        names.append(name)
    return names
