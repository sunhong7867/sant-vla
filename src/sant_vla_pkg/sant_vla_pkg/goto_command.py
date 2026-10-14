"""Chat text -> the policy sentence for the go-to-object practice (2026-10-08).

The s1 policy was trained on SECTOR sentences only (goto_layout.SECTOR_TEMPLATES:
"Go to the object on the left." ...), never on object names. So the lecture
GUI routes a command in one of two ways:

  * the text already names a sector (left / ahead / right, Korean or English)
    -> that sector's canonical training sentence, no model call;
  * otherwise (an object name or a description such as "an extinct animal")
    -> System 2: the Qwen2.5-VL 7B model the demo already keeps loaded on the
    lab server (Ollama, the scene-narration model behind the 11501 tunnel)
    reads one front-camera frame plus the sentence and answers which object is
    meant and whether it is left / center / right of the image. No simulator
    coordinates are used. Measured 2026-10-08 on saved closed-loop frames:
    Korean object names on sector layouts 29/30, the held-out robot described
    as "안드로이드 마스코트" on free layouts 15/20 (all misses on near-centre
    objects); about 0.5 s per call.

Lane / zone / speed commands are left to the normal parser (`is_goto` False).
"""
import base64
import json
import re
import time
import urllib.request

from sant_vla_pkg import goto_layout as G

_SECTOR_WORDS = (
    ("left", r"왼쪽|좌측|\bleft\b"),
    ("right", r"오른쪽|우측|\bright\b"),
    ("ahead", r"정면|가운데|중앙|앞에\s*있는|똑바로|\bahead\b|\bstraight\b|\bcent(?:er|re)\b|\bmiddle\b"),
)
# Words that make it a driving-course command, not a go-to-object one.
_COURSE_WORDS = re.compile(r"차선|lane|T\d|M\d|바퀴|lap|속도|speed|빠르게|느리게|천천히|주차|park", re.I)
_GOTO_VERB = re.compile(r"(으로|로|까지|앞으로|에게)\s*(가|이동|가줘|가자|가라|가서)|\bgo to\b|\bdrive to\b|"
                        r"\bhead (?:to|over)\b|\btake me\b|\bstop in front\b|\bmove to\b", re.I)


_QUESTION = re.compile(r"\?|뭐|무엇|무슨|어떤|어디|뭔지|보여|보이|있어|있니|알려|설명|\bwhat\b|\bwhich\b|"
                       r"\bwhere\b|\bsee\b|\bdescribe\b|\bis there\b", re.I)


def sector_of(text):
    """'left' / 'ahead' / 'right' when the text names exactly one sector."""
    hits = [name for name, pat in _SECTOR_WORDS if re.search(pat, text, re.I)]
    return hits[0] if len(hits) == 1 else None


def is_goto(text, nouns=()):
    """True when the text should go to the go-to-object path: it names a
    sector, one of the placed objects, or reads as "go to X" — and is not a
    lane / zone / speed command."""
    if _COURSE_WORDS.search(text):
        return False
    if _QUESTION.search(text) and not _GOTO_VERB.search(text):
        return False        # "왼쪽에 뭐 있어?" is a question for the assistant, not a command
    if sector_of(text):
        return True
    low = text.lower()
    if any(n and n.lower() in low for n in nouns):
        return True
    return _GOTO_VERB.search(text) is not None


def sector_sentence(sector):
    return G.SECTOR_TEMPLATES[sector][0]


VLM_PROMPT = ('Forward camera of a car. Instruction: "{text}". Which visible object does the '
              'instruction refer to, and is it on the left, in the center, or on the right of the image?')
_POSITION = {"left": "left", "center": "ahead", "right": "right"}


def vlm_sector(host, model, jpeg_bytes, text, timeout=30.0):
    """System 2. Returns (sector or None, note, seconds)."""
    payload = {
        "model": model, "stream": False, "think": False, "keep_alive": "30m",
        "format": {"type": "object",
                   "properties": {"object": {"type": "string"},
                                  "position": {"type": "string",
                                               "enum": ["left", "center", "right", "not visible"]}},
                   "required": ["object", "position"]},
        "messages": [{"role": "user", "content": VLM_PROMPT.format(text=text),
                      "images": [base64.b64encode(jpeg_bytes).decode("ascii")]}],
        "options": {"temperature": 0},
    }
    t0 = time.monotonic()
    request = urllib.request.Request(f"{host}/api/chat", data=json.dumps(payload).encode("utf-8"),
                                     headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = json.loads(response.read().decode("utf-8"))
        answer = json.loads(str((body.get("message") or {}).get("content") or ""))
    except Exception as exc:                                    # noqa: BLE001
        return None, f"VLM 호출 실패 ({host}): {exc}", time.monotonic() - t0
    obj, position = str(answer.get("object", "?"))[:30], answer.get("position")
    sector = _POSITION.get(position)
    if sector is None:
        return None, f"VLM 이 화면에서 대상을 찾지 못함 ({obj}, {position})", time.monotonic() - t0
    return sector, f"VLM: '{obj}' 는 화면 {position}", time.monotonic() - t0
