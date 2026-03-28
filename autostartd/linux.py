#!/usr/bin/env python3
import os
import subprocess
import getpass
import time

from .main import (
    get_python_executable,
    input_nonempty,
    print_error,
    print_info,
    print_ok,
    run,
    safe_input,
    safe_print,
    spinner_delay,
    tr,
)

# ----------------- 工具函数 -----------------

def safe_getpass(prompt):
    try:
        return getpass.getpass(prompt)
    except UnicodeEncodeError:
        safe_print(prompt, end="")
        return getpass.getpass("")

def sudo_run(cmd, password=None):
    """运行sudo命令，自动传递密码"""
    if password is None:
        password = safe_getpass(tr("请输入 sudo 密码: ", "sudo password: "))
    full_cmd = f'echo {password} | sudo -S {cmd}'
    result = run(full_cmd)
    if result.returncode != 0:
        print_error(result.stderr.strip())
    return result


def _read_os_release():
    try:
        with open("/etc/os-release", "r", encoding="utf-8") as f:
            return f.read().lower()
    except Exception:
        return ""


def _detect_pkg_manager():
    os_release = _read_os_release()
    if os.path.exists("/usr/bin/apt-get") or "ubuntu" in os_release or "debian" in os_release:
        return "apt"
    if os.path.exists("/usr/bin/dnf"):
        return "dnf"
    if os.path.exists("/usr/bin/yum") or "centos" in os_release or "rhel" in os_release:
        return "yum"
    return None


def _supervisor_installed():
    result = run("command -v supervisorctl")
    return result.returncode == 0


_SUPERVISOR_CHECKED = False
_SUPERVISOR_AVAILABLE = False


def ensure_supervisor_once(password):
    global _SUPERVISOR_CHECKED, _SUPERVISOR_AVAILABLE
    if _SUPERVISOR_CHECKED:
        return _SUPERVISOR_AVAILABLE

    _SUPERVISOR_CHECKED = True
    if _supervisor_installed():
        _SUPERVISOR_AVAILABLE = True
        return True

    print_info(tr("正在安装依赖...", "Installing dependencies..."), use_color=True)
    pkg = _detect_pkg_manager()
    if pkg == "apt":
        sudo_run("apt-get update -y", password)
        install_result = sudo_run("apt-get install -y supervisor", password)
    elif pkg == "dnf":
        install_result = sudo_run("dnf install -y supervisor", password)
    elif pkg == "yum":
        install_result = sudo_run("yum install -y supervisor", password)
    else:
        print_error(tr("无法识别包管理器，请手动安装 supervisor", "Unknown package manager, install supervisor manually"), use_color=True)
        _SUPERVISOR_AVAILABLE = False
        return False

    if install_result.returncode != 0:
        print_error(tr("安装 supervisor 失败", "Failed to install supervisor"), use_color=True)
        _SUPERVISOR_AVAILABLE = False
        return False

    sudo_run("mkdir -p /etc/supervisor/conf.d", password)
    sudo_run("systemctl enable --now supervisor", password)
    sudo_run("systemctl enable --now supervisord", password)
    _SUPERVISOR_AVAILABLE = _supervisor_installed()
    return _SUPERVISOR_AVAILABLE


def _supervisor_conf_path(project_name):
    return f"/etc/supervisor/conf.d/{project_name}.conf"


def _supervisor_conf_exists(project_name, password):
    result = sudo_run(f"test -f {_supervisor_conf_path(project_name)}", password)
    return result.returncode == 0


def _resolve_project_name_for_create(project_name, password):
    if project_name is None:
        return None
    if not _supervisor_conf_exists(project_name, password):
        return project_name

    while True:
        safe_print(tr("项目已存在，请选择操作:", "Project exists. Choose action:"))
        safe_print(tr("1) 覆盖", "1) Overwrite"))
        safe_print(tr("2) 重命名", "2) Rename"))
        choice = safe_input(tr("请输入数字选择: ", "Select option: ")).strip()
        if choice.lower() == "q":
            return None
        if choice == "1":
            return project_name
        if choice == "2":
            new_name = input_nonempty(tr("请输入新的项目名称: ", "New project name: "))
            if new_name is None:
                return None
            if _supervisor_conf_exists(new_name, password):
                print_error(tr("名称已存在，请换一个", "Name already exists"), use_color=True)
                continue
            return new_name
        print_error(tr("无效选择，请重新输入", "Invalid choice, please try again"), use_color=True)

# ----------------- Supervisor 操作 -----------------
def generate_supervisor_conf(project_name, script_path, script_type):
    script_path = os.path.expanduser(script_path)
    log_dir = f"/home/{getpass.getuser()}/logs/{project_name}"
    os.makedirs(log_dir, exist_ok=True)
    conf_path = f"/tmp/{project_name}.conf"
    python_exe = get_python_executable()

    if script_type == "python":
        conf_content = f"""[program:{project_name}]
command={python_exe} {script_path}
directory=/home/{getpass.getuser()}
autostart=true
autorestart=true
startsecs=3
stdout_logfile={log_dir}/{project_name}.out.log
stderr_logfile={log_dir}/{project_name}.err.log
user={getpass.getuser()}"""
    elif script_type == "ros":
        conf_content = f"""[program:{project_name}]
command=/bin/bash {script_path}
autostart=true
autorestart=true
startsecs=3
stdout_logfile={log_dir}/{project_name}.out.log
stderr_logfile={log_dir}/{project_name}.err.log
user={getpass.getuser()}"""
    else:
        print_error(tr("不支持的脚本类型", "Unsupported script type"), use_color=True)
        return None

    with open(conf_path, "w") as f:
        f.write(conf_content)
    print_ok(tr(f"Supervisor 配置生成完成: {conf_path}", f"Config generated: {conf_path}"), use_color=True)
    return conf_path

