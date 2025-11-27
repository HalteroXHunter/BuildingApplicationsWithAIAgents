import asyncio
import os, json, base64, websockets
from fastapi import FastAPI, WebSocket
from dotenv import load_dotenv

load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
VOICE = "alloy"
PCM_SR = 16000
PORT = 5050

app = FastAPI()


@app.websocket("/voice")
async def voice_bridge(ws: WebSocket) -> None:
    """
    1. browser opens ws://host:5050/voice
    2. browser streams base64-encoded 16-bit mono PCM chunks
    3. we forward chunks to openai realtime
    4. we relay assistant audio deltas back to the browser the same way
    5. we listen for "speech_started" events and send a truncate if user interrupts

    :param ws: Description
    :type ws: WebSocket
    """

    await ws.accept()

    openai_ws = await websockets.connect(
        "wss://api.openai.com/v1/realtime?"
        + "model=gpt-40-realtime-preview-2024-10-01",
        extra_headers={
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "OpenAI-Beta": "realtime=v1",
        },
        max_size=None,
        max_queue=None,
    )

    # initialize the realtime session
    await openai_ws.send(
        json.dumps(
            {
                "type": "session.update",
                "session": {
                    "turn_detection": {"type": "server_vad"},
                    "input_audio_format": f"pcm_{PCM_SR}",
                    "output_audio_format": f"pcm_{PCM_SR}",
                    "voice": VOICE,
                    "modalities": ["audio"],
                    "instructions": "you are a concise AI assistant.",
                },
            }
        )
    )

    last_assistant_item = None
    latest_pcm_ts = 0
    pending_marks = []

    async def from_client() -> None:
        """relay microphone PCM chunks from browser to OpenAI"""
        nonlocal latest_pcm_ts
        async for msg in ws.iter_text():
            data = json.loads(msg)
            pcm = base64.b64decode(data["audio"])
            latest_pcm_ts += int(len(pcm) / (PCM_SR * 2) * 1000)
            await openai_ws.send(
                json.dumps(
                    {
                        "type": "input_audio_buffer.append",
                        "audio": base64.b64encode(pcm).decode("ascii"),
                        "timestamp": latest_pcm_ts,
                    }
                )
            )

    async def to_client() -> None:
        """relay assistant audio + handle interruptions"""
        nonlocal last_assistant_item, pending_marks
        async for raw in openai_ws:
            msg = json.loads(raw)

            # assistant speaks
            if msg["type"] == "response.audio.delta":
                pcm = base64.b64decode(msg["delta"])
                await ws.send_json({"audio": base64.b64encode(pcm).decode("ascii")})
                last_assistant_item = msg.get("item_id")

            # user started talking -> interrupt assistant
            started = "input_audio_buffer.speech_started"
            if msg["type"] == started and last_assistant_item:
                await openai_ws.send(
                    json.dumps(
                        {
                            "type": "conversation.item.truncate",
                            "item_id": last_assistant_item,
                            "context_index": 0,
                            "audio_end_ms": 0,
                        }
                    )
                )

    try:
        await asyncio.gather(from_client(), to_client())
    finally:
        await openai_ws.close()
        await ws.close()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("book_chapters.ch3.voice_chat:app", host="0.0.0.0", port=PORT)
