"""One-off check that Kokoro writes a playable WAV. First run downloads the model."""

import numpy as np
import soundfile as sf
from kokoro import KPipeline

pipeline = KPipeline(lang_code="a", repo_id="hexgrad/Kokoro-82M")
text = "Hello, this is a test. Does it pause correctly? Yes... it does!"
chunks = []
for _, _, audio in pipeline(text, voice="af_heart", speed=1.0):
    chunks.append(np.asarray(audio, dtype=np.float32).reshape(-1))
sf.write("test.wav", np.concatenate(chunks), 24000)
print("Saved test.wav")
