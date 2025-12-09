# broker_server.py
import asyncio
import websockets

clients = {}  # client_id -> websocket

async def handler(websocket):
    while True:
        try:
            message = await websocket.recv()
        except:
            # dacă se deconectează un client, îl ștergem
            for cid, ws in list(clients.items()):
                if ws == websocket:
                    del clients[cid]
            break

        parts = message.split("|", 2)
        cmd = parts[0]

        # --------------- CLIENTUL SE ÎNREGISTREAZĂ ----------------
        if cmd == "REGISTER":
            client_id = parts[1]
            clients[client_id] = websocket
            print(f"[REGISTER] {client_id} conectat.")

        # --------------- VIEWER CERE CONECTAREA ----------------
        elif cmd == "CONNECT":
            viewer_id = parts[1]
            target_id = parts[2]

            if target_id in clients:
                await clients[target_id].send(f"REQUEST|{viewer_id}|")

        # --------------- MESAJ BIDIRECȚIONAL ----------------
        elif cmd == "FORWARD":
            sender_id = parts[1]
            rest = parts[2]
            target_id, data = rest.split(":", 1)

            if target_id in clients:
                await clients[target_id].send(f"DATA|{sender_id}|{data}")

async def main():
    print("Broker server pornit pe portul 9000...")
    async with websockets.serve(handler, "0.0.0.0", 9000):
        await asyncio.Future()  # rulează la infinit

asyncio.run(main())
