# viewer_gui.py
import sys, asyncio, threading, io
from PyQt5 import QtWidgets, QtGui, QtCore
from PyQt5.QtWidgets import QApplication, QLabel, QPushButton, QVBoxLayout, QWidget, QLineEdit, QTextEdit
import websockets
from PIL import Image

# EDITEAZĂ aici cu adresa broker-ului
BROKER_URL = "ws://SERVER_IP:9000"

class ViewerWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Remote Viewer")
        self.setGeometry(100,100,900,650)
        layout = QVBoxLayout()

        self.my_id_input = QLineEdit()
        self.my_id_input.setPlaceholderText("ID viewer (ex: viewer-1)")
        layout.addWidget(self.my_id_input)

        self.target_input = QLineEdit()
        self.target_input.setPlaceholderText("ID host (ex: host-123)")
        layout.addWidget(self.target_input)

        self.connect_btn = QPushButton("Request Connect")
        self.connect_btn.clicked.connect(self.start)
        layout.addWidget(self.connect_btn)

        self.img_label = QLabel("Remote screen will appear here")
        self.img_label.setAlignment(QtCore.Qt.AlignCenter)
        self.img_label.setFixedSize(860,480)
        layout.addWidget(self.img_label, stretch=1)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        layout.addWidget(self.log)

        self.setLayout(layout)
        self.loop = None
        self.ws = None

    def log_msg(self, t):
        self.log.append(t)

    def start(self):
        threading.Thread(target=self.run_loop, daemon=True).start()
        self.connect_btn.setEnabled(False)

    def run_loop(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self.async_main())

    async def async_main(self):
        my_id = self.my_id_input.text().strip()
        target = self.target_input.text().strip()
        if not my_id or not target:
            self.log_msg("Completează ambele ID-uri.")
            self.connect_btn.setEnabled(True)
            return

        try:
            async with websockets.connect(BROKER_URL, max_size=None) as ws:
                self.ws = ws
                await ws.send(f"REGISTER|{my_id}")
                self.log_msg("Înregistrat ca " + my_id)
                # Trimitem cererea de conectare către host (prin broker)
                # Format: COMMAND|<host_id>|REQUEST_CONNECT|<viewer_id>
                await ws.send(f"COMMAND|{target}|REQUEST_CONNECT|{my_id}")
                self.log_msg(f"Cerere trimisă către {target}, aștept ACCEPT.")

                async for msg in ws:
                    if isinstance(msg, bytes):
                        # așteptăm format: header\njpeg
                        header, sep, payload = msg.partition(b'\n')
                        if header.startswith(b'BINARY|'):
                            # verificăm că header este pentru noi
                            header_target = header.split(b'|',1)[1].decode()
                            # header_target ar trebui să fie my_id
                            if header_target != my_id:
                                # nu e pentru noi - ignora
                                continue
                            # payload = jpeg bytes
                            try:
                                image = Image.open(io.BytesIO(payload))
                                image = image.convert("RGB")
                                # convert la QPixmap
                                data = image.tobytes("raw","RGB")
                                qimg = QtGui.QImage(data, image.width, image.height, QtGui.QImage.Format_RGB888)
                                pix = QtGui.QPixmap.fromImage(qimg)
                                # scalăm pentru label
                                pix = pix.scaled(self.img_label.size(), QtCore.Qt.KeepAspectRatio)
                                # setăm pixmap din thread UI
                                QtCore.QMetaObject.invokeMethod(self.img_label, "setPixmap",
                                                                QtCore.Qt.QueuedConnection,
                                                                QtCore.Q_ARG(QtGui.QPixmap, pix))
                            except Exception as e:
                                self.log_msg("Eroare decodare imagine: " + str(e))
                        else:
                            # text forwarded as bytes (rare) -> decode
                            try:
                                txt = msg.decode()
                                self.log_msg("Text binar->text: " + txt)
                            except:
                                pass
                    else:
                        # text message
                        parts = msg.split("|")
                        # ex: INFO|<viewer_id>|ACCEPTED|<host_id>
                        if len(parts) >= 3 and parts[0] == "INFO":
                            # INFO|viewer-1|ACCEPTED|host-123
                            info_type = parts[2] if len(parts) > 2 else ""
                            if parts[1] == my_id and info_type == "ACCEPTED":
                                host_id = parts[3] if len(parts) > 3 else "?"
                                self.log_msg(f"Conexiune ACCEPTED de la {host_id}. Începem afișarea cadrului.")
                            else:
                                self.log_msg("INFO: " + msg)
                        else:
                            self.log_msg("Mesaj text: " + msg)
        except Exception as e:
            self.log_msg("Eroare viewer: " + str(e))
        finally:
            self.connect_btn.setEnabled(True)
