import os
import time
import pandas as pd
import threading
from datetime import datetime
import matplotlib.pyplot as plt

# ==================== 配置部分 ====================
ROOT_DIR = r'D:\课件\学科ppt'  # 根目录
LOG_FILE = r'D:\study_progress\study_log.csv'  # 学习日志路径
CHECK_INTERVAL = 2  # 文件检查间隔（秒）
LEARNING_THRESHOLD = 0.1  # 最小学习时长（分钟）
INACTIVITY_THRESHOLD = 300  # 不活动超时时间（秒），设置为5分钟
SUPPORTED_EXTENSIONS = ['.pdf', '.docx', '.pptx']  # 支持的文件类型

# Matplotlib 字体设置（解决中文字符无法显示的问题）
plt.rcParams['font.sans-serif'] = ['SimHei']  # 支持中文
plt.rcParams['axes.unicode_minus'] = False  # 支持负号显示


# ==================== 初始化日志 ====================
def initialize_log():
    if not os.path.exists(os.path.dirname(LOG_FILE)):
        os.makedirs(os.path.dirname(LOG_FILE))
    if not os.path.exists(LOG_FILE):
        df = pd.DataFrame(columns=[
            "文件名", "学科", "学习时长（分钟）", "状态",
            "开始时间", "结束时间", "日期", "周", "月",
            "最后访问时间"
        ])
        df.to_csv(LOG_FILE, index=False)
        print("✅ 学习日志初始化完成！")


# ==================== 文件检测与学习时长记录 ====================
def get_all_supported_files():
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