def add_supervisor_project():
    project_name = input_nonempty(tr("请输入项目名称: ", "Project name: "))
    script_path = input_nonempty(tr("请输入需要自启动的脚本路径: ", "Script path: "))
    if project_name is None or script_path is None:
        return
    script_path = os.path.expanduser(script_path)
    script_type = "python" if script_path.endswith(".py") else "ros"

    password = safe_getpass(tr("请输入 sudo 密码，用于部署 Supervisor 配置: ", "sudo password for Supervisor: "))
    if not ensure_supervisor_once(password):
        return
    project_name = _resolve_project_name_for_create(project_name, password)
    if project_name is None:
        return
    conf_path = generate_supervisor_conf(project_name, script_path, script_type)

    # mv 配置文件
    spinner_delay(1.2, tr("正在写入配置", "Writing config"))
    sudo_run(f"mv {conf_path} {_supervisor_conf_path(project_name)}", password)
    sudo_run("supervisorctl reread", password)
    sudo_run("supervisorctl update", password)
    print_info(tr("等待 Supervisor 启动...", "Waiting for Supervisor..."), use_color=True)
    time.sleep(2)
    result = sudo_run("supervisorctl status", password)
    if result.stdout:
        print_ok(result.stdout.strip())

def query_supervisor_projects():
    keyword = safe_input(tr("请输入项目名称关键字 (留空查询全部): ", "Keyword (empty for all): ")).strip()
    if keyword.lower() == "q":
        return
    password = safe_getpass(tr("请输入 sudo 密码，用于查询 Supervisor 项目: ", "sudo password for query: "))
    if not ensure_supervisor_once(password):
        return
    result = sudo_run("supervisorctl status", password)
    if result.stdout:
        lines = [line for line in result.stdout.splitlines() if line.strip()]
        if keyword:
            lines = [line for line in lines if keyword.lower() in line.lower()]
        if lines:
            print_ok("\n".join(lines))
        else:
            print_info(tr("未找到匹配的项目", "No matching projects"), use_color=True)

def delete_supervisor_project():
    project_name = input_nonempty(tr("请输入要删除的 Supervisor 项目名称: ", "Project name to delete: "))
    if project_name is None:
        return
    password = safe_getpass(tr("请输入 sudo 密码，用于删除 Supervisor 项目: ", "sudo password for delete: "))
    if not ensure_supervisor_once(password):
        return

    spinner_delay(1.0, tr("正在删除配置", "Deleting config"))
    sudo_run(f"rm -f /etc/supervisor/conf.d/{project_name}.conf", password)
    sudo_run("supervisorctl reread", password)
    sudo_run("supervisorctl update", password)
    print_ok(tr(f"项目 {project_name} 已删除", f"Project deleted: {project_name}"), use_color=True)

# ----------------- pip工具运行 -----------------
def install_and_run_pyre():
    script_path = input_nonempty(tr("请输入目标脚本绝对路径: ", "Absolute script path: "))
    if script_path is None:
        return
    print_info(tr("安装 pyre_tools...", "Installing pyre_tools..."), use_color=True)
    python_cmd = get_python_executable()
    subprocess.run([python_cmd, "-m", "pip", "install", "--upgrade", "pyre-tools"], check=False)

    print_info(tr(f"开始分析文件: {script_path}", f"Analyzing file: {script_path}"), use_color=True)
    process = subprocess.Popen(
        [python_cmd, "-m", "pyre", script_path],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        stdin=subprocess.PIPE,
        text=True
    )

    try:
        # 实时输出
        for line in process.stdout:
            safe_print(line, end="")  # 逐行打印
            if "是否现在通过 pip 安装缺失依赖" in line:
                answer = safe_input(tr("请输入 y/n 选择: ", "Enter y/n: ")).strip().lower()
                process.stdin.write(answer + "\n")
                process.stdin.flush()
        process.wait()
    except KeyboardInterrupt:
        process.terminate()
        print_error(tr("用户中断", "Interrupted"), use_color=True)



def get_menu_title():
    return tr("\n====== Supervisor 管理菜单 ======", "\n====== Supervisor Menu ======")


def get_actions():
    return [
        ("add", tr("新增自启动项目", "Add autostart"), add_supervisor_project),
        ("query", tr("查询自启动项目", "List autostart"), query_supervisor_projects),
        ("delete", tr("删除自启动项目", "Delete autostart"), delete_supervisor_project),
        ("pyre", tr("运行 pyre_tools", "Run pyre_tools"), install_and_run_pyre),
    ]
if __name__ == "__main__":
    from . import main

    main.main()
