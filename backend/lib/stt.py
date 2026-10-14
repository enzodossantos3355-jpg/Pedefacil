"""WhatsApp voice notes → text (OpenAI whisper-1 via the Emergent universal key)."""

import asyncio
import base64
import logging
import os
import tempfile
from pathlib import Path

import imageio_ffmpeg
from emergentintegrations.llm.openai import OpenAISpeechToText

logger = logging.getLogger(__name__)
HALLUCINATIONS = ("amara.org", "legendas pela comunidade", "obrigado por assistir", "inscreva-se no canal", "legenda adriana")


async def transcribe_audio(audio_b64: str) -> str:
    """WhatsApp sends OGG/Opus, which the STT client rejects, so it is converted to mp3 first."""
    with tempfile.TemporaryDirectory() as tmp:
        src, dst = Path(tmp) / "voice.ogg", Path(tmp) / "voice.mp3"
        src.write_bytes(base64.b64decode(audio_b64))
        proc = await asyncio.create_subprocess_exec(
            imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-i", str(src), "-ac", "1", "-ar", "16000", str(dst),
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE,
        )
        _, err = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"ffmpeg: {err.decode()[:200]}")
        stt = OpenAISpeechToText(api_key=os.environ.get("EMERGENT_LLM_KEY", ""))
        with open(dst, "rb") as f:
            res = await stt.transcribe(file=f, model="whisper-1", response_format="json", language="pt", prompt="Pedido de marmita pelo WhatsApp.")
        text = (res.text or "").strip()
        # whisper-1 invents these captions on silence/noise; treat them as "not understood"
        return "" if any(h in text.lower() for h in HALLUCINATIONS) else text
