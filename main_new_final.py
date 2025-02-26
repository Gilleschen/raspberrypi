from flask import Flask, jsonify, request, session, redirect, render_template, url_for, Response, send_file
import os
import pygame
import threading
import atexit
import secrets
from gtts import gTTS
import cv2
import subprocess
import time
import datetime
from adafruit_servokit import ServoKit  # 引入 ServoKit
import pyaudio  # 新增 pyaudio 庫用於處理音訊


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

# 初始化 OpenCV 視訊攝影機
camera = cv2.VideoCapture(0)
camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

# 初始化音訊串流
CHUNK = 1024
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 44100
audio = pyaudio.PyAudio()
audio_stream = None

# 列出所有可用的音訊設備
def list_audio_devices():
    """列出所有可用的音訊輸入設備"""
    info = audio.get_host_api_info_by_index(0)
    numdevices = info.get('deviceCount')
    devices = []
    
    print("可用的音訊輸入設備:")
    for i in range(0, numdevices):
        device_info = audio.get_device_info_by_host_api_device_index(0, i)
        max_input_channels = device_info.get('maxInputChannels')
        if max_input_channels > 0:
            print(f"設備 ID {i}: {device_info.get('name')} (通道數: {max_input_channels})")
            devices.append((i, device_info.get('name'), max_input_channels))
    
    return devices

def start_audio_stream():
    global audio_stream
    try:
        # 列出所有設備
        devices = list_audio_devices()
        
        # 嘗試找到合適的設備
        device_index = None
        device_channels = 1
        
        if devices:
            # 優先選擇內建麥克風
            for dev_id, name, channels in devices:
                if "built-in" in name.lower() or "內建" in name:
                    device_index = dev_id
                    device_channels = min(channels, 2)  # 最多使用 2 通道
                    print(f"選擇內建麥克風: ID {dev_id}, 通道數 {device_channels}")
                    break
            
            # 如果沒有找到內建麥克風，使用第一個可用設備
            if device_index is None and devices:
                device_index = devices[0][0]
                device_channels = min(devices[0][2], 2)  # 最多使用 2 通道
                print(f"選擇第一個可用設備: ID {device_index}, 通道數 {device_channels}")
        
        # 根據設備支援的通道數調整
        actual_channels = device_channels if device_channels > 0 else 1
        
        print(f"嘗試開啟音訊串流: 設備 ID {device_index}, 通道數 {actual_channels}")
        
        # 開啟音訊串流
        audio_stream = audio.open(
            format=FORMAT,
            channels=actual_channels,  # 使用設備支援的通道數
            rate=RATE,
            input=True,
            input_device_index=device_index,  # 可能是 None，表示使用默認設備
            frames_per_buffer=CHUNK
        )
        
        print(f"✅ 音訊串流已啟動: 設備 ID {device_index}, 通道數 {actual_channels}")
        return True
    except Exception as e:
        print(f"❌ 音訊串流啟動失敗: {e}")
        return False

def stop_audio_stream():
    global audio_stream
    try:
        if audio_stream:
            # 先檢查串流是否活躍
            if audio_stream.is_active():
                audio_stream.stop_stream()
            audio_stream.close()
            audio_stream = None
            print("✅ 音訊串流已停止")
    except Exception as e:
        print(f"停止音訊串流時發生錯誤: {e}")
    finally:
        # 確保清理任何剩餘的資源
        audio_stream = None

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

def generate_audio():
    global audio_stream
    if not audio_stream:
        start_audio_stream()
    
    # 發送 WAV 頭部信息
    wav_header = get_wav_header(RATE, 16, CHANNELS)
    yield wav_header
    
    while True:
        try:
            if audio_stream:
                data = audio_stream.read(CHUNK, exception_on_overflow=False)
                # 確保 data 是位元組類型
                if isinstance(data, bytes):
                    yield data
                else:
                    # 如果不是位元組，嘗試轉換
                    yield bytes(data)
            else:
                time.sleep(0.1)
        except Exception as e:
            print(f"音訊串流錯誤: {e}")
            time.sleep(0.5)
            stop_audio_stream()
            start_audio_stream()
            wav_header = get_wav_header(RATE, 16, CHANNELS)
            yield wav_header

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
        stop_audio_stream()
        if audio:
            audio.terminate()
        pygame.mixer.quit()
        pygame.quit()
        camera.release()
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