def track_study_time(stop_event, active_sessions_lock, active_sessions):
    print("🚀 开始追踪学习时长... (按 Ctrl+C 停止)")
    all_files = get_all_supported_files()

    while not stop_event.is_set():
        current_time = time.time()
        current_files = get_all_supported_files()

        # 检测文件波动
        for file, last_atime in current_files.items():
            current_atime = last_atime
            if file not in all_files:
                # 新文件被添加
                all_files[file] = current_atime

            if current_atime != all_files[file]:
                with active_sessions_lock:
                    if file not in active_sessions:
                        # 新的学习会话开始
                        active_sessions[file] = {
                            "start_time": current_time,
                            "last_fluctuation": current_time
                        }
                        print(f"🟢 开始学习: {file} 于 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                    else:
                        # 更新最后一次波动时间
                        active_sessions[file]["last_fluctuation"] = current_time
                all_files[file] = current_atime

        # 检测不活动超时
        with active_sessions_lock:
            files_to_remove = []
            for file, times in active_sessions.items():
                last_fluctuation = times["last_fluctuation"]
                if current_time - last_fluctuation > INACTIVITY_THRESHOLD:
                    duration = (last_fluctuation - times["start_time"]) / 60  # 转换为分钟
                    if duration >= LEARNING_THRESHOLD:
                        log_study_time(file, times["start_time"], last_fluctuation)
                        print(
                            f"🛑 停止学习: {file} -> {duration:.2f} 分钟 于 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                    files_to_remove.append(file)
            for file in files_to_remove:
                del active_sessions[file]

        # 更新 all_files 字典，移除已删除的文件
        removed_files = set(all_files.keys()) - set(current_files.keys())
        for file in removed_files:
            with active_sessions_lock:
                if file in active_sessions:
                    times = active_sessions[file]
                    duration = (times["last_fluctuation"] - times["start_time"]) / 60
                    if duration >= LEARNING_THRESHOLD:
                        log_study_time(file, times["start_time"], times["last_fluctuation"])
                        print(
                            f"🛑 文件被删除或移动，停止学习: {file} -> {duration:.2f} 分钟 于 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                    del active_sessions[file]
            del all_files[file]

        time.sleep(CHECK_INTERVAL)


def log_study_time(file_path, start_time, end_time):
    duration = (end_time - start_time) / 60  # 转换为分钟
    try:
        df = pd.read_csv(LOG_FILE)
    except pd.errors.EmptyDataError:
        df = pd.DataFrame(columns=[
            "文件名", "学科", "学习时长（分钟）", "状态",
            "开始时间", "结束时间", "日期", "周", "月",
            "最后访问时间"
        ])

    filename = os.path.basename(file_path)
    subject = file_path.split(os.sep)[-2] if len(file_path.split(os.sep)) >= 2 else "未知"
    now = datetime.now()
    date = now.strftime("%Y-%m-%d")
    week = now.strftime("%Y-%U")
    month = now.strftime("%Y-%m")
    start_datetime = datetime.fromtimestamp(start_time).strftime("%Y-%m-%d %H:%M:%S")
    end_datetime = datetime.fromtimestamp(end_time).strftime("%Y-%m-%d %H:%M:%S")

    status = "已完成" if duration >= 15 else "进行中"

    new_entry = pd.DataFrame({
        "文件名": [filename],
        "学科": [subject],
        "学习时长（分钟）": [round(duration, 2)],
        "状态": [status],
        "开始时间": [start_datetime],
        "结束时间": [end_datetime],
        "日期": [date],
        "周": [week],
        "月": [month],
        "最后访问时间": [now.strftime("%Y-%m-%d %H:%M:%S")]
    })

    df = pd.concat([df, new_entry], ignore_index=True)
    df.to_csv(LOG_FILE, index=False)


# ==================== 学习报告生成 ====================
def generate_report():
    try:
        df = pd.read_csv(LOG_FILE)
    except pd.errors.EmptyDataError:
        print("📭 没有找到学习记录！")
        return

    if df.empty:
        print("📭 没有找到学习记录！")
        return

    while True:
        print("\n--- 📊 学习进度报告菜单 ---")
        print("1. 查看每日学科学习时长")
        print("2. 查看每周学科学习时长")
        print("3. 查看每月学科学习时长")
        print("4. 查看学科总学习时长分布")
        print("5. 导出学习日志为Excel")
        print("6. 返回主菜单")
        choice = input("请输入选项 (1/2/3/4/5/6): ")

        if choice == "1":
            show_summary(df, "日期", "每日学科学习时长")
        elif choice == "2":
            show_summary(df, "周", "每周学科学习时长", detailed=True)
        elif choice == "3":
            show_summary(df, "月", "每月学科学习时长", detailed=True)
        elif choice == "4":
            show_subject_summary(df)
        elif choice == "5":
            export_log_to_excel(df)
        elif choice == "6":
            break
        else:
            print("❌ 无效选项，请重新输入！")


def show_summary(df, group_by, title, detailed=False):
    if detailed:
        summary = df.groupby([group_by, "日期", "学科"])["学习时长（分钟）"].sum().unstack().fillna(0)
    else:
        summary = df.groupby([group_by, "学科"])["学习时长（分钟）"].sum().unstack().fillna(0)

    print(f"\n--- 📈 {title} ---")
    print(summary)

    summary.plot(kind='bar', stacked=True, title=title, ylabel="学习时长（分钟）", xlabel=group_by)
    plt.tight_layout()
    plt.show()


def show_subject_summary(df):
    summary = df.groupby("学科")["学习时长（分钟）"].sum().sort_values(ascending=False)
    print("\n--- 📈 学科总学习时长分布 ---")
    print(summary)

    fig, axes = plt.subplots(1, 2, figsize=(14, 7))
    summary.plot(kind='bar', ax=axes[0], title="学科学习时长分布")
    summary.plot(kind='pie', autopct='%1.1f%%', ax=axes[1], title="学科学习时长占比")
    plt.tight_layout()
    plt.show()


def export_log_to_excel(df):
    export_path = r'D:\study_progress\study_log.xlsx'
    try:
        df.to_excel(export_path, index=False)
        print(f"✅ 学习日志已成功导出到 {export_path}")
    except Exception as e:
        print(f"❌ 导出失败: {e}")


# ==================== 显示当前活动会话 ====================
def display_active_sessions(active_sessions, active_sessions_lock):
    with active_sessions_lock:
        if not active_sessions:
            print("当前没有正在进行的学习会话。")
        else:
            print("\n--- 当前活动学习会话 ---")
            for file, times in active_sessions.items():
                duration = (time.time() - times["start_time"]) / 60  # 分钟
                print(f"{file} | 已学习: {duration:.2f} 分钟")


# ==================== 主菜单 ====================
def main_menu():
    initialize_log()
    stop_event = threading.Event()
    active_sessions_lock = threading.Lock()
    active_sessions = {}
    tracker_thread = threading.Thread(target=track_study_time, args=(stop_event, active_sessions_lock, active_sessions),
                                      daemon=True)
    tracker_thread.start()

    try:
        while True:
            print("\n-- 📚 学习进度跟踪系统 --")
            print("1. 查看学习报告")
            print("2. 查看当前活动学习会话")
            print("3. 退出程序")
            choice = input("请输入选项 (1/2/3): ")

            if choice == "1":
                generate_report()
            elif choice == "2":
                display_active_sessions(active_sessions, active_sessions_lock)
            elif choice == "3":
                print("🔴 停止跟踪并退出程序...")
                stop_event.set()
                tracker_thread.join()
                # 处理退出时仍在进行的会话
                with active_sessions_lock:
                    for file, times in active_sessions.items():
                        duration = (time.time() - times["start_time"]) / 60
                        if duration >= LEARNING_THRESHOLD:
                            log_study_time(file, times["start_time"], time.time())
                            print(
                                f"🛑 退出时停止学习: {file} -> {duration:.2f} 分钟 于 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                break
            else:
                print("❌ 无效选项，请重新输入！")
    except KeyboardInterrupt:
        print("\n🔴 收到中断信号，停止跟踪并退出程序...")
        stop_event.set()
        tracker_thread.join()
        with active_sessions_lock:
            for file, times in active_sessions.items():
                duration = (time.time() - times["start_time"]) / 60
                if duration >= LEARNING_THRESHOLD:
                    log_study_time(file, times["start_time"], time.time())
                    print(
                        f"🛑 中断时停止学习: {file} -> {duration:.2f} 分钟 于 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("✅ 程序已退出。")


# ==================== 主程序启动 ====================
if __name__ == "__main__":
    main_menu()
