import datetime
import json
import uuid

import uvicorn
from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from discord_webhook import DiscordWebhook
from fastapi.responses import FileResponse

app = FastAPI()

with open('config.json', 'r') as file:
    config = json.load(file)

sessions: dict[str, dict] = {}


def send_webhook(message: str):
    DiscordWebhook(url=config["discord_webhook_url"], content=message).execute()


@app.get("/")
async def create_session(request: Request, background_tasks: BackgroundTasks):
    if request.client.host in config["blacklisted_addresses"]:
        background_tasks.add_task(send_webhook,
                                  f"Connection from blacklisted address - {request.client.host}:{request.client.port}")
        raise HTTPException(status_code=404)

    if request.client.host in sessions.keys():
        if (datetime.datetime.now() - sessions[request.client.host]["last_action"]).seconds < config[
            "idle_session_lifespan"]:
            background_tasks.add_task(send_webhook,
                                      f"New session request during active one - {request.client.host}:{request.client.port}")
            raise HTTPException(status_code=404)
        sessions.pop(request.client.host)

    session_id = uuid.uuid1()

    sessions[request.client.host] = {
        "last_action": datetime.datetime.now(),
        "session_id": session_id
    }

    background_tasks.add_task(send_webhook, f"New session created - {request.client.host}:{request.client.port}")

    return session_id


@app.get("/{session_id}/{license}")
async def get_library(session_id: str, license: str, request: Request, background_tasks: BackgroundTasks):
    if request.client.host not in sessions.keys():
        background_tasks.add_task(send_webhook,
                                  f"Plugin download attempt without session - {request.client.host}:{request.client.port}/{license}")
        raise HTTPException(status_code=404)

    if sessions[request.client.host]["session_id"] != session_id:
        background_tasks.add_task(send_webhook,
                                  f"Plugin download attempt with wrong session_id - {request.client.host}:{request.client.port}/{license}")
        raise HTTPException(status_code=404)

    if (datetime.datetime.now() - sessions[request.client.host]["last_action"]).seconds >= config[
        "idle_session_lifespan"]:
        background_tasks.add_task(send_webhook,
                                  f"Plugin download attempt with inactive session - {request.client.host}:{request.client.port}/{license}")
        sessions.pop(request.client.host)
        raise HTTPException(status_code=404)

    if license not in config["licenses"]:
        background_tasks.add_task(send_webhook,
                                  f"Plugin download attempt with wrong license - {request.client.host}:{request.client.port}/{license}")
        sessions.pop(request.client.host)
        raise HTTPException(status_code=404)

    if request.client.host not in config["licenses"][license]["addresses"]:
        background_tasks.add_task(send_webhook,
                                  f"Plugin download attempt from wrong address - {request.client.host}:{request.client.port}/{license}")
        sessions.pop(request.client.host)
        raise HTTPException(status_code=404)

    if request.client.port not in config["licenses"][license]["addresses"][request.client.host]:
        background_tasks.add_task(send_webhook,
                                  f"Plugin download attempt from wrong port - {request.client.host}:{request.client.port}/{license}")
        sessions.pop(request.client.host)
        raise HTTPException(status_code=404)

    background_tasks.add_task(send_webhook,
                              f"Plugin download successful- {request.client.host}:{request.client.port}/{license}")

    return FileResponse(config["licenses"]["library"])


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
