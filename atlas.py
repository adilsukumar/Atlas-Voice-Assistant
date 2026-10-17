"""Atlas: a small voice or text assistant with explicit, testable actions."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
import os
import re
import smtplib
import ssl
import subprocess
from email.message import EmailMessage
from urllib.parse import quote_plus
import webbrowser


@dataclass(frozen=True)
class Action:
    kind: str
    value: str = ""


def has_wake_word(text: str) -> bool:
    return bool(re.search(r"\batlas\b", text, re.IGNORECASE))


def parse_command(text: str) -> Action:
    query = " ".join(text.strip().lower().split())
    query = re.sub(r"^(?:(?:hey|hi|hello|okay|ok)\s+)?atlas[,:]?\s*", "", query)
    if not query:
        return Action("say", "Hello. What would you like to do?")
    if query in {"exit", "quit", "goodbye", "bye forever"}:
        return Action("exit")
    if query in {"sleep", "go to sleep", "sleep mode"}:
        return Action("sleep")
    if query in {"time", "what is the time", "what is the time now", "what's the time"}:
        return Action("time")
    if query in {"day", "date", "what is the day", "what is the day today", "what is the date"}:
        return Action("date")
    if query in {"word", "open word", "open word document"}:
        return Action("app", "winword")
    if query in {"excel", "open excel", "open excel document"}:
        return Action("app", "excel")
    if query == "open youtube":
        return Action("url", "https://www.youtube.com/")
    for prefix in ("search wikipedia ", "who is ", "what is "):
        if query.startswith(prefix) and query[len(prefix):].strip():
            return Action("wiki", query[len(prefix):].strip())
    for prefix in ("search google ", "search for ", "search "):
        if query.startswith(prefix) and query[len(prefix):].strip():
            return Action("url", "https://www.google.com/search?q=" + quote_plus(query[len(prefix):]))
    if query in {"joke", "tell me a joke"}:
        return Action("joke")
    if query in {"hello", "hi", "hey", "how are you"}:
        return Action("say", "Hello. I'm ready to help.")
    return Action("unknown")


def execute(action: Action, *, dry_run: bool = False) -> str:
    if action.kind == "time":
        return datetime.now().strftime("The time is %H:%M.")
    if action.kind == "date":
        return datetime.now().strftime("Today is %A, %d %B %Y.")
    if action.kind in {"exit", "sleep", "say"}:
        return {"exit": "Goodbye.", "sleep": "Sleeping. Say Atlas to wake me."}.get(action.kind, action.value)
    if action.kind == "url":
        if not dry_run:
            webbrowser.open(action.value)
        return f"{'Would open' if dry_run else 'Opening'} {action.value}"
    if action.kind == "app":
        if dry_run:
            return f"Would open {action.value}."
        if os.name != "nt":
            return "Office launch is supported on Windows only."
        # Only the fixed allow-listed applications above can reach this branch.
        if action.value not in {"winword", "excel"}:
            raise ValueError("Unsupported application")
        subprocess.Popen([os.environ.get("COMSPEC", "cmd.exe"), "/c", "start", "", action.value])
        return f"Opening {action.value}."
    if action.kind == "wiki":
        if dry_run:
            return f"Would search Wikipedia for {action.value}."
        try:
            import wikipedia
            wikipedia.set_user_agent("AtlasVoiceAssistant/1.0 (personal educational project)")
            return wikipedia.summary(action.value, sentences=3, auto_suggest=False)
        except ImportError:
            return "Install requirements-voice.txt to enable Wikipedia lookup."
        except Exception:
            return "Wikipedia could not return an unambiguous result. Try a more specific name."
    if action.kind == "joke":
        if dry_run:
            return "Would tell a joke."
        try:
            import pyjokes
            return pyjokes.get_joke()
        except ImportError:
            return "Why do programmers prefer dark mode? Because light attracts bugs."
    return "I didn't understand. Try time, date, open YouTube, search, Wikipedia, sleep or exit."


def send_email(receiver: str, subject: str, message: str) -> None:
    """Explicit library helper; never called automatically from recognized speech."""
    sender = os.environ.get("ATLAS_EMAIL_ADDRESS", "")
    password = os.environ.get("ATLAS_EMAIL_PASSWORD", "")
    host = os.environ.get("ATLAS_SMTP_HOST", "smtp.gmail.com")
    if not sender or not password:
        raise ValueError("Set ATLAS_EMAIL_ADDRESS and ATLAS_EMAIL_PASSWORD before sending email")
    if not re.fullmatch(r"[^\s@<>\r\n]+@[^\s@<>\r\n]+\.[^\s@<>\r\n]+", receiver):
        raise ValueError("A valid explicit recipient address is required")
    if "\n" in subject or "\r" in subject:
        raise ValueError("Email subject cannot contain newlines")
    mail = EmailMessage()
    mail["From"], mail["To"], mail["Subject"] = sender, receiver, subject
    mail.set_content(message)
    with smtplib.SMTP(host, int(os.environ.get("ATLAS_SMTP_PORT", "587")), timeout=15) as server:
        server.starttls(context=ssl.create_default_context())
        server.login(sender, password)
        server.send_message(mail)


class Voice:
    def __init__(self) -> None:
        try:
            import speech_recognition as sr
            import pyttsx3
            self.sr = sr
            self.recognizer = sr.Recognizer()
            self.microphone = sr.Microphone()
            self.engine = pyttsx3.init()
            self.engine.setProperty("rate", 150)
        except (ImportError, OSError, AttributeError) as error:
            raise RuntimeError("Voice setup unavailable. Install requirements-voice.txt or use --text.") from error

    def listen(self) -> str:
        with self.microphone as source:
            self.recognizer.adjust_for_ambient_noise(source, duration=0.3)
            audio = self.recognizer.listen(source, timeout=8, phrase_time_limit=12)
        return self.recognizer.recognize_google(audio, language="en-IN").lower()

    def speak(self, text: str) -> None:
        self.engine.say(text)
        self.engine.runAndWait()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--text", action="store_true", help="Use terminal input; no microphone or optional libraries")
    parser.add_argument("--dry-run", action="store_true", help="Describe external actions without executing them")
    parser.add_argument("--once", help="Process one text command and exit; never initializes the microphone")
    args = parser.parse_args()
    if args.once is not None:
        print(execute(parse_command(args.once), dry_run=args.dry_run))
        return 0
    try:
        voice = None if args.text else Voice()
    except RuntimeError as error:
        parser.exit(2, str(error) + "\n")
    print("Atlas ready. Voice recognition uses Google's online service." if voice else "Atlas text mode. Type exit to stop.")
    sleeping = False
    while True:
        try:
            query = voice.listen() if voice else input("> ")
            if sleeping:
                if not has_wake_word(query):
                    continue
                sleeping = False
                # A wake phrase may include a command; don't discard that command.
            action = parse_command(query)
            answer = execute(action, dry_run=args.dry_run)
            print(answer)
            if voice:
                voice.speak(answer)
            if action.kind == "exit":
                return 0
            sleeping = action.kind == "sleep"
        except (KeyboardInterrupt, EOFError):
            return 0
        except Exception as error:
            # Speech/network errors should not terminate the command loop.
            print(f"Unable to process that command ({type(error).__name__}). Try again.")


if __name__ == "__main__":
    raise SystemExit(main())
