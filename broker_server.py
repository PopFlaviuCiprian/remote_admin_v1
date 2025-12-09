# broker_server.py
# Broker WebSocket simplu: păstrează clients[id] și forwardează text/binary
import asyncio
import websockets

clients = {}  # id -> websocket

async def handler(ws, path):
    my_id = None
    try:
        init = await ws.recv()
    except websockets.ConnectionClosed:
        return

    # așteptăm mesaj de înregistrare: "REGISTER|<id>"
    if isinstance(init, str) and init.startswith("REGISTER|"):
        my_id = init.split("|",1)[1]
        print(f"[BROKER] REGISTER: {my_id}")
        clients[my_id] = ws
        await ws.send(f"INFO|REGISTERED|{my_id}")
    else:
        await ws.send("ERROR|expected REGISTER")
        return

    try:
        async for msg in ws:
            # Text message forwarding: "COMMAND|TARGET|payload..."
            if isinstance(msg, str):
                parts = msg.split("|", 2)
                if len(parts) >= 2:
                    cmd, target = parts[0], parts[1]
                    payload = parts[2] if len(parts) > 2 else ""
                    if target in clients:
                        try:
                            await clients[target].send(msg)
                        except Exception as e:
                            print(f"[BROKER] Forward text error to {target}: {e}")
                else:
                    # malformed, ignore or log
                    print("[BROKER] Malformed text:", msg[:200])
            else:
                # Binary messages: header\n<payload>
                # header example: b"BINARY|TARGET\n"
                header, sep, payload = msg.partition(b'\n')
                if not sep:
                    print("[BROKER] Binary without header, ignoring")
                    continue
                if header.startswith(b'BINARY|'):
                    target = header.split(b'|',1)[1].decode()
                    if target in clients:
                        try:
                            await clients[target].send(msg)
                        except Exception as e:
                            print(f"[BROKER] Forward binary error to {target}: {e}")
                else:
                    print("[BROKER] Unknown binary header:", header)
    except websockets.ConnectionClosed:
        print(f"[BROKER] ConnectionClosed: {my_id}")
    finally:
        if my_id and my_id in clients and clients[my_id] == ws:
            del clients[my_id]
            print(f"[BROKER] UNREGISTER: {my_id}")

async def main():
    server = await websockets.serve(handler, "0.0.0.0", 9000, max_size=None)
    print("[BROKER] Running on ws://0.0.0.0:9000")
    await server.wait_closed()

if __name__ == "__main__":
    asyncio.run(main())
