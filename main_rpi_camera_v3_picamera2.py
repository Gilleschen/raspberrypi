from flask import Flask, jsonify, request, session, redirect, render_template, url_for, Response, send_file
import os
import pygame
import threading
import atexit
import secrets
from gtts import gTTS
import subprocess
import time
import datetime
from adafruit_servokit import ServoKit  # 引入 ServoKit
import io
from threading import Condition
import numpy as np
from picamera2 import Picamera2  # 引入 Picamera2
from picamera2.encoders import JpegEncoder
from picamera2.outputs import FileOutput


# 設定 Flask 應用
app = Flask(__name__, static_folder='static')
app.secret_key = secrets.token_hex(16)

# 設定藍牙設備 MAC 地址
BLUETOOTH_DEVICE_MAC = "DC:3C:26:00:06:5F"  # 替換成你的藍牙設備 MAC 地址

# 設定伺服馬達的通道數
kit = ServoKit(channels=16)  # 初始化 ServoKit

# 設定「預設初始角度」
DEFAULT_ANGLE = 90  # 伺服馬達的初始角度
current_angle = DEFAULT_ANGLE

def set_servo_angle(angle):
    """ 設定伺服馬達角度 (0° - 180°) """
    # return "200"
    kit.servo[0].angle = angle  # 使用 ServoKit 設定角度
    kit.servo[1].angle = angle  # 使用 ServoKit 設定角度

# **啟動時，讓伺服馬達回到預設角度**
set_servo_angle(current_angle)  # 設定為 90 度

@app.route("/servo_right", methods=["POST"])
def servo_right():
    global current_angle
    if current_angle > 5:  # 確保不低於 0°
        current_angle -= 5  # 每次減少 5 度
        set_servo_angle(current_angle)  # 設置伺服馬達角度
    return jsonify({"message": f"畫面向右"})

@app.route("/servo_left", methods=["POST"])
def servo_left():
    global current_angle
    if current_angle < 175:  # 確保不超過 180°
        current_angle += 5  # 每次增加 5 度
        set_servo_angle(current_angle)  # 設置伺服馬達角度
    return jsonify({"message": f"畫面向左"})

@app.route("/servo_up", methods=["POST"])
def servo_up():
    global current_angle
    if current_angle < 175:  # 確保不超過 180°
        current_angle += 5  # 每次增加 5 度
        set_servo_angle(current_angle)  # 設置伺服馬達角度
    return jsonify({"message": f"畫面向上"})

@app.route("/servo_down", methods=["POST"])
def servo_down():
    global current_angle
    if current_angle > 5:  # 確保不低於 0°
        current_angle -= 5  # 每次減少 5 度
        set_servo_angle(current_angle)  # 設置伺服馬達角度
    return jsonify({"message": f"畫面向下"})

@app.route("/servo_reset", methods=["POST"])
def servo_reset():
    global current_angle
    current_angle = DEFAULT_ANGLE  # 重置為預設角度 (90度)
    set_servo_angle(current_angle)
    return jsonify({"message": f"已重置畫面位置"})

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

# 初始化 Picamera2
class StreamingOutput(io.BufferedIOBase):
    def __init__(self):
        self.frame = None
        self.condition = Condition()

    def write(self, buf):
        with self.condition:
            self.frame = buf
            self.condition.notify_all()
        return len(buf)

# 初始化相機
picam2 = None
output = StreamingOutput()
encoder = None

def init_camera():
    global picam2, output, encoder
    try:
        if picam2 is None:
            picam2 = Picamera2()
            
            # 設定相機配置
            config = picam2.create_still_configuration(
                main={"size": (640, 480)},
                lores={"size": (320, 240)},
                display="lores"
            )
            picam2.configure(config)
            
            # 創建編碼器和輸出
            encoder = JpegEncoder(q=70)
            picam2.start_recording(encoder, FileOutput(output))
            
            print("✅ Pi Camera 2 已初始化")
    except Exception as e:
        print(f"❌ 初始化 Pi Camera 2 失敗: {e}")

def generate_frames():
    global output
    while True:
        with output.condition:
            output.condition.wait()
            frame = output.frame
        
        if frame is not None:
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
        else:
            time.sleep(0.1)

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
    try:
        pygame.mixer.quit()
        pygame.quit()
        if picam2:
            picam2.stop_recording()
            picam2.close()
    except Exception as e:
        print(f"清理資源時發生錯誤: {e}")

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

# **檢查藍牙連接狀態**
@app.route('/bluetooth_status', methods=['GET'])
def bluetooth_status():
    """檢查藍牙連接狀態"""
    try:
        output = bluetooth_command(f"bluetoothctl info {BLUETOOTH_DEVICE_MAC}")
        is_connected = "Connected: yes" in output
        return jsonify({"connected": is_connected})
    except Exception as e:
        return jsonify({"connected": False, "error": str(e)})

@app.route("/take_photo", methods=["POST"])
def take_photo():
    try:
        global picam2, output
        
        # 使用 Picamera2 拍照
        stream = io.BytesIO()
        with output.condition:
            if output.frame:
                stream.write(output.frame)
                stream.seek(0)
            else:
                # 如果沒有從串流獲取到幀，直接拍一張照片
                metadata = picam2.capture_file(stream, format='jpeg')
                stream.seek(0)
        
        # 生成唯一的檔案名稱 (使用時間戳)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"webcam_{timestamp}.jpg"
        
        # 返回二進制響應，使瀏覽器直接下載
        return send_file(
            stream,
            mimetype='image/jpeg',
            as_attachment=True,  # 強制下載而不是直接顯示
            download_name=filename  # 設置下載的檔名
        )
    except Exception as e:
        print(f"拍照時發生錯誤: {e}")
        return jsonify({"error": f"拍照失敗: {str(e)}"}), 500

# 啟動 Flask 伺服器
if __name__ == '__main__':
    try:
        # 初始化相機
        init_camera()
        app.run(host='192.168.192.1', port=5000, debug=True)
    except Exception as e:
        print(f"啟動服務時發生錯誤: {e}")
    finally:
        cleanup() 