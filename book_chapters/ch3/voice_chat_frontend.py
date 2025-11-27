import streamlit as st
from streamlit_webrtc import webrtc_streamer, AudioProcessorBase, WebRtcMode
import av
import asyncio
import websockets
import base64
import json
import threading
import queue


st.title("Voice Chat with OpenAI (WebSocket Demo)")

# User can specify backend URL
default_url = "ws://localhost:5050/voice"
WS_URL = st.text_input("Backend WebSocket URL", value=default_url)

st.markdown(
    """
**Instructions:**
1. Start your FastAPI backend (`voice_chat.py`).
2. Ensure the backend is accessible at the URL above.
3. Click 'Connect' and allow microphone access.
4. Speak and listen for AI responses!
"""
)


# Thread-safe queues for audio streaming
to_server_q = queue.Queue()
from_server_q = queue.Queue()


# Audio processor to capture microphone audio


class AudioProcessor(AudioProcessorBase):
    def recv(self, frame: av.AudioFrame) -> av.AudioFrame:
        pcm = frame.to_ndarray().tobytes()
        to_server_q.put(base64.b64encode(pcm).decode("ascii"))
        return frame


def ws_client(ws_url):
    async def run():
        try:
            async with websockets.connect(ws_url) as ws:
                # Start a task to send audio to server
                async def send_audio():
                    while True:
                        audio_b64 = await asyncio.get_event_loop().run_in_executor(
                            None, to_server_q.get
                        )
                        await ws.send(json.dumps({"audio": audio_b64}))

                # Start a task to receive audio from server
                async def recv_audio():
                    async for msg in ws:
                        data = json.loads(msg)
                        if "audio" in data:
                            from_server_q.put(data["audio"])

                await asyncio.gather(send_audio(), recv_audio())
        except Exception as e:
            from_server_q.put(f"__ERROR__:{e}")

    asyncio.run(run())


def start_ws_thread(ws_url):
    thread = threading.Thread(target=ws_client, args=(ws_url,), daemon=True)
    thread.start()


# Start WebSocket client thread
if st.button("Connect"):
    start_ws_thread(WS_URL)
    st.session_state["ws_connected"] = True
    st.success("Connecting to backend... Allow microphone and start speaking!")


# Start audio stream
webrtc_ctx = webrtc_streamer(
    key="voice-chat",
    mode=WebRtcMode.SENDONLY,
    audio_receiver_size=1024,
    audio_processor_factory=AudioProcessor,
    media_stream_constraints={"audio": True, "video": False},
    async_processing=True,
)

# Playback received audio (very basic, for demo)
if not from_server_q.empty():
    audio_b64 = from_server_q.get()
    if audio_b64.startswith("__ERROR__:"):
        st.error(f"WebSocket error: {audio_b64[10:]}")
    else:
        audio_bytes = base64.b64decode(audio_b64)
        st.audio(audio_bytes, format="audio/wav")

st.info(
    "This is a minimal demo. For production, use a more robust audio streaming and playback approach."
)
