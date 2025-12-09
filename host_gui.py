# host_gui.py
import sys, asyncio, threading, io
from PyQt5 import QtWidgets, QtCore
from PyQt5.QtWidgets import QApplication, QLabel, QPushButton, QVBoxLayout, QWidget, QLineEdit, QTextEdit
import mss
import cv2
import numpy as np
import websockets

# EDITEAZĂ aici cu adresa broker-ului (sau folosește ws://localhost:9000 pentru test local)
BROKER_URL = "ws://SERVER_IP:9000"

MY_ID = None

class HostWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Remote Host (Host)")
        self.setGeometry(300,300,420,240)
        layout = QVBoxLayout()

        self.id_input = QLineEdit()
        self.id_input.setPlaceholderText("Introduceți ID-ul host (ex: host-123)")
        layout.addWidget(self.id_input)

        self.start_btn = QPushButton("Start Host")
        self.start_btn.clicked.connect(self.start_host)
        layout.addWidget(self.start_btn)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        layout.addWidget(self.log)

        self.setLayout(layout)

        self.ws = None
        self.loop = None
        self.target_viewer = None
        self.sending = False

    def log_msg(self, t):
        self.log.append(t)

    def start_host(self):
        global MY_ID
        MY_ID = self.id_input.text().strip()
        if not MY_ID:
            self.log_msg("Setează un ID valid.")
            return
        self.start_btn.setEnabled(False)
        self.log_msg(f"Pornire host cu ID: {MY_ID}")
        threading.Thread(target=self.run_async_loop, daemon=True).start()

    def run_async_loop(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self.async_main())

    async def async_main(self):
        uri = BROKER_URL
        try:
            async with websockets.connect(uri, max_size=None) as ws:
                self.ws = ws
                await ws.send(f"REGISTER|{MY_ID}")
                self.log_msg("Conectat la broker.")
                # pornim recv task și (la nevoie) capture task
                recv_task = asyncio.create_task(self.recv_loop())
                await recv_task
        except Exception as e:
            self.log_msg("Eroare broker: " + str(e))
        finally:
            self.start_btn.setEnabled(True)
            self.sending = False

    async def recv_loop(self):
        try:
            async for msg in self.ws:
                if isinstance(msg, str):
                    # format text: COMMAND|TARGET|PAYLOAD...
                    parts = msg.split("|", 3)
                    if len(parts) >= 3:
                        cmd = parts[0]
                        target = parts[1]
                        payload = parts[2] if len(parts) > 2 else ""
                        # ne interesează doar COMMAND adresate host-ului (target == MY_ID)
                        if target != MY_ID:
                            continue

                        # cerere de conectare: REQUEST_CONNECT|<viewer_id>
                        if cmd == "COMMAND" and payload.startswith("REQUEST_CONNECT"):
                            # payload poate fi "REQUEST_CONNECT|viewer-1" (dacă avem un al 4-lea segment)
                            # acceptăm cererea si setăm target_viewer
                            # suportăm și formatul: COMMAND|host|REQUEST_CONNECT|viewer-1
                            if len(parts) >= 4:
                                viewer_id = parts[3]
                            else:
                                # payload contine viewer id dupa spatiu
                                seg = payload.split("|")
                                viewer_id = seg[1] if len(seg) > 1 else None

                            if viewer_id:
                                self.target_viewer = viewer_id
                                self.log_msg(f"Primita cerere CONNECT de la {viewer_id} — acceptată (demo).")
                                # anunțăm viewer că am acceptat
                                await self.ws.send(f"INFO|{viewer_id}|ACCEPTED|{MY_ID}")
                                # pornesc trimiterea de cadre dacă nu e deja pornită
                                if not self.sending:
                                    self.sending = True
                                    asyncio.create_task(self.capture_loop())
                            else:
                                self.log_msg("Request connect malformed.")
                        elif cmd == "COMMAND":
                            # alte comenzi (ex: MOVE, CLICK) pot fi procesate aici
                            self.log_msg(f"COMMAND pentru host: {payload}")
                    else:
                        self.log_msg("Mesaj text neasteptat: " + msg[:200])
                else:
                    # broker forwardă binare și host nu așteaptă binare
                    pass
        except Exception as e:
            self.log_msg("Recv loop error: " + str(e))

    async def capture_loop(self):
        if not self.target_viewer:
            self.log_msg("Nu există viewer setat, aștept cerere.")
            return
        self.log_msg(f"Trimitem cadre către: {self.target_viewer}")
        with mss.mss() as sct:
            monitor = sct.monitors[1]
            while self.sending and self.target_viewer:
                try:
                    frame = np.array(sct.grab(monitor))
                    frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
                    # scaling pentru bandă
                    h, w = frame.shape[:2]
                    scale = 0.6
                    frame_small = cv2.resize(frame, (int(w*scale), int(h*scale)))
                    ret, jpg = cv2.imencode('.jpg', frame_small, [cv2.IMWRITE_JPEG_QUALITY, 50])
                    if not ret:
                        await asyncio.sleep(0.05)
                        continue
                    data = jpg.tobytes()
                    header = f"BINARY|{self.target_viewer}\n".encode()
                    # trimitem header + jpeg ca mesaj binar
                    await self.ws.send(header + data)
                    await asyncio.sleep(0.04)  # ~25 FPS teoretic
                except Exception as e:
                    self.log_msg("Eroare trimitere frame: " + str(e))
                    break
        self.log_msg("Capture loop ended.")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = HostWindow()
    w.show()
    sys.exit(app.exec_())
