# broker_server.py
import asyncio, json, secrets
import websockets

PORT = 9000
clients = {}   # id -> {"ws": websocket, "passwd": "...", "info": {...}}

async def handler(ws, path):
    my_id = None
    try:
        async for raw in ws:
            # text messages only for broker control (clients send JSON lines)
            try:
                msg = json.loads(raw)
            except Exception:
                continue

            typ = msg.get("type")
            if typ == "register":
                my_id = msg["id"]
                clients[my_id] = {"ws": ws, "passwd": msg.get("password"), "info": msg.get("info", {})}
                print(f"[BROKER] REGISTER {my_id}")
                await ws.send(json.dumps({"type":"registered","id":my_id}))
            elif typ == "connect":
                # viewer requests connection to target host
                viewer = msg["from"]
                target = msg["target"]
                passwd = msg.get("password", "")
                if target in clients:
                    print(f"[BROKER] {viewer} requests connect -> {target}")
                    await clients[target]["ws"].send(json.dumps({"type":"incoming","from":viewer}))
                else:
                    await ws.send(json.dumps({"type":"error","error":"target_not_online"}))
            elif typ == "accept":
                # host accepts connection request from viewer
                host = msg["from"]
                viewer = msg["viewer"]
                # create session key (Fernet) - demo: symmetric key distributed by broker
                from cryptography.fernet import Fernet
                session_key = Fernet.generate_key().decode()
                print(f"[BROKER] Session key for {host}<->{viewer} created.")
                # send session key to host and viewer
                if viewer in clients and host in clients:
                    await clients[viewer]["ws"].send(json.dumps({"type":"session","key":session_key,"peer":host}))
                    await clients[host]["ws"].send(json.dumps({"type":"session","key":session_key,"peer":viewer}))
                else:
                    if host in clients:
                        await clients[host]["ws"].send(json.dumps({"type":"error","error":"viewer_not_online"}))
            elif typ == "forward":
                # generic forward text: {type: "forward", from:, to:, payload: {...}}
                to = msg.get("to")
                if to in clients:
                    await clients[to]["ws"].send(json.dumps(msg.get("payload")))
            elif typ == "list":
                # debug: return list of online ids
                ids = list(clients.keys())
                await ws.send(json.dumps({"type":"list","ids":ids}))
    except websockets.ConnectionClosed:
        pass
    finally:
        if my_id and my_id in clients and clients[my_id]["ws"] == ws:
            del clients[my_id]
            print(f"[BROKER] UNREGISTER {my_id}")

async def main():
    print(f"[BROKER] running on :{PORT}")
    async with websockets.serve(handler,"0.0.0.0",PORT, max_size=None):
        await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())
