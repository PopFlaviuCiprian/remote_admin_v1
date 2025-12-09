# viewer.py
import asyncio
import websockets

BROKER = "ws://IP_SERVER:9000"    # același IP ca în host.py
MY_ID = "PC_VIEWER"               # ID-ul acestui PC
TARGET = "PC_HOST"                # ID-ul host-ului

async def viewer():
    async with websockets.connect(BROKER) as ws:
        await ws.send(f"REGISTER|{MY_ID}|")
        print("VIEWER înregistrat.")

        # cerere conectare către host
        await ws.send(f"CONNECT|{MY_ID}|{TARGET}")
        print(f"Conectare către {TARGET}...")

        while True:
            # primește mesaje de la host
            msg = await ws.recv()
            parts = msg.split("|")

            if parts[0] == "DATA":
                host_id = parts[1]
                data = parts[2]
                print(f"[Mesaj de la {host_id}] {data}")

            # trimit mesaj de test
            cmd = input("Trimite comandă către HOST: ")
            await ws.send(f"FORWARD|{MY_ID}|{TARGET}:{cmd}")

asyncio.run(viewer())
