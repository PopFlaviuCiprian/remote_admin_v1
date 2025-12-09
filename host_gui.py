# host.py
import asyncio
import websockets

BROKER = "ws://IP_SERVER:9000"   # aici pui IP-ul brokerului
MY_ID = "PC_HOST"                # ID unic pt acest PC

async def host():
    async with websockets.connect(BROKER) as ws:
        await ws.send(f"REGISTER|{MY_ID}|")
        print("HOST înregistrat la broker.")

        while True:
            msg = await ws.recv()
            parts = msg.split("|")

            if parts[0] == "REQUEST":
                viewer_id = parts[1]
                print(f"Cerere de conectare de la: {viewer_id}")

            elif parts[0] == "DATA":
                sender_id = parts[1]
                data = parts[2]
                print(f"[Comandă de la {sender_id}] {data}")

                # aici poți executa comenzi reale (ex: control mouse, tastatură)

asyncio.run(host())
