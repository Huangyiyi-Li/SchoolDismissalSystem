"""Windows speech playback with explicit SAPI completion and cancellation."""
import math


class WindowsSapiEngine:
    def __init__(self, stop_event):
        # Create and use the COM object exclusively in the TTS worker thread.
        from win32com.client import Dispatch
        self.voice = Dispatch("SAPI.SpVoice")
        self.stop_event = stop_event

    def setProperty(self, name, value):
        if name == "volume":
            self.voice.Volume = min(100, max(0, round(value * 100)))
        elif name == "rate":
            # Preserve the WPM-to-SAPI mapping used for Microsoft voices by
            # pyttsx3. Zero/default is handled by the caller without overriding
            # the system voice's speed.
            self.voice.Rate = min(10, max(-10, int(math.log(value / 156.63, 1.11))))
        else:
            raise ValueError(f"Unsupported Windows speech property: {name}")

    def say(self, text):
        # Async + literal text; school/class names must not be interpreted as XML.
        self.voice.Speak(text, 1 | 16)

    def runAndWait(self):
        while not self.voice.WaitUntilDone(100):
            if self.stop_event.is_set():
                self.stop()
                return

    def stop(self):
        self.voice.Speak("", 1 | 2)
