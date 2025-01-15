from flask import Flask, request, render_template, jsonify, redirect, url_for, send_from_directory
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user
import subprocess
import threading
import os
import zipfile
import schedule
import time
import uuid
import shutil
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

app = Flask(__name__)
app.secret_key = 'your_secret_key'

# 设置项目和打包结果的保存位置
BASE_DIR = '/path/to/base/dir'
REPO_DIR = os.path.join(BASE_DIR, 'repo')
OUTPUT_DIR = os.path.join(BASE_DIR, 'output')
from_email = "noreply@azteam.cn"
from_password = "Zlk939067"

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
        email = request.form['email']
        single_file = request.form.get('single_file', False)
        if single_file == "false":
            single_file = False
        else:
            single_file = True
        no_console = request.form.get('no_console', False)
        if no_console == "false":
            no_console = False
        else:
            no_console = True
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
        threading.Thread(target=package_project, args=(git_url, main_file, email, single_file, no_console, icon_path, requirements_path, resource_folder, plugins, windows_file_description, windows_file_version, windows_product_version, windows_product_name, windows_company_name, include_package, include_module, custom_args)).start()
        return jsonify({"message": "打包开始"})
    return render_template('index.html')

def package_project(git_url, main_file, email, single_file, no_console, icon_path, requirements_path, resource_folder, plugins, windows_file_description, windows_file_version, windows_product_version, windows_product_name, windows_company_name, include_package, include_module, custom_args):
    unique_id = str(uuid.uuid4())
    project_path = os.path.join(REPO_DIR, unique_id)
    output_path = os.path.join(OUTPUT_DIR, f"{unique_id}.zip")

    # Clone the repository
    git_clone_cmd = f"git clone {git_url} {project_path}"
    proc = subprocess.Popen(git_clone_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    proc.wait()

    if proc.returncode != 0:
        print('Git clone failed.')
        return

    os.chdir(project_path)
    if requirements_path:
        pip_install_cmd = f"pip install -r {requirements_path}"
        proc = subprocess.Popen(pip_install_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        proc.wait()

    # Build the Nuitka command
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
        nuitka_cmd += f" --plugin-enable={plugins}"
    for package in include_package.split(','):
        if package:
            nuitka_cmd += f" --include-package={package}"
    for module in include_module.split(','):
        if module:
            nuitka_cmd += f" --include-module={module}"
    for arg in custom_args.split(','):
        if arg:
            nuitka_cmd += f" {arg}"
    nuitka_cmd += f" {main_file}"

    # Execute the Nuitka command
    proc = subprocess.Popen(nuitka_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    proc.wait()

    if proc.returncode == 0:
        with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk('dist'):
                for file in files:
                    zipf.write(os.path.join(root, file))
        send_email(email, f'http://admin.v6.server.tjmtr.world:5000/download/{unique_id}.zip', unique_id)
    else:
        print('Nuitka build failed.')

    os.chdir("..")
    
def send_email(to_email, download_link, unique_id):
    global from_email, from_password
    subject = f"打包任务完成通知"
    body = f"你的打包任务({unique_id})已完成。 你可以通过这个链接下载: {download_link}"

    msg = MIMEMultipart()
    msg['From'] = from_email
    msg['To'] = to_email
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain'))

    try:
        server = smtplib.SMTP('smtp.office365.com', 587)
        server.starttls()
        server.login(from_email, from_password)
        server.sendmail(from_email, to_email, msg.as_string())
        server.quit()
        print(f"Email sent to {to_email}")
    except Exception as e:
        print(f"Failed to send email. Error: {e}")

@app.route('/download/<path:filename>', methods=['GET'])
def download(filename):
    try:
        return send_from_directory(OUTPUT_DIR, filename, as_attachment=True)
    except Exception as e:
        print(f"Error sending file: {e}")
        return "File not found", 404

def clear_files():
    # 清除 OUTPUT_DIR 中的所有文件
    for filename in os.listdir(OUTPUT_DIR):
        file_path = os.path.join(OUTPUT_DIR, filename)
        try:
            if os.path.isfile(file_path) or os.path.islink(file_path):
                os.unlink(file_path)  # 删除文件或符号链接
            elif os.path.isdir(file_path):
                shutil.rmtree(file_path)  # 删除目录及其内容
        except Exception as e:
            print(f'Failed to delete {file_path}. Reason: {e}')

    # 清除 REPO_DIR 中的所有文件
    for filename in os.listdir(REPO_DIR):
        file_path = os.path.join(REPO_DIR, filename)
        try:
            if os.path.isfile(file_path) or os.path.islink(file_path):
                os.unlink(file_path)
            elif os.path.isdir(file_path):
                shutil.rmtree(file_path)
        except Exception as e:
            print(f'Failed to delete {file_path}. Reason: {e}')

schedule.every().friday.do(clear_files)

def run_scheduler():
    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == '__main__':
    # 启动定时任务线程
    threading.Thread(target=run_scheduler).start()
    app.run(host='0.0.0.0', port=5000, debug=True) 