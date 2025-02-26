const API_BASE_URL = "http://192.168.192.1:5000";
let bluetoothConnected = false;
let audioEnabled = false;
const audioToggleBtn = document.getElementById("audioToggleBtn");
const audioPlayer = document.getElementById("audioPlayer");

// 頁面加載時檢查藍牙狀態
document.addEventListener("DOMContentLoaded", async () => {
    try {
        const response = await fetch(`${API_BASE_URL}/bluetooth_status`);
        const data = await response.json();
        bluetoothConnected = data.connected;
        document.getElementById("bluetoothBtn").innerText = bluetoothConnected
            ? "中斷藍芽"
            : "連接藍芽";
    } catch (error) {
        console.error("無法獲取藍牙狀態:", error);
    }

    // 設置音效按鈕的事件監聽器
    document.querySelectorAll(".playSoundBtn").forEach((button) => {
        button.addEventListener("click", async () => {
            try {
                const soundFile = button.dataset.sound + ".mp3";
                const response = await fetch(`${API_BASE_URL}/play_sound`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ file: soundFile }),
                });
                const data = await response.json();
                showMessage(document.getElementById("soundMessage"), data.message);
            } catch (error) {
                showMessage(document.getElementById("soundMessage"), "播放音效失敗", true);
            }
        });
    });

    // 設置其他按鈕的事件監聽器
    setupEventListeners();
});

// 顯示訊息的通用函數
const showMessage = (element, message, isError = false) => {
    element.innerText = message;
    element.style.color = isError ? "red" : "black";
    setTimeout(() => (element.innerText = ""), 3000);
};

// 設置事件監聽器
function setupEventListeners() {
    // 檢查狀態按鈕
    document.getElementById("checkStatusBtn").addEventListener("click", async () => {
        try {
            const response = await fetch(`${API_BASE_URL}/status`);
            const data = await response.json();
            showMessage(document.getElementById("statusMessage"), data.message);
        } catch (error) {
            console.error("狀態檢查失敗:", error);
            showMessage(document.getElementById("statusMessage"), "無法連接到 API", true);
        }
    });

    // 藍牙按鈕
    document.getElementById("bluetoothBtn").addEventListener("click", async () => {
        const endpoint = bluetoothConnected ? "/disconnect_bluetooth" : "/connect_bluetooth";
        try {
            const response = await fetch(`${API_BASE_URL}${endpoint}`, {
                method: "POST",
            });
            const data = await response.json();
            showMessage(document.getElementById("bluetoothMessage"), data.message);
            bluetoothConnected = !bluetoothConnected;
            document.getElementById("bluetoothBtn").innerText = bluetoothConnected ? "中斷藍芽" : "連接藍芽";
        } catch (error) {
            showMessage(document.getElementById("bluetoothMessage"), "藍牙操作失敗", true);
        }
    });

    // 音訊切換按鈕
    audioToggleBtn.addEventListener("click", async () => {
        try {
            const response = await fetch(`${API_BASE_URL}/toggle_audio`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ enable: !audioEnabled }),
            });

            const data = await response.json();
            audioEnabled = data.status === "on";

            if (audioEnabled) {
                audioToggleBtn.innerText = "關閉麥克風";
                audioToggleBtn.classList.remove("off");
                setupAudioStream();
            } else {
                audioToggleBtn.innerText = "開啟麥克風";
                audioToggleBtn.classList.add("off");
                stopAudioStream();
            }

            showMessage(document.getElementById("statusMessage"), data.message);
        } catch (error) {
            console.error("音訊控制失敗:", error);
            showMessage(document.getElementById("statusMessage"), "音訊控制失敗", true);
        }
    });
}

// 伺服馬達控制函數
function moveUp() {
    fetch(`${API_BASE_URL}/servo_up`, { method: "POST" })
        .then((response) => response.json())
        .then((data) => {
            document.getElementById("servoMessage").innerText = data.message;
        })
        .catch(() => showMessage(servoMessage, "無法上移", true));
}

function moveDown() {
    fetch(`${API_BASE_URL}/servo_down`, { method: "POST" })
        .then((response) => response.json())
        .then((data) => {
            document.getElementById("servoMessage").innerText = data.message;
        })
        .catch(() => showMessage(servoMessage, "無法下移", true));
}

