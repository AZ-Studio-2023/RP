from flask import Flask, request, render_template, jsonify, redirect, url_for, send_from_directory
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user
from flask_socketio import SocketIO, emit
import subprocess
import threading
import os
import zipfile
import schedule
import time
import uuid

app = Flask(__name__)
app.secret_key = 'your_secret_key'
socketio = SocketIO(app)

# 设置项目和打包结果的保存位置
BASE_DIR = '/path/to/base/dir'
REPO_DIR = os.path.join(BASE_DIR, 'repo')
OUTPUT_DIR = os.path.join(BASE_DIR, 'output')

# 确保目录存在
os.makedirs(REPO_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# 用户模型
class User(UserMixin):
    def __init__(self, id):
        self.id = id

# 用户表
users = {'admin': {'password': 'admin'}}

@login_manager.user_loader
def load_user(user_id):
    return User(user_id)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if username in users and users[username]['password'] == password:
            user = User(username)
            login_user(user)
            return redirect(url_for('index'))
        else:
            return '登录失败'
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/', methods=['GET', 'POST'])
@login_required
def index():
    if request.method == 'POST':
        # 处理表单数据
        git_url = request.form['git_url']
        main_file = request.form['main_file']
        single_file = request.form.get('single_file', False)
        no_console = request.form.get('no_console', False)
        icon_path = request.form.get('icon_path', None)
        requirements_path = request.form.get('requirements_path', None)
        resource_folder = request.form.get('resource_folder', None)
        plugins = request.form.get('plugins', None)
        windows_file_description = request.form.get('windows_file_description', None)
        windows_file_version = request.form.get('windows_file_version', None)
        windows_product_version = request.form.get('windows_product_version', None)
        windows_product_name = request.form.get('windows_product_name', None)
        windows_company_name = request.form.get('windows_company_name', None)
        include_package = request.form.get('include_package', None)
        include_module = request.form.get('include_module', None)
        custom_args = request.form.get('custom_args', None)
        
        # 启动打包线程
        threading.Thread(target=package_project, args=(git_url, main_file, single_file, no_console, icon_path, requirements_path, resource_folder, plugins, windows_file_description, windows_file_version, windows_product_version, windows_product_name, windows_company_name, include_package, include_module, custom_args)).start()
        return jsonify({"message": "打包开始"})
    return render_template('index.html')

def package_project(git_url, main_file, single_file, no_console, icon_path, requirements_path, resource_folder, plugins, windows_file_description, windows_file_version, windows_product_version, windows_product_name, windows_company_name, include_package, include_module, custom_args):
    # 解析自定义参数
    custom_args_list = custom_args.split(',') if custom_args else []
    # 构建 Nuitka 命令
    nuitka_cmd = "nuitka --standalone"
    if single_file:
        nuitka_cmd += " --onefile"
    nuitka_cmd += " --output-dir=dist"
    if no_console:
        nuitka_cmd += " --windows-console-mode=disable"
    if icon_path:
        nuitka_cmd += f" --windows-icon-from-ico={icon_path}"
    if windows_file_description:
        nuitka_cmd += f' --windows-file-description="{windows_file_description}"'
    if windows_file_version:
        nuitka_cmd += f' --windows-file-version="{windows_file_version}"'
    if windows_product_version:
        nuitka_cmd += f' --windows-product-version="{windows_product_version}"'
    if windows_product_name:
        nuitka_cmd += f' --windows-product-name="{windows_product_name}"'
    if windows_company_name:
        nuitka_cmd += f' --windows-company-name="{windows_company_name}"'
    if plugins:
        nuitka_cmd += f"--plugin-enable={plugins}"
    for package in include_package.split(','):
        if package:
            nuitka_cmd += f" --include-package={package}"
    for module in include_module.split(','):
        if module:
            nuitka_cmd += f" --include-module={module}"
    # 添加自定义参数
    for arg in custom_args_list:
        nuitka_cmd += f" {arg}"
    nuitka_cmd += f" {main_file}"
    # 执行命令
    unique_id = str(uuid.uuid4())
    project_path = os.path.join(REPO_DIR, unique_id)
    output_path = os.path.join(OUTPUT_DIR, f"{unique_id}.zip")

    os.system(f"git clone {git_url} {project_path}")
    os.chdir(project_path)
    if requirements_path:
        os.system(f"pip install -r {requirements_path}")
    print(nuitka_cmd)
    proc = subprocess.Popen(nuitka_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    while True:
        output = proc.stdout.readline()
        if output == b'':  # Check for binary empty string
            if proc.poll() is not None:
                break
        else:
            # Decode with 'ignore' to handle undecodable bytes
            decoded_output = output.decode('utf-8', 'ignore')
            socketio.emit('output', {'data': decoded_output}, namespace='/test')
    proc.wait()
    with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk('dist'):
            for file in files:
                zipf.write(os.path.join(root, file))
    os.chdir("..")
    os.system(f"rm -rf {project_path}")
    socketio.emit('done', {'url': f'/download/{unique_id}.zip'}, namespace='/test')

@app.route('/download/<path:filename>', methods=['GET'])
def download(filename):
    return send_from_directory(directory=OUTPUT_DIR, filename=filename, as_attachment=True)

def clear_files():
    if os.path.exists('project.zip'):
        os.remove('project.zip')
    if os.path.exists('project'):
        os.system('rm -rf project')

schedule.every().friday.do(clear_files)

def run_scheduler():
    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == '__main__':
    # 启动定时任务线程
    threading.Thread(target=run_scheduler).start()
    socketio.run(app, port=5000, debug=True) 