import datetime
import json
import uuid

import uvicorn
from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from discord_webhook import DiscordWebhook, DiscordEmbed
from fastapi.responses import FileResponse

app = FastAPI()

with open('config.json', 'r') as file:
    config = json.load(file)

sessions: dict[str, dict] = {}


def send_webhook(title: str, message: str, color: str):
    webhook = DiscordWebhook(url=config["discord_webhook_url"])

    embed = DiscordEmbed(title=title, description=message, color=color)
    webhook.add_embed(embed)

    webhook.execute()


@app.get("/")
async def create_session(request: Request, background_tasks: BackgroundTasks):
    if request.client.host in config["blacklisted_addresses"]:
        background_tasks.add_task(send_webhook,
                                  f"{request.client.host}:{request.client.port}",
                                  f"Connection from blacklisted address",
                                  "#FF0000")
        return HTTPException(status_code=404)

    if request.client.host in sessions.keys():
        if (datetime.datetime.now() - sessions[request.client.host]["last_action"]).seconds < config[
            "idle_session_lifespan"]:
            background_tasks.add_task(send_webhook,
                                      f"{request.client.host}:{request.client.port}",
                                      f"New session request during active one",
                                      "#FF0000")
            return HTTPException(status_code=404)
        sessions.pop(request.client.host)

    session_id = str(uuid.uuid1())

    sessions[request.client.host] = {
        "last_action": datetime.datetime.now(),
        "session_id": session_id
    }

    background_tasks.add_task(send_webhook,
                              f"{request.client.host}:{request.client.port}",
                              f"New session created",
                              "#00FF00")

    return session_id


@app.get("/{session_id}/{license}")
async def get_library(session_id: str, license: str, request: Request, background_tasks: BackgroundTasks):
    if request.client.host not in sessions.keys():
        background_tasks.add_task(send_webhook,
                                  f"{request.client.host}:{request.client.port}",
                                  f"Plugin download attempt without session - {license}",
                                  "#FF0000")
        return HTTPException(status_code=404)

    if sessions[request.client.host]["session_id"] != session_id:
        background_tasks.add_task(send_webhook,
                                  f"{request.client.host}:{request.client.port}",
                                  f"Plugin download attempt with wrong session_id - {license}",
                                  "#FF0000")
        return HTTPException(status_code=404)

    if (datetime.datetime.now() - sessions[request.client.host]["last_action"]).seconds >= config[
        "idle_session_lifespan"]:
        background_tasks.add_task(send_webhook,
                                  f"{request.client.host}:{request.client.port}",
                                  f"Plugin download attempt with inactive session - {license}",
                                  "#FF0000")
        return HTTPException(status_code=404)

    if license not in config["licenses"]:
        background_tasks.add_task(send_webhook,
                                  f"{request.client.host}:{request.client.port}",
                                  f"Plugin download attempt with wrong license - {license}",
                                  "#FF0000")
        sessions.pop(request.client.host)
        return HTTPException(status_code=404)

    if request.client.host not in config["licenses"][license]["addresses"]:
        background_tasks.add_task(send_webhook,
                                  f"{request.client.host}:{request.client.port}",
                                  f"Plugin download attempt from wrong address - {license}",
                                  "#FF0000")
        sessions.pop(request.client.host)
        return HTTPException(status_code=404)

    if request.client.port not in config["licenses"][license]["addresses"][request.client.host]:
        background_tasks.add_task(send_webhook,
                                  f"{request.client.host}:{request.client.port}",
                                  f"Plugin download attempt from wrong port - {license}",
                                  "#FF0000")
        sessions.pop(request.client.host)
        return HTTPException(status_code=404)

    background_tasks.add_task(send_webhook,
                              f"{request.client.host}:{request.client.port}",
                              f"Plugin download successful - {license}",
                              "#00FF00")

    sessions[request.client.host]["last_action"] = datetime.datetime.now()

    return FileResponse(config["licenses"][license]["library"])


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
