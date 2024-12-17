import sys
import os
import time
import pandas as pd
import threading
from datetime import datetime
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from plyer import notification
from sklearn.linear_model import LinearRegression
import numpy as np
import sqlite3
from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QLineEdit, QPushButton,
    QVBoxLayout, QHBoxLayout, QMessageBox, QTabWidget, QTableWidget,
    QTableWidgetItem, QFileDialog, QColorDialog, QComboBox
)
from PyQt5.QtGui import QFont
import logging

# ==================== 配置部分 ====================
ROOT_DIR = r'D:\课件\学科ppt'  # 根目录
CHECK_INTERVAL = 2  # 文件检查间隔（秒）
LEARNING_THRESHOLD = 0.01  # 最小学习时长（分钟）
INACTIVITY_THRESHOLD = 300 # 不活动超时时间（秒），设置为5分钟
SUPPORTED_EXTENSIONS = ['.pdf', '.docx', '.pptx']  # 支持的文件类型

# 通知配置
NOTIFICATION_TITLE = "学习进度提醒"
NOTIFICATION_DURATION = 5  # 通知持续时间（秒）

# 数据库配置
DB_PATH = 'study_tracker.db'

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("study_tracker.log", encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)


# ==================== 数据库初始化 ====================
def initialize_database():
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        # 创建用户表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                email TEXT,
                theme TEXT DEFAULT 'Light'
            )
        ''')
        # 创建学习日志表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS study_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                filename TEXT,
                subject TEXT,
                duration REAL,
                status TEXT,
                start_time TEXT,
                end_time TEXT,
                date TEXT,
                week TEXT,
                month TEXT,
                last_access_time TEXT,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
        ''')
        # 创建通知设置表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                reminder_type TEXT,
                enabled INTEGER,
                time TEXT,
                frequency TEXT,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
        ''')
        conn.commit()
        logging.info("数据库初始化完成。")
    except Exception as e:
        logging.error(f"数据库初始化失败: {e}")
    finally:
        conn.close()


# ==================== 用户管理功能 ====================
def register_user(username, email):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('INSERT INTO users (username, email) VALUES (?, ?)', (username, email))
        conn.commit()
        user_id = cursor.lastrowid
        logging.info(f"用户注册成功: {username}")
    except sqlite3.IntegrityError:
        user_id = None
        logging.warning(f"注册失败，用户名已存在: {username}")
    except Exception as e:
        user_id = None
        logging.error(f"注册用户时出错: {e}")
    finally:
        conn.close()
    return user_id


def login_user(username):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('SELECT id, theme FROM users WHERE username = ?', (username,))
        result = cursor.fetchone()
        conn.close()
        if result:
            logging.info(f"用户登录成功: {username}")
            return {'id': result[0], 'username': username, 'theme': result[1]}
        else:
            logging.warning(f"用户登录失败，用户不存在: {username}")
            return None
    except Exception as e:
        logging.error(f"登录用户时出错: {e}")
        return None


# ==================== 学习时长跟踪 ====================
class StudyTracker(threading.Thread):
    def __init__(self, user_id, stop_event, notify_callback, log_callback):
        super().__init__()
        self.user_id = user_id
        self.stop_event = stop_event
        self.notify_callback = notify_callback
        self.log_callback = log_callback
        self.active_sessions = {}
        self.active_sessions_lock = threading.Lock()
        self.all_files = self.get_all_supported_files()

    def get_all_supported_files(self):
        supported_files = {}
        for root, _, files in os.walk(ROOT_DIR):
            for file in files:
                if any(file.endswith(ext) for ext in SUPPORTED_EXTENSIONS):
                    file_path = os.path.join(root, file)
                    try:
                        supported_files[file_path] = os.path.getatime(file_path)
                    except FileNotFoundError:
                        continue
        return supported_files

    def run(self):
        logging.info("学习时长跟踪线程启动")
        while not self.stop_event.is_set():
            try:
                current_time = time.time()
                current_files = self.get_all_supported_files()

                # 检测文件波动
                for file, last_atime in current_files.items():
                    current_atime = os.path.getatime(file)
                    if file not in self.all_files:
                        # 新文件被添加
                        self.all_files[file] = current_atime
                        logging.info(f"检测到新文件: {file}")

                    if current_atime != self.all_files[file]:
                        with self.active_sessions_lock:
                            if file not in self.active_sessions:
                                # 新的学习会话开始
                                self.active_sessions[file] = {
                                    "start_time": current_time,
                                    "last_fluctuation": current_time
                                }
                                self.notify_callback(
                                    "开始学习",
                                    f"开始学习: {os.path.basename(file)}"
                                )
                                self.log_callback(f"开始学习: {file} at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                                logging.info(f"🟢 开始学习: {file} 于 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                            else:
                                # 更新最后一次波动时间
                                self.active_sessions[file]["last_fluctuation"] = current_time
                        self.all_files[file] = current_atime

                # 检测不活动超时
                with self.active_sessions_lock:
                    files_to_remove = []
                    for file, times in self.active_sessions.items():
                        last_fluctuation = times["last_fluctuation"]
                        if current_time - last_fluctuation > INACTIVITY_THRESHOLD:
                            duration = (last_fluctuation - times["start_time"]) / 60  # 转换为分钟
                            if duration >= LEARNING_THRESHOLD:
                                self.log_study_time(file, times["start_time"], last_fluctuation)
                                self.notify_callback(
                                    "停止学习",
                                    f"停止学习: {os.path.basename(file)}，时长 {duration:.2f} 分钟"
                                )
                                self.log_callback(f"停止学习: {file} at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                                logging.info(
                                    f"🛑 停止学习: {file} -> {duration:.2f} 分钟 于 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                            files_to_remove.append(file)
                    for file in files_to_remove:
                        del self.active_sessions[file]

                # 更新 all_files 字典，移除已删除的文件
                removed_files = set(self.all_files.keys()) - set(current_files.keys())
                for file in removed_files:
                    with self.active_sessions_lock:
                        if file in self.active_sessions:
                            times = self.active_sessions[file]
                            duration = (times["last_fluctuation"] - times["start_time"]) / 60
                            if duration >= LEARNING_THRESHOLD:
                                self.log_study_time(file, times["start_time"], times["last_fluctuation"])
                                self.notify_callback(
                                    "停止学习",
                                    f"文件被删除或移动: {os.path.basename(file)}，时长 {duration:.2f} 分钟"
                                )
                                self.log_callback(
                                    f"文件被删除或移动: {file} at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                                logging.info(
                                    f"🛑 文件被删除或移动: {file} -> {duration:.2f} 分钟 于 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                            del self.active_sessions[file]
                    del self.all_files[file]

            except Exception as e:
                logging.error(f"跟踪线程错误: {e}")
            time.sleep(CHECK_INTERVAL)
        logging.info("学习时长跟踪线程停止")

    def log_study_time(self, file_path, start_time, end_time):
        duration = (end_time - start_time) / 60  # 转换为分钟
        filename = os.path.basename(file_path)
        subject = file_path.split(os.sep)[-2] if len(file_path.split(os.sep)) >= 2 else "未知"
        now = datetime.now()
        date = now.strftime("%Y-%m-%d")
        week = now.strftime("%U")
        month = now.strftime("%Y-%m")
        start_datetime = datetime.fromtimestamp(start_time).strftime("%Y-%m-%d %H:%M:%S")
        end_datetime = datetime.fromtimestamp(end_time).strftime("%Y-%m-%d %H:%M:%S")

        status = "已完成" if duration >= 15 else "进行中"

        try:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO study_logs (
                    user_id, filename, subject, duration, status,
                    start_time, end_time, date, week, month, last_access_time
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                self.user_id, filename, subject, round(duration, 2), status,
                start_datetime, end_datetime, date, week, month,
                now.strftime("%Y-%m-%d %H:%M:%S")
            ))
            conn.commit()
            logging.info(f"学习时长记录: {filename}, 时长: {duration:.2f} 分钟")
        except Exception as e:
            logging.error(f"记录学习时长时出错: {e}")
        finally:
            conn.close()


# ==================== 主GUI类 ====================
class StudyTrackerApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("学习进度跟踪系统")
        self.setGeometry(100, 100, 1000, 700)
        self.current_user = None
        self.tracker = None
        self.stop_event = threading.Event()
        self.chart_refresh_timer = QtCore.QTimer()

        self.initUI()

    def initUI(self):
        self.stack = QtWidgets.QStackedWidget()
        self.setCentralWidget(self.stack)

        self.login_widget = self.create_login_widget()
        self.stack.addWidget(self.login_widget)

    def create_login_widget(self):
        widget = QWidget()
        layout = QVBoxLayout()

        title = QLabel("学习进度跟踪系统")
        title.setFont(QFont("Arial", 20))
        title.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(title)

        form_layout = QVBoxLayout()

        username_label = QLabel("用户名:")
        self.username_input = QLineEdit()
        form_layout.addWidget(username_label)
        form_layout.addWidget(self.username_input)

        email_label = QLabel("电子邮件 (注册时需填写):")
        self.email_input = QLineEdit()
        form_layout.addWidget(email_label)
        form_layout.addWidget(self.email_input)

        layout.addLayout(form_layout)

        button_layout = QHBoxLayout()
        login_btn = QPushButton("登录")
        login_btn.clicked.connect(self.login)
        register_btn = QPushButton("注册")
        register_btn.clicked.connect(self.register)
        button_layout.addWidget(login_btn)
        button_layout.addWidget(register_btn)
        layout.addLayout(button_layout)

        widget.setLayout(layout)
        return widget

    def login(self):
        username = self.username_input.text().strip()
        if not username:
            QMessageBox.warning(self, "错误", "用户名不能为空！")
            return
        user = login_user(username)
        if user:
            self.current_user = user
            self.start_tracker()
            self.create_main_menu()
        else:
            QMessageBox.warning(self, "错误", "用户不存在，请注册！")

    def register(self):
        username = self.username_input.text().strip()
        email = self.email_input.text().strip()
        if not username or not email:
            QMessageBox.warning(self, "错误", "用户名和电子邮件不能为空！")
            return
        user_id = register_user(username, email)
        if user_id:
            QMessageBox.information(self, "成功", "注册成功！请登录。")
        else:
            QMessageBox.warning(self, "错误", "用户名已存在！")

    def create_main_menu(self):
        self.main_menu_widget = QWidget()
        layout = QVBoxLayout()

        welcome_label = QLabel(f"欢迎, {self.current_user['username']}")
        welcome_label.setFont(QFont("Arial", 16))
        welcome_label.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(welcome_label)

        tabs = QTabWidget()
        tabs.setStyleSheet("""
            QTabWidget::pane { 
                border-top: 2px solid #C2C7CB; 
            }
            QTabBar::tab {
                background: #f0f0f0;
                padding: 10px;
                margin: 2px;
                border-radius: 4px;
            }
            QTabBar::tab:selected { 
                background: #d0d0d0;
            }
        """)

        # 学习报告标签
        self.report_tab = self.create_report_tab()
        tabs.addTab(self.report_tab, "学习报告")

        # 活动会话标签
        self.active_sessions_tab = self.create_active_sessions_tab()
        tabs.addTab(self.active_sessions_tab, "当前活动会话")

        # 设置标签
        self.settings_tab = self.create_settings_tab()
        tabs.addTab(self.settings_tab, "设置")

        layout.addWidget(tabs)

        # 退出按钮
        exit_btn = QPushButton("退出程序")
        exit_btn.setStyleSheet("""
            QPushButton {
                background-color: #ff4d4d;
                color: white;
                padding: 10px;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #ff1a1a;
            }
        """)
        exit_btn.clicked.connect(self.exit_program)
        layout.addWidget(exit_btn)

        self.main_menu_widget.setLayout(layout)
        self.stack.addWidget(self.main_menu_widget)
        self.stack.setCurrentWidget(self.main_menu_widget)

        # 设置图表自动刷新定时器
        self.chart_refresh_timer.timeout.connect(self.refresh_charts)
        self.chart_refresh_timer.start(10000)  # 每10秒刷新一次

    def create_report_tab(self):
        widget = QWidget()
        layout = QVBoxLayout()

        # 按钮布局
        button_layout = QHBoxLayout()
        daily_btn = QPushButton("查看每日学科学习时长")
        daily_btn.clicked.connect(lambda: self.show_summary("date", "每日学科学习时长"))
        weekly_btn = QPushButton("查看每周学科学习时长")
        weekly_btn.clicked.connect(lambda: self.show_summary("week", "每周学科学习时长"))
        monthly_btn = QPushButton("查看每月学科学习时长")
        monthly_btn.clicked.connect(lambda: self.show_summary("month", "每月学科学习时长"))
        subject_btn = QPushButton("查看学科总学习时长分布")
        subject_btn.clicked.connect(lambda: self.show_subject_summary())
        export_btn = QPushButton("导出学习日志为Excel")
        export_btn.clicked.connect(self.export_log_to_excel)
        analyze_btn = QPushButton("数据分析与预测")
        analyze_btn.clicked.connect(self.analyze_and_predict)

        button_layout.addWidget(daily_btn)
        button_layout.addWidget(weekly_btn)
        button_layout.addWidget(monthly_btn)
        button_layout.addWidget(subject_btn)
        button_layout.addWidget(export_btn)
        button_layout.addWidget(analyze_btn)

        layout.addLayout(button_layout)

        # 图表显示区域
        self.chart_canvas = FigureCanvas(plt.Figure(figsize=(10, 6)))
        layout.addWidget(self.chart_canvas)

        widget.setLayout(layout)
        return widget

    def create_active_sessions_tab(self):
        widget = QWidget()
        layout = QVBoxLayout()

        self.active_sessions_table = QTableWidget()
        self.active_sessions_table.setColumnCount(2)
        self.active_sessions_table.setHorizontalHeaderLabels(["文件名", "已学习时长（分钟）"])
        self.active_sessions_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.active_sessions_table)

        refresh_btn = QPushButton("刷新")
        refresh_btn.clicked.connect(self.refresh_active_sessions)
        layout.addWidget(refresh_btn)

        # 设置定时器自动刷新
        self.refresh_timer = QtCore.QTimer()
        self.refresh_timer.timeout.connect(self.refresh_active_sessions)
        self.refresh_timer.start(5000)  # 每5秒刷新一次

        widget.setLayout(layout)
        return widget

    def create_settings_tab(self):
        widget = QWidget()
        layout = QVBoxLayout()

        # 主题设置
        theme_layout = QHBoxLayout()
        theme_label = QLabel("选择主题:")
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["Light", "Dark"])
        if self.current_user:
            self.theme_combo.setCurrentText(self.current_user.get('theme', 'Light'))
        self.theme_combo.currentTextChanged.connect(self.change_theme)
        theme_layout.addWidget(theme_label)
        theme_layout.addWidget(self.theme_combo)
        layout.addLayout(theme_layout)

        # 通知设置（简化为启用/禁用）
        notification_layout = QHBoxLayout()
        notif_label = QLabel("启用桌面通知:")
        self.notif_checkbox = QtWidgets.QCheckBox()
        self.notif_checkbox.setChecked(True)
        self.notif_checkbox.stateChanged.connect(self.toggle_notifications)
        notification_layout.addWidget(notif_label)
        notification_layout.addWidget(self.notif_checkbox)
        layout.addLayout(notification_layout)

        widget.setLayout(layout)
        return widget

    def change_theme(self, theme):
        if theme == "Dark":
            self.setStyleSheet("""
                QMainWindow {
                    background-color: #2E2E2E;
                    color: white;
                }
                QLabel, QPushButton, QLineEdit, QComboBox {
                    color: white;
                }
                QPushButton {
                    background-color: #555555;
                }
                QPushButton:hover {
                    background-color: #777777;
                }
            """)
        else:
            self.setStyleSheet("")
        # 更新用户主题到数据库
        try:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute('UPDATE users SET theme = ? WHERE id = ?', (theme, self.current_user['id']))
            conn.commit()
            conn.close()
            logging.info(f"用户 {self.current_user['username']} 切换到 {theme} 主题")
        except Exception as e:
            logging.error(f"更新用户主题时出错: {e}")

    def toggle_notifications(self, state):
        # 这里可以保存通知设置到数据库，暂时简化为启用/禁用全局通知
        if state == QtCore.Qt.Checked:
            logging.info("桌面通知已启用")
        else:
            logging.info("桌面通知已禁用")
        # 未来可以将状态保存到数据库

    def start_tracker(self):
        self.stop_event.clear()
        self.tracker = StudyTracker(
            user_id=self.current_user['id'],
            stop_event=self.stop_event,
            notify_callback=self.send_notification,
            log_callback=self.log_debug
        )
        self.tracker.start()
        logging.info("学习时长跟踪器已启动")

    def send_notification(self, title, message):
        try:
            notification.notify(
                title=title,
                message=message,
                timeout=NOTIFICATION_DURATION
            )
            logging.info(f"发送通知: {title} - {message}")
        except Exception as e:
            logging.error(f"发送通知失败: {e}")

    def log_debug(self, message):
        logging.info(message)

    def show_summary(self, group_by, title):
        try:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            query = f'''
                SELECT {group_by}, subject, SUM(duration)
                FROM study_logs
                WHERE user_id = ?
                GROUP BY {group_by}, subject
            '''
            cursor.execute(query, (self.current_user['id'],))
            results = cursor.fetchall()
            conn.close()

            if not results:
                QMessageBox.information(self, "提示", "没有找到学习记录！")
                return

            df = pd.DataFrame(results, columns=[group_by, 'subject', 'duration'])
            summary = df.pivot_table(index=group_by, columns='subject', values='duration', aggfunc='sum').fillna(0)

            # 清空之前的图表
            self.chart_canvas.figure.clf()
            ax = self.chart_canvas.figure.add_subplot(111)

            summary.plot(kind='bar', stacked=True, ax=ax)
            ax.set_title(title)
            ax.set_xlabel(group_by.capitalize())
            ax.set_ylabel("学习时长（分钟）")

            # 设置中文字体
            plt.rcParams['font.sans-serif'] = ['SimHei']  # 确保系统已安装SimHei字体
            plt.rcParams['axes.unicode_minus'] = False

            self.chart_canvas.draw()
            logging.info(f"显示学习报告: {title}")
        except Exception as e:
            logging.error(f"显示学习报告时出错: {e}")
            QMessageBox.warning(self, "错误", f"无法生成报告: {e}")

    def show_subject_summary(self):
        try:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            query = '''
                SELECT subject, SUM(duration)
                FROM study_logs
                WHERE user_id = ?
                GROUP BY subject
                ORDER BY SUM(duration) DESC
            '''
            cursor.execute(query, (self.current_user['id'],))
            results = cursor.fetchall()
            conn.close()

            if not results:
                QMessageBox.information(self, "提示", "没有找到学习记录！")
                return

            df = pd.DataFrame(results, columns=['subject', 'duration'])
            summary = df.set_index('subject')['duration']

            # 清空之前的图表
            self.chart_canvas.figure.clf()
            ax1 = self.chart_canvas.figure.add_subplot(121)
            ax2 = self.chart_canvas.figure.add_subplot(122)

            summary.plot(kind='bar', ax=ax1)
            ax1.set_title("学科学习时长分布")
            ax1.set_xlabel("学科")
            ax1.set_ylabel("学习时长（分钟）")

            summary.plot(kind='pie', autopct='%1.1f%%', ax=ax2, legend=False)
            ax2.set_title("学科学习时长占比")
            ax2.set_ylabel("")

            # 设置中文字体
            plt.rcParams['font.sans-serif'] = ['SimHei']
            plt.rcParams['axes.unicode_minus'] = False

            self.chart_canvas.draw()
            logging.info("显示学科学习时长分布")
        except Exception as e:
            logging.error(f"显示学科学习时长分布时出错: {e}")
            QMessageBox.warning(self, "错误", f"无法生成学科报告: {e}")

    def export_log_to_excel(self):
        try:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            query = '''
                SELECT filename, subject, duration, status, start_time, end_time, date, week, month, last_access_time
                FROM study_logs
                WHERE user_id = ?
            '''
            cursor.execute(query, (self.current_user['id'],))
            results = cursor.fetchall()
            conn.close()

            if not results:
                QMessageBox.information(self, "提示", "没有找到学习记录！")
                return

            df = pd.DataFrame(results, columns=[
                "文件名", "学科", "学习时长（分钟）", "状态",
                "开始时间", "结束时间", "日期", "周", "月",
                "最后访问时间"
            ])

            options = QFileDialog.Options()
            file_path, _ = QFileDialog.getSaveFileName(self, "保存学习日志为Excel", "",
                                                       "Excel Files (*.xlsx);;All Files (*)", options=options)
            if file_path:
                try:
                    # 设置中文字体
                    plt.rcParams['font.sans-serif'] = ['SimHei']
                    plt.rcParams['axes.unicode_minus'] = False
                    df.to_excel(file_path, index=False)
                    QMessageBox.information(self, "成功", f"学习日志已成功导出到 {file_path}")
                    logging.info(f"学习日志已成功导出到 {file_path}")
                except Exception as e:
                    QMessageBox.warning(self, "错误", f"导出失败: {e}")
                    logging.error(f"导出学习日志失败: {e}")
        except Exception as e:
            logging.error(f"导出学习日志时出错: {e}")
            QMessageBox.warning(self, "错误", f"无法导出学习日志: {e}")

    def analyze_and_predict(self):
        try:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            query = '''
                SELECT date, SUM(duration) as daily_duration
                FROM study_logs
                WHERE user_id = ?
                GROUP BY date
                ORDER BY date
            '''
            cursor.execute(query, (self.current_user['id'],))
            results = cursor.fetchall()
            conn.close()

            if len(results) < 2:
                QMessageBox.information(self, "提示", "数据不足以进行分析和预测！")
                return

            df = pd.DataFrame(results, columns=['date', 'daily_duration'])
            df['date'] = pd.to_datetime(df['date'])
            df.sort_values('date', inplace=True)

            # 学习习惯分析
            total_duration = df['daily_duration'].sum()
            avg_duration = df['daily_duration'].mean()
            max_duration = df['daily_duration'].max()

            # 学习时长趋势
            plt.figure(figsize=(10, 5))
            plt.plot(df['date'], df['daily_duration'], marker='o')
            plt.title("每日学习时长趋势")
            plt.xlabel("日期")
            plt.ylabel("学习时长（分钟）")
            plt.grid(True)

            # 设置中文字体
            plt.rcParams['font.sans-serif'] = ['SimHei']
            plt.rcParams['axes.unicode_minus'] = False

            plt.tight_layout()
            plt.show()

            # 未来学习时长预测
            model = LinearRegression()
            X = np.array((df['date'] - df['date'].min()).dt.days).reshape(-1, 1)
            y = df['daily_duration'].values
            model.fit(X, y)
            next_day = df['date'].max() + pd.Timedelta(days=1)
            X_pred = np.array([(next_day - df['date'].min()).days]).reshape(-1, 1)
            y_pred = model.predict(X_pred)[0]

            # 显示分析结果
            analysis_text = f"""
总学习时长: {total_duration:.2f} 分钟
平均每日学习时长: {avg_duration:.2f} 分钟
最高每日学习时长: {max_duration:.2f} 分钟

预测 {next_day.strftime('%Y-%m-%d')} 的学习时长: {y_pred:.2f} 分钟
"""
            QMessageBox.information(self, "学习习惯分析与预测", analysis_text)
            logging.info(f"学习习惯分析与预测:\n{analysis_text}")
        except Exception as e:
            logging.error(f"进行学习习惯分析与预测时出错: {e}")
            QMessageBox.warning(self, "错误", f"无法进行分析与预测: {e}")

    def refresh_active_sessions(self):
        try:
            self.active_sessions_table.setRowCount(0)
            with self.tracker.active_sessions_lock:
                for file, times in self.tracker.active_sessions.items():
                    duration = (time.time() - times["start_time"]) / 60  # 分钟
                    row_position = self.active_sessions_table.rowCount()
                    self.active_sessions_table.insertRow(row_position)
                    self.active_sessions_table.setItem(row_position, 0, QTableWidgetItem(os.path.basename(file)))
                    self.active_sessions_table.setItem(row_position, 1, QTableWidgetItem(f"{duration:.2f}"))
            # logging.info("活动会话已刷新")
        except Exception as e:
            logging.error(f"刷新活动会话表时出错: {e}")

    def refresh_charts(self):
        try:
            # 选择当前激活的标签
            current_tab = self.stack.currentWidget().findChild(QTabWidget).currentWidget()
            if current_tab == self.report_tab:
                # 自动刷新当前显示的报告
                current_index = self.stack.currentWidget().findChild(QTabWidget).currentIndex()
                if current_index == 0:  # 学习报告
                    # 根据需要自动刷新，可以存储最后一个查看的报告类型
                    pass
                elif current_index == 1:  # 活动会话
                    pass
                elif current_index == 2:  # 设置
                    pass
            logging.info("图表已自动刷新")
        except Exception as e:
            logging.error(f"自动刷新图表时出错: {e}")

    def exit_program(self):
        if QMessageBox.question(self, "退出", "确定要退出程序吗？", QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            logging.info("用户选择退出程序。")
            self.cleanup()
            QApplication.quit()

    def cleanup(self):
        try:
            self.stop_event.set()
            if self.tracker and self.tracker.is_alive():
                self.tracker.join(timeout=5)
                if self.tracker.is_alive():
                    logging.warning("跟踪线程未能在5秒内停止。")
                else:
                    logging.info("跟踪线程已成功停止。")
            # 处理退出时仍在进行的会话
            if self.tracker:
                with self.tracker.active_sessions_lock:
                    for file, times in list(self.tracker.active_sessions.items()):
                        duration = (time.time() - times["start_time"]) / 60
                        if duration >= LEARNING_THRESHOLD:
                            self.tracker.log_study_time(file, times["start_time"], time.time())
                            self.send_notification(
                                "停止学习",
                                f"退出时停止学习: {os.path.basename(file)}，时长 {duration:.2f} 分钟"
                            )
                            self.log_debug(f"退出时停止学习: {file} at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                            logging.info(
                                f"🛑 退出时停止学习: {file} -> {duration:.2f} 分钟 于 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                            del self.tracker.active_sessions[file]
        except Exception as e:
            logging.error(f"清理资源时出错: {e}")

    def closeEvent(self, event):
        """覆盖窗口关闭事件，确保资源被正确释放。"""
        reply = QMessageBox.question(self, '退出', '确定要退出程序吗？',
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            logging.info("用户通过窗口关闭按钮退出程序。")
            self.cleanup()
            event.accept()
        else:
            event.ignore()

    def log_debug(self, message):
        logging.info(message)


# ==================== 主程序启动 ====================
def main():
    initialize_database()
    app = QApplication(sys.argv)
    window = StudyTrackerApp()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