function rotateLeft() {
    fetch(`${API_BASE_URL}/servo_left`, { method: "POST" })
        .then((response) => response.json())
        .then((data) => {
            document.getElementById("servoMessage").innerText = data.message;
        })
        .catch(() => showMessage(servoMessage, "無法轉動", true));
}

function rotateRight() {
    fetch(`${API_BASE_URL}/servo_right`, { method: "POST" })
        .then((response) => response.json())
        .then((data) => {
            document.getElementById("servoMessage").innerText = data.message;
        })
        .catch(() => showMessage(servoMessage, "無法轉動", true));
}

function resetServo() {
    fetch(`${API_BASE_URL}/servo_reset`, { method: "POST" })
        .then((response) => response.json())
        .then((data) => {
            document.getElementById("servoMessage").innerText = data.message;
        })
        .catch(() => showMessage(servoMessage, "無法重置位置", true));
}

// 文字轉語音
function sendCustomMessage() {
    let text = document.getElementById("customMessage").value;
    fetch(`${API_BASE_URL}/speak`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: text }),
    });
}

// 設置音訊串流
function setupAudioStream() {
    try {
        console.log("開始設置音訊串流");
        audioPlayer.src = `${API_BASE_URL}/audio_feed?t=${new Date().getTime()}`;
        audioPlayer.volume = 1.0;

        audioPlayer.onerror = function (e) {
            console.error("音訊播放錯誤:", e);
            showMessage(document.getElementById("statusMessage"), "音訊播放錯誤", true);
        };

        audioPlayer.play()
            .then(() => {
                console.log("音訊播放成功");
            })
            .catch((err) => {
                console.error("播放音訊失敗:", err);
                showMessage(document.getElementById("statusMessage"), "播放音訊失敗，請點擊頁面啟用音訊", true);

                document.addEventListener("click", function playOnce() {
                    audioPlayer.play().catch((e) => console.error("再次播放失敗:", e));
                    document.removeEventListener("click", playOnce);
                });
            });
    } catch (error) {
        console.error("設置音訊串流失敗:", error);
        showMessage(document.getElementById("statusMessage"), "設置音訊串流失敗", true);
    }
}

// 停止音訊串流
function stopAudioStream() {
    audioPlayer.pause();
    audioPlayer.src = "";
} 


// 拍照功能 - 直接下載到用戶設備
function takePhoto() {
    // 顯示處理中的消息
    showMessage(document.getElementById("servoMessage"), "處理中...");
    
    // 創建一個表單數據對象
    const formData = new FormData();
    
    // 發送請求到後端
    fetch(`${API_BASE_URL}/take_photo`, {
        method: "POST",
    })
    .then(response => {
        if (!response.ok) {
            return response.json().then(data => {
                throw new Error(data.error || "拍照失敗");
            });
        }
        
        // 從響應中提取文件名
        const contentDisposition = response.headers.get('Content-Disposition');
        let filename = "webcam.jpg";
        if (contentDisposition) {
            const filenameMatch = contentDisposition.match(/filename="(.+)"/);
            if (filenameMatch) {
                filename = filenameMatch[1];
            }
        }
        
        // 返回 blob 數據
        return response.blob().then(blob => ({
            blob,
            filename
        }));
    })
    .then(({ blob, filename }) => {
        // 使用 URL.createObjectURL 創建臨時 URL
        const url = URL.createObjectURL(blob);
        
        // 創建一個臨時的 <a> 元素來觸發下載
        const link = document.createElement('a');
        link.href = url;
        link.download = filename;
        link.style.display = 'none';
        
        // 將鏈接添加到文檔並觸發點擊
        document.body.appendChild(link);
        link.click();
        
        // 清理
        setTimeout(() => {
            URL.revokeObjectURL(url);
            document.body.removeChild(link);
            showMessage(document.getElementById("servoMessage"), "照片已下載");
        }, 100);
    })
    .catch(error => {
        console.error("拍照失敗:", error);
        showMessage(document.getElementById("servoMessage"), error.message || "拍照失敗", true);
    });
}