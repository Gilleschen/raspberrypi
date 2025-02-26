from flask import Flask, jsonify, request, session, redirect, render_template, url_for, Response
import os
import pygame
import threading
import atexit
import secrets
from gtts import gTTS
import cv2
import subprocess
import time
from gpiozero import Servo  # 替換 pigpio

# 設定 Flask 應用
app = Flask(__name__, static_folder='static')
app.secret_key = secrets.token_hex(16)

# 設定藍牙設備 MAC 地址
BLUETOOTH_DEVICE_MAC = "DC:3C:26:00:06:5F"  # 替換成你的藍牙設備 MAC 地址

# 設定伺服馬達 GPIO
SERVO_PIN = 18  # SG90 伺服馬達信號線接 GPIO 18
servo = Servo(SERVO_PIN)  # 使用 gpiozero 的 Servo 類

# 設定「預設初始角度」
DEFAULT_ANGLE = 90  # gpiozero 中 -1 到 1，對應 0° 到 180°，0 為中間位置
current_angle = DEFAULT_ANGLE

def set_servo_angle(angle):
    """ 設定 SG90 伺服馬達角度 (0° - 180°) """
    # 將 0-180 度轉換為 gpiozero 的 -1 到 1 範圍
    value = (angle / 90.0) - 1  # 0° -> -1, 90° -> 0, 180° -> 1
    servo.value = value

# **啟動時，讓伺服馬達回到預設角度**
# set_servo_angle(current_angle)  # 設定為 90 度 (被註解掉了)

@app.route("/servo_left", methods=["POST"])
def servo_left():
    global current_angle
    if current_angle > 0:  # 確保不低於 0°
        # current_angle -= 50
        current_angle = 0
        set_servo_angle(current_angle)
    return jsonify({"message": f"畫面向左"})

@app.route("/servo_right", methods=["POST"])
def servo_right():
    global current_angle
    if current_angle < 180:  # 確保不超過 180°
        # current_angle += 50
        current_angle = 180
        set_servo_angle(current_angle)
    return jsonify({"message": f"畫面向右"})

def bluetooth_command(cmd):
    try:
        output = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        return output.stdout.strip()
    except Exception as e:
        return str(e)

def is_bluetooth_powered_on():
    """檢查藍牙是否已開啟"""
    output = bluetooth_command("bluetoothctl show")
    return "Powered: yes" in output

def power_on_bluetooth():
    """確保藍牙已開啟"""
    if not is_bluetooth_powered_on():
        bluetooth_command("sudo rfkill unblock bluetooth")
        time.sleep(2)
        print("🔹 藍牙未開啟，嘗試開啟藍牙...")
        bluetooth_command("bluetoothctl power on")
        time.sleep(2)  # 等待藍牙啟動
    else:
        print("✅ 藍牙已經開啟！")

# 登入帳號密碼
VALID_USERNAME = "jimchen"
VALID_PASSWORD = "m800"

# 初始化 OpenCV 視訊攝影機
camera = cv2.VideoCapture(0)
camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

def generate_frames():
    while True:
        success, frame = camera.read()
        if not success:
            continue  # 避免 Flask 崩潰，繼續嘗試讀取

        ret, buffer = cv2.imencode('.jpg', frame)
        if not ret:
            continue

        frame = buffer.tobytes()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

# 設定音效資料夾
SOUND_FOLDER = os.path.join(os.path.dirname(__file__), 'sound')
if not os.path.exists(SOUND_FOLDER):
    os.makedirs(SOUND_FOLDER)

# 初始化 pygame
try:
    pygame.mixer.init()
except Exception as e:
    print(f"初始化音效系統失敗: {e}")

# 清理資源
def cleanup():
    pygame.mixer.quit()
    pygame.quit()
    servo.detach()  # 釋放伺服馬達資源

atexit.register(cleanup)

# 檢查網路狀態
@app.route('/status', methods=['GET'])
def status():
    return jsonify({"message": "Network is good"})

# **首頁 (工具箱)**，需要登入
@app.route('/home')
def home():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    return render_template('home.html')

# 提供 Webcam 影像串流
@app.route('/video_feed')
def video_feed():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

# **登入頁面**
@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if (request.form.get('username') == VALID_USERNAME and 
            request.form.get('password') == VALID_PASSWORD):
            session['logged_in'] = True
            return redirect(url_for('home'))

        return render_template('login.html', error="Invalid credentials")

    return render_template('login.html')

# **登出功能**
@app.route('/logout')
def logout():
    session.pop('logged_in', None)  # 移除登入狀態
    return redirect(url_for('login'))  # 返回登入頁面

# **播放音效**
def play_audio(file_path):
    try:
        pygame.mixer.music.load(file_path)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            pygame.time.Clock().tick(10)
    except Exception as e:
        print(f"播放音效時發生錯誤: {e}")

@app.route('/play_sound', methods=['POST'])
def play_sound():
    data = request.get_json()
    file_name = data.get('file')

    if not file_name:
        return jsonify({"error": "請提供音效檔案名稱"}), 400

    file_name = os.path.basename(file_name)
    file_path = os.path.join(SOUND_FOLDER, file_name)

    if not os.path.exists(file_path):
        return jsonify({"error": f"音效檔案 {file_name} 不存在"}), 404

    if not file_name.lower().endswith(('.mp3', '.wav')):
        return jsonify({"error": "不支援的檔案格式"}), 400

    threading.Thread(target=play_audio, args=(file_path,)).start()
    return jsonify({"message": f"正在播放 {file_name}"}), 200

# **文字轉語音**
@app.route('/speak', methods=['POST'])
def speak():
    data = request.get_json()
    text = data.get("text", "")

    if not text:
        return jsonify({"error": "請輸入文字"}), 400

    tts = gTTS(text=text, lang="zh-tw")
    file_path = os.path.join(SOUND_FOLDER, "custom_message.mp3")
    tts.save(file_path)

    threading.Thread(target=play_audio, args=(file_path,)).start()
    return jsonify({"message": "播放語音"}), 200

# **開啟藍牙**
@app.route('/power_on_bluetooth', methods=['POST'])
def api_power_on_bluetooth():
    power_on_bluetooth()
    return jsonify({"message": "藍牙已開啟"}), 200

# **連接藍牙設備**
@app.route('/connect_bluetooth', methods=['POST'])
def connect_bluetooth():
    power_on_bluetooth()  # 確保藍牙已開啟
    result = bluetooth_command(f"bluetoothctl connect {BLUETOOTH_DEVICE_MAC}")
    if "Connection successful" in result or "Connected: yes" in bluetooth_command(f"bluetoothctl info {BLUETOOTH_DEVICE_MAC}"):
        return jsonify({"message": "藍牙連接成功"})
    return jsonify({"message": "藍牙連接失敗", "error": result}), 400

# **斷開藍牙設備**
@app.route('/disconnect_bluetooth', methods=['POST'])
def disconnect_bluetooth():
    result = bluetooth_command(f"bluetoothctl disconnect {BLUETOOTH_DEVICE_MAC}")
    if "Successful disconnected" in result or "Device has been disconnected" in result:
        return jsonify({"message": "藍牙已中斷"})
    return jsonify({"message": "藍牙中斷失敗", "error": result}), 400

# 啟動 Flask 伺服器
if __name__ == '__main__':
    try:
        app.run(host='192.168.192.4', port=5000, debug=False)
    except Exception as e:
        print(f"啟動服務時發生錯誤: {e}")
    finally:
        cleanup()