# 提供音訊串流
@app.route('/audio_feed')
def audio_feed():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    # 使用更簡單的方式處理音訊串流
    def generate():
        global audio_stream
        
        # 如果音訊串流未啟動，嘗試啟動
        if not audio_stream:
            success = start_audio_stream()
            if not success:
                # 如果啟動失敗，返回空音訊
                yield bytes(get_wav_header(RATE, 16, 1))
                return
        
        # 獲取實際的通道數
        actual_channels = audio_stream._channels if hasattr(audio_stream, '_channels') else 1
        
        # 發送 WAV 頭部信息
        yield bytes(get_wav_header(RATE, 16, actual_channels))
        
        while True:
            try:
                if audio_stream and audio_stream.is_active():
                    data = audio_stream.read(CHUNK, exception_on_overflow=False)
                    if data:
                        yield data
                else:
                    time.sleep(0.1)
                    # 如果音訊串流不活躍，嘗試重新啟動
                    if not audio_stream or not audio_stream.is_active():
                        stop_audio_stream()
                        if start_audio_stream():
                            # 重新獲取通道數
                            actual_channels = audio_stream._channels if hasattr(audio_stream, '_channels') else 1
                            # 重新發送 WAV 頭部信息
                            yield bytes(get_wav_header(RATE, 16, actual_channels))
            except Exception as e:
                print(f"音訊串流錯誤: {e}")
                time.sleep(0.5)
                stop_audio_stream()
                if start_audio_stream():
                    # 重新獲取通道數
                    actual_channels = audio_stream._channels if hasattr(audio_stream, '_channels') else 1
                    # 重新發送 WAV 頭部信息
                    yield bytes(get_wav_header(RATE, 16, actual_channels))
    
    return Response(generate(), mimetype='audio/wav')

# 啟動/停止音訊串流
@app.route('/toggle_audio', methods=['POST'])
def toggle_audio():
    global audio_stream
    data = request.get_json()
    enable = data.get('enable', False)
    
    try:
        if enable:
            if not audio_stream:
                success = start_audio_stream()
                if success:
                    return jsonify({"message": "音訊串流已啟動", "status": "on"})
                else:
                    return jsonify({"message": "音訊串流啟動失敗", "status": "off", "error": "無法啟動音訊設備"})
            else:
                return jsonify({"message": "音訊串流已經啟動", "status": "on"})
        else:
            stop_audio_stream()
            return jsonify({"message": "音訊串流已停止", "status": "off"})
    except Exception as e:
        print(f"切換音訊串流時發生錯誤: {e}")
        # 確保在發生錯誤時也能清理資源
        stop_audio_stream()
        return jsonify({"message": "音訊串流操作失敗", "status": "error", "error": str(e)})

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
from io import BytesIO

@app.route("/take_photo", methods=["POST"])
def take_photo():
    try:
        # 讀取當前的視訊幀
        success, frame = camera.read()
        if not success:
            return jsonify({"error": "無法捕捉照片"}), 400
        
        # 生成唯一的檔案名稱 (使用時間戳)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"webcam_{timestamp}.jpg"
        
        # 將圖像編碼為 JPEG 格式
        ret, buffer = cv2.imencode('.jpg', frame)
        if not ret:
            return jsonify({"error": "圖像編碼失敗"}), 500
        
        # 將編碼後的圖像轉換為 bytes
        img_bytes = buffer.tobytes()
        
        # 使用 BytesIO 創建內存文件對象
        img_io = BytesIO(img_bytes)
        
        # 返回二進制響應，使瀏覽器直接下載
        return send_file(
            img_io,
            mimetype='image/jpeg',
            as_attachment=True,  # 強制下載而不是直接顯示
            download_name=filename  # 設置下載的檔名
        )
    except Exception as e:
        print(f"拍照時發生錯誤: {e}")
        return jsonify({"error": f"拍照失敗: {str(e)}"}), 500
# 創建 WAV 頭部信息
def get_wav_header(sample_rate=44100, bits_per_sample=16, channels=1):
    """生成 WAV 文件頭，支援不同的通道數"""
    # 確保通道數至少為 1
    actual_channels = max(1, channels)
    
    header = bytearray()
    # RIFF 頭部
    header.extend(b'RIFF')
    header.extend((0).to_bytes(4, byteorder='little'))  # 文件大小，暫時設為 0
    header.extend(b'WAVE')
    # fmt 子塊
    header.extend(b'fmt ')
    header.extend((16).to_bytes(4, byteorder='little'))  # 子塊大小
    header.extend((1).to_bytes(2, byteorder='little'))   # 音頻格式 (PCM)
    header.extend((actual_channels).to_bytes(2, byteorder='little'))  # 通道數
    header.extend((sample_rate).to_bytes(4, byteorder='little'))  # 採樣率
    bytes_per_second = sample_rate * actual_channels * bits_per_sample // 8
    header.extend((bytes_per_second).to_bytes(4, byteorder='little'))  # 每秒字節數
    header.extend((actual_channels * bits_per_sample // 8).to_bytes(2, byteorder='little'))  # 塊對齊
    header.extend((bits_per_sample).to_bytes(2, byteorder='little'))  # 每個樣本的位數
    # data 子塊
    header.extend(b'data')
    header.extend((0).to_bytes(4, byteorder='little'))  # 數據大小，暫時設為 0
    return bytes(header)  # 確保返回位元組

# 啟動 Flask 伺服器
if __name__ == '__main__':
    try:
        # 確保程式啟動時音訊串流是關閉的
        stop_audio_stream()
        app.run(host='192.168.192.1', port=5000, debug=True)
    except Exception as e:
        print(f"啟動服務時發生錯誤: {e}")
    finally:
        cleanup()