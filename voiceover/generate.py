#!/usr/bin/env python3
"""Generate one voiceover clip per tour stop with OpenAI text-to-speech.

Usage:  OPENAI_API_KEY=... python3 voiceover/generate.py [stop numbers... | all]
Reads voiceover/lines.json, writes audio/sNN.mp3 and audio/manifest.json.
Existing clips are kept unless you name their stop numbers, so you can
re-record just the lines you have edited:  python3 voiceover/generate.py 8 14
Pass "all" to re-record every clip (e.g. after changing VOICE or SPEED).
"""
import json, os, re, subprocess, sys, urllib.request, urllib.error

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LINES = os.path.join(ROOT, "voiceover", "lines.json")
OUT = os.path.join(ROOT, "audio")

MODEL = "gpt-4o-mini-tts"
VOICE = os.environ.get("VOICE", "fable")  # fable is the most British-sounding OpenAI voice
# gpt-4o-mini-tts ignores the API's speed setting, so clips are sped up afterwards with
# ffmpeg (atempo keeps the pitch natural). 1.0 = as recorded.
SPEED = float(os.environ.get("SPEED", "1.1"))
INSTRUCTIONS = (
    "Speak with a natural, warm British English accent, like an experienced consultant "
    "presenting a product demo to a senior client in a meeting room. Conversational and "
    "confident, at a brisk but clear pace, with natural pauses at full stops. Never salesy or theatrical."
)
VISION_INSTRUCTIONS = INSTRUCTIONS + (
    " For this part, lift the energy slightly: less 'here is what you have bought', "
    "more 'here is what becomes possible'."
)

# Spoken forms for things TTS tends to misread. Display text in lines.json is untouched.
SAY = [
    (r"\bEXP-100\b", "E X P one hundred"),
    (r"\bS4a\b", "S four A"),
    (r"\bSMRs\b", "S M Rs"),
    (r"\bSMR\b", "S M R"),
    (r"Rolls[- ]⁠?Royce", "Rolls-Royce"),
    (r"Temelín", "Temelin"),
]


def spoken(text):
    for pat, rep in SAY:
        text = re.sub(pat, rep, text)
    return text


def duration(path):
    out = subprocess.run(["afinfo", path], capture_output=True, text=True).stdout
    m = re.search(r"estimated duration: ([\d.]+)", out)
    return round(float(m.group(1)), 1) if m else None


def tts(text, instructions, path):
    body = json.dumps({"model": MODEL, "voice": VOICE, "input": text,
                       "instructions": instructions, "response_format": "mp3"}).encode()
    req = urllib.request.Request("https://api.openai.com/v1/audio/speech", data=body, headers={
        "Authorization": "Bearer " + os.environ["OPENAI_API_KEY"],
        "Content-Type": "application/json"})
    # Work in temp files so a failed download or ffmpeg run leaves the existing clip untouched.
    raw, fast = path + ".raw.mp3", path + ".fast.mp3"
    try:
        with urllib.request.urlopen(req, timeout=120) as r, open(raw, "wb") as f:
            f.write(r.read())
        if SPEED != 1.0:
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", raw, "-filter:a",
                            f"atempo={SPEED}", "-b:a", "128k", fast], check=True)
            os.replace(fast, path)
        else:
            os.replace(raw, path)
    finally:
        for t in (raw, fast):
            if os.path.exists(t):
                os.remove(t)


def main():
    if not os.environ.get("OPENAI_API_KEY"):
        sys.exit("Set OPENAI_API_KEY first.")
    redo_all = "all" in sys.argv[1:]
    only = {int(a) for a in sys.argv[1:] if a != "all"}
    lines = json.load(open(LINES))
    os.makedirs(OUT, exist_ok=True)
    manifest = {}
    for ln in lines:
        key, path = ln["key"], os.path.join(OUT, ln["key"] + ".mp3")
        if redo_all or not os.path.exists(path) or ln["stop"] in only:
            instr = VISION_INSTRUCTIONS if ln["stop"] >= 27 else INSTRUCTIONS
            print(f"stop {ln['stop']:2}  {ln['title']}", flush=True)
            try:
                tts(spoken(ln["text"]), instr, path)
            except urllib.error.HTTPError as e:
                sys.exit(f"OpenAI error {e.code}: {e.read().decode()[:300]}")
        manifest[key] = {"src": f"audio/{key}.mp3", "dur": duration(path)}
    json.dump(manifest, open(os.path.join(OUT, "manifest.json"), "w"), indent=1)
    # manifest.js lets the page load the list when opened straight from disk (file://)
    open(os.path.join(OUT, "manifest.js"), "w").write("window.__NT_AUDIO=" + json.dumps(manifest) + ";\n")
    print(f"Done: {len(manifest)} clips, {sum(v['dur'] or 0 for v in manifest.values())/60:.1f} min of audio.")


if __name__ == "__main__":
    main()
