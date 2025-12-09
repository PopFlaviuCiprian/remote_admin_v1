# client_gui.py
import sys, os, json, asyncio, threading, time, io
from uuid import uuid4
from PyQt5 import QtWidgets, QtGui, QtCore
from PyQt5.QtWidgets import QApplication, QLabel, QPushButton, QVBoxLayout, QWidget, QLineEdit, QTextEdit, QHBoxLayout
import websockets
from cryptography.fernet import Fernet
import mss, cv2, numpy as np
from PIL import Image
from pynput.mouse import Controller as MouseController, Button as MouseButton
from pynput.keyboard import Controller as KeyController

# === CONFIG ===
BROKER_URL = "ws://SERVER_IP:9000"   # <- schimbi aici
CONFIG_FILE = "client_config.json"

# === UTILITIES ===
def load_or_create_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE,"r") as f:
            return json.load(f)
    else:
        cfg = {"id": str(uuid4())[:8], "password": None}
        # genereaza parola simpla
        import random, string
        cfg["password"] = ''.join(random.choices(string.ascii_uppercase+string.digits, k=6))
        with open(CONFIG_FILE,"w") as f:
            json.dump(cfg,f)
        return cfg

cfg = load_or_create_config()

# === GUI APP ===
class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PyRemote (Host & Viewer)")
        self.setGeometry(200,200,900,700)

        self.id_label = QLabel(f"Your ID: {cfg['id']}  Password: {cfg['password']}")
        self.log = QTextEdit()
        self.log.setReadOnly(True)

        # viewer controls
        self.target_input = QLineEdit()
        self.target_input.setPlaceholderText("Target ID (ex: host-id)")

        self.connect_btn = QPushButton("Request Connect")
        self.connect_btn.clicked.connect(self.request_connect)

        # host accept button (shown when incoming)
        self.accept_btn = QPushButton("Accept incoming")
        self.accept_btn.setEnabled(False)
        self.accept_btn.clicked.connect(self.accept_incoming)

        # image display (viewer)
        self.img_label = QLabel("Remote screen will appear here")
        self.img_label.setFixedSize(820,460)
        self.img_label.setAlignment(QtCore.Qt.AlignCenter)

        # layout
        top_layout = QHBoxLayout()
        top_layout.addWidget(self.id_label)
        top_layout.addStretch()
        top_layout.addWidget(self.accept_btn)

        v = QVBoxLayout()
        v.addLayout(top_layout)
        v.addWidget(self.log)
        controls = QHBoxLayout()
        controls.addWidget(self.target_input)
        controls.addWidget(self.connect_btn)
        v.addLayout(controls)
        v.addWidget(self.img_label)
        self.setLayout(v)

        # background
        self.ws = None
        self.loop = None
        self.incoming_from = None
        self.session_key = None
        self.peer = None
        self.sending = False
        self.mouse = MouseController()
        self.keyboard = KeyController()

        # start networking background thread
        threading.Thread(target=self.start_loop, daemon=True).start()

    def log_msg(self,m):
        print(m)
        self.log.append(m)

    def start_loop(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self.network_main())

    async def network_main(self):
        try:
            self.ws = await websockets.connect(BROKER_URL, max_size=None)
            # register
            await self.ws.send(json.dumps({"type":"register","id":cfg["id"], "password":cfg["password"]}))
            self.log_msg("Registered at broker: " + cfg["id"])
            # listen loop
            asyncio.create_task(self.recv_loop())
        except Exception as e:
            self.log_msg("Network error: " + str(e))

    async def recv_loop(self):
        try:
            async for raw in self.ws:
                # raw is text (JSON) or bytes (binary forwarded)
                if isinstance(raw, bytes):
                    # binary messages are header\npayload
                    header, sep, payload = raw.partition(b'\n')
                    if header.startswith(b'BINARY|'):
                        target = header.split(b'|',1)[1].decode()
                        # if target equals our id -> process
                        if target != cfg["id"]:
                            continue
                        if not self.session_key:
                            continue
                        try:
                            f = Fernet(self.session_key.encode())
                            jpg = f.decrypt(payload)
                            # decode jpg -> QPixmap
                            image = Image.open(io.BytesIO(jpg)).convert("RGB")
                            data = image.tobytes("raw","RGB")
                            qimg = QtGui.QImage(data, image.width, image.height, QtGui.QImage.Format_RGB888)
                            pix = QtGui.QPixmap.fromImage(qimg)
                            pix = pix.scaled(self.img_label.size(), QtCore.Qt.KeepAspectRatio)
                            QtCore.QMetaObject.invokeMethod(self.img_label, "setPixmap",
                                                            QtCore.Qt.QueuedConnection,
                                                            QtCore.Q_ARG(QtGui.QPixmap, pix))
                        except Exception as e:
                            self.log_msg("Decrypt/display error: " + str(e))
                    else:
                        # unknown binary
                        pass
                else:
                    # text control messages
                    import json
                    try:
                        msg = json.loads(raw)
                    except:
                        continue
                    t = msg.get("type")
                    if t == "incoming":
                        frm = msg.get("from")
                        self.log_msg(f"Incoming connection request from {frm}")
                        self.incoming_from = frm
                        QtCore.QMetaObject.invokeMethod(self.accept_btn, "setEnabled",
                                                        QtCore.Qt.QueuedConnection,
                                                        QtCore.Q_ARG(bool, True))
                    elif t == "session":
                        # receive session key
                        key = msg.get("key")
                        peer = msg.get("peer")
                        self.session_key = key
                        self.peer = peer
                        self.log_msg(f"Session started with {peer}, key received.")
                    elif t == "registered":
                        pass
                    elif t == "error":
                        self.log_msg("Broker error: " + msg.get("error",""))
                    else:
                        # forwarded payload from other client
                        # ex: command messages
                        typ = msg.get("cmd")
                        if typ == "COMMAND":
                            data = msg.get("data")
                            self.handle_command(data)
        except Exception as e:
            self.log_msg("Recv loop ended: " + str(e))

    def request_connect(self):
        target = self.target_input.text().strip()
        if not target:
            self.log_msg("Set target ID.")
            return
        # send connect request
        asyncio.run_coroutine_threadsafe(self.ws.send(json.dumps({"type":"connect","from":cfg["id"],"target":target,"password":""})), self.loop)
        self.log_msg(f"Connect request sent to {target} (via broker).")

    def accept_incoming(self):
        if not self.incoming_from:
            self.log_msg("No incoming.")
            return
        viewer = self.incoming_from
        # send accept to broker (broker will create and distribute session key)
        asyncio.run_coroutine_threadsafe(self.ws.send(json.dumps({"type":"accept","from":cfg["id"],"viewer":viewer})), self.loop)
        self.log_msg(f"Accepted connection from {viewer}. Starting capture soon...")
        # disable accept button
        QtCore.QMetaObject.invokeMethod(self.accept_btn, "setEnabled",
                                        QtCore.Qt.QueuedConnection,
                                        QtCore.Q_ARG(bool, False))
        # start capture loop in background (it will only send after session key arrives)
        threading.Thread(target=self.capture_loop_thread, daemon=True).start()

    def capture_loop_thread(self):
        # run in a thread but use asyncio to send bytes
        with mss.mss() as sct:
            monitor = sct.monitors[1]
            while True:
                if not self.session_key or not self.peer:
                    time.sleep(0.1)
                    continue
                try:
                    frame = np.array(sct.grab(monitor))
                    frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
                    h,w = frame.shape[:2]
                    scale = 0.6
                    small = cv2.resize(frame,(int(w*scale), int(h*scale)))
                    ret, jpg = cv2.imencode('.jpg', small, [cv2.IMWRITE_JPEG_QUALITY,50])
                    if not ret:
                        continue
                    jpg_bytes = jpg.tobytes()
                    f = Fernet(self.session_key.encode())
                    enc = f.encrypt(jpg_bytes)
                    header = f"BINARY|{self.peer}\n".encode()
                    # send binary header+payload
                    fut = asyncio.run_coroutine_threadsafe(self.ws.send(header+enc), self.loop)
                    fut.result(timeout=2)
                    time.sleep(0.04)
                except Exception as e:
                    self.log_msg("Capture send error: " + str(e))
                    time.sleep(0.5)

    def send_command_to_host(self, cmd):
        # util: create forward payload so broker will forward to host
        payload = {"cmd":"COMMAND","data":cmd}
        # send as forward wrapper
        wr = {"type":"forward","from":cfg["id"],"to":self.target_input.text().strip(),"payload":payload}
        asyncio.run_coroutine_threadsafe(self.ws.send(json.dumps(wr)), self.loop)

    def handle_command(self, data):
        # data examples: "MOVE 100 200", "CLICK", "KEY hello"
        try:
            if data.startswith("MOVE"):
                _, x, y = data.split()
                self.mouse.position = (int(x), int(y))
            elif data.startswith("CLICK"):
                self.mouse.click(MouseButton.left, 1)
            elif data.startswith("KEY"):
                text = data[4:]
                self.keyboard.type(text)
            self.log_msg("Executed command: " + data)
        except Exception as e:
            self.log_msg("Command exec error: " + str(e))


if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec_())
