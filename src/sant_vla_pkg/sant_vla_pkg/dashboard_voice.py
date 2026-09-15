"""Bounded microphone capture and CPU Whisper decoding off the Qt thread."""
import os
import threading

import numpy as np
from PySide6.QtCore import QObject, QTimer, Signal


class VoiceInput(QObject):
    text_ready = Signal(int, str)
    error = Signal(str)
    state_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.stream = None
        self.frames = []
        self.samples = 0
        self.model = None
        self.busy = False
        self.closed = False
        self.generation = 0
        self.limit = QTimer(self)
        self.limit.setSingleShot(True)
        self.limit.timeout.connect(self.finish)

    def toggle(self):
        if self.busy:
            return
        if self.stream is not None:
            self.finish()
            return
        try:
            import sounddevice as sd
            self.frames = []
            self.samples = 0
            def callback(data, _frames, _time, _status):
                if self.samples < 16000*30:
                    self.frames.append(data.copy())
                    self.samples += len(data)
            self.stream = sd.InputStream(samplerate=16000, channels=1,
                                         dtype="float32", callback=callback)
            self.stream.start()
            self.limit.start(30000)
            self.state_changed.emit("녹음 종료")
        except Exception as exc:
            self.cancel()
            self.error.emit(f"마이크를 열 수 없습니다: {exc}")

    def finish(self):
        if self.stream is None:
            return
        self.limit.stop()
        self.stream.stop()
        self.stream.close()
        self.stream = None
        audio = np.concatenate(self.frames).reshape(-1) if self.frames else np.array([])
        self.frames = []
        if len(audio) < 1600:
            self.state_changed.emit("음성 입력")
            self.error.emit("녹음된 음성이 너무 짧습니다.")
            return
        self.busy = True
        generation = self.generation
        self.state_changed.emit("음성 변환 중…")
        def decode():
            try:
                from faster_whisper import WhisperModel
                if self.model is None:
                    self.model = WhisperModel(os.environ.get("SANT_VLA_WHISPER_MODEL", "base"),
                                              device="cpu", compute_type="int8")
                segments,_ = self.model.transcribe(audio, beam_size=3, vad_filter=True, language="ko")
                text = " ".join(s.text.strip() for s in segments).strip()
                from sant_vla_pkg.chat_gui_node import ChatGuiWindow
                text = ChatGuiWindow._normalize_voice_text(text)
                if not self.closed and generation == self.generation:
                    self.text_ready.emit(generation, text)
            except Exception as exc:
                if not self.closed and generation == self.generation:
                    self.error.emit(f"음성 인식 실패: {exc}")
            finally:
                self.busy = False
                if not self.closed:
                    self.state_changed.emit("음성 입력")
        threading.Thread(target=decode, daemon=True).start()

    def cancel(self):
        self.generation += 1
        self.limit.stop()
        if self.stream is not None:
            self.stream.stop()
            self.stream.close()
            self.stream = None
        self.frames = []
        if not self.closed:
            self.state_changed.emit("음성 입력")

    def close(self):
        self.closed = True
        self.cancel()
