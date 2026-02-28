import sounddevice as sd
import numpy as np

SAMPLE_RATE = 44100
AUDIO_DTYPE = 'float32'

def get_audio_stream():
    # Создаем дуплексный поток (вход/выход)
    stream = sd.RawStream(samplerate=SAMPLE_RATE, channels=1, dtype=AUDIO_DTYPE)
    stream.start()
    return stream

def play(stream, audio_bytes):
    # Записываем байты напрямую в поток воспроизведения
    if stream:
        stream.write(audio_bytes)

def record(stream, frames):
    # Читаем данные из микрофона
    if stream:
        data, overflowed = stream.read(frames)
        return data # Возвращает bytes
    return b''