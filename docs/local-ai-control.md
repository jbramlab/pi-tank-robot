# Local AI Control for the XiaoR Geek Tank

Oct 5, 2026

## Overview

A language model runs on your gaming PC, the Raspberry Pi 3B on the tank only receives short commands over WiFi, and a small safety layer on the Pi keeps the tank from doing anything dangerous. The Pi 3B has 1 GB of RAM, so it cannot run a useful model itself; the RX 9070 (16 GB) can.

There are three parts:

1. **The brain (PC).** A local model runner serves a model that can call tools. You type or say a goal such as "turn left and move to the wall"; the model replies with tool calls like `drive(forward, 0.4, 2)` or `arm(up)`.
2. **The bridge (PC).** A short Python program connects the model to the tank. It sends the model's tool calls to the Pi as small HTTP requests, and returns results such as the ultrasonic distance or a camera snapshot.
3. **The receiver (Pi).** A small server on the tank accepts only a fixed list of commands, caps speed, stops the motors if it hears nothing for half a second, and has a stop command that always wins.

Build order: get the receiver working with plain button presses first, then add the bridge in a simulator with the wheels lifted off the ground, then connect the model. Nothing the model produces is trusted directly: every command passes through the Pi's limits.

## What you need

You already have the hard parts. The one open item is how the tank is controlled today, which decides how the receiver is written.

| Item | Where | Status |
| --- | --- | --- |
| Ryzen 5 5600, 32 GB RAM, RX 9070 16 GB | PC | Built and running |
| XiaoR Geek TH Tank with robotic arm and WiFi camera | Tank | Assembled |
| Raspberry Pi 3B (1 GB) | Tank | In use |
| HC-SR04 ultrasonic sensor, front right | Tank | Fitted |
| PC and Pi on the same WiFi network | Both | To confirm |
| Pi's fixed IP address (set a DHCP reservation on the router) | Pi | To do |
| The kit's own control code or app: which language, which ports | Pi | To confirm |
| Local model runner (Ollama or llama.cpp) | PC | To install |
| Python 3.10 or newer | PC and Pi | To confirm |

The kit's control interface is still the main unknown. Your Tank Robot: Project Brief in Drive records that the kit is driven by XiaoR's own Android, iOS and PC apps, with a 2-axis camera, a 4-axis arm, infrared line sensors and the ultrasonic sensor, but not how those apps talk to the Pi (ports and message format) or whether the tank joins your home WiFi or makes its own hotspot. Two ways forward, and I'd pick the first:

1. **Replace the stock software with the receiver in step 2.** The Pi runs only your code, which gives full control and the safety limits below. You need the kit's motor, servo and sensor pin map from XiaoR's documentation or the SD card's code, then fill in the `Motors` class.
2. **Keep XiaoR's software and send it commands.** Quicker if its protocol is simple, but you inherit its limits and there is no hard safety layer, so a small proxy on the PC would have to add the caps.

The model runner on the PC uses the GPU. AMD cards work with Ollama on Windows, and the RX 9070 should be supported, but check the runner's current release notes, because RDNA 4 support has changed between versions. If the GPU is not picked up, llama.cpp's Vulkan build is the fallback and runs fine on this card.

## Step 1: the model runner on the PC

Install Ollama, pull a model that supports tool calling, and check that it answers. A 14B model at 4-bit quantisation takes about 9 GB, which fits in the 16 GB card with room for the camera model later.

```powershell
winget install Ollama.Ollama
ollama pull qwen3:14b
ollama run qwen3:14b "Reply with the single word ready"
```

Check the model's page on the Ollama library for a tag marked as supporting tools; newer models replace these names regularly, so use the newest tool-calling model that fits in about 10 GB. Then confirm the GPU is being used: run `ollama ps` while a prompt is running, and look for 100% GPU in the processor column. If it shows CPU, the card was not detected: update the Adrenalin driver and Ollama, or switch to the llama.cpp Vulkan build.

The runner now listens at `http://localhost:11434`. Leave it that way; the bridge in step 3 runs on the same PC, so nothing needs to be exposed to your network.

## Step 2: the receiver on the Pi

The receiver is the only thing that touches the motors, so all the safety rules live here and cannot be bypassed by the model. It accepts five commands, caps speed and duration, refuses forward motion when the ultrasonic sensor sees something close, and stops the motors by itself if no new command arrives in time.

Install Flask on the Pi (`pip3 install flask`) and save this as `receiver.py`. The `Motors` class is a stub that prints instead of moving: replace its four methods with the kit's own motor, arm and sensor calls once you know which interface the kit uses (see What you need).

```python
import threading, time, os
from flask import Flask, request, jsonify

TOKEN = os.environ.get("TANK_TOKEN", "change-me")
MAX_SPEED = 0.5        # never exceed 50% power, whatever is asked
MAX_SECONDS = 3.0      # longest single move
MIN_DISTANCE_CM = 15   # refuse to drive forward closer than this

class Motors:
    """Replace these bodies with the kit's own calls."""
    def set(self, left, right): print("motors", left, right)
    def arm(self, action): print("arm", action)
    def distance_cm(self): return 100.0   # read the HC-SR04 here
    def stop(self): self.set(0.0, 0.0)

motors = Motors()
state = {"deadline": 0.0, "estop": False}
lock = threading.Lock()
app = Flask(__name__)

DIRECTIONS = {
    "forward": (1, 1), "backward": (-1, -1),
    "left": (-1, 1), "right": (1, -1),
}

def watchdog():
    while True:
        time.sleep(0.05)
        with lock:
            if state["deadline"] and time.time() > state["deadline"]:
                motors.stop()
                state["deadline"] = 0.0

threading.Thread(target=watchdog, daemon=True).start()

@app.before_request
def check_token():
    if request.headers.get("X-Token") != TOKEN:
        return jsonify(error="unauthorised"), 401

@app.post("/drive")
def drive():
    d = request.get_json(force=True)
    direction = d.get("direction")
    if direction not in DIRECTIONS:
        return jsonify(error="bad direction"), 400
    speed = max(0.0, min(float(d.get("speed", 0.3)), MAX_SPEED))
    seconds = max(0.0, min(float(d.get("seconds", 1.0)), MAX_SECONDS))
    with lock:
        if state["estop"]:
            return jsonify(error="emergency stop active"), 409
        if direction == "forward" and motors.distance_cm() < MIN_DISTANCE_CM:
            motors.stop()
            return jsonify(error="obstacle ahead"), 409
        l, r = DIRECTIONS[direction]
        motors.set(l * speed, r * speed)
        state["deadline"] = time.time() + seconds
    return jsonify(ok=True, speed=speed, seconds=seconds)

@app.post("/arm")
def arm():
    action = request.get_json(force=True).get("action")
    if action not in ("up", "down", "open", "close", "home"):
        return jsonify(error="bad action"), 400
    with lock:
        if state["estop"]:
            return jsonify(error="emergency stop active"), 409
        motors.arm(action)
    return jsonify(ok=True)

@app.post("/stop")
def stop():
    with lock:
        motors.stop()
        state["estop"] = True
        state["deadline"] = 0.0
    return jsonify(ok=True, estop=True)

@app.post("/resume")      # a person calls this, never the model
def resume():
    with lock:
        state["estop"] = False
    return jsonify(ok=True, estop=False)

@app.get("/distance")
def distance():
    return jsonify(cm=motors.distance_cm())

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5055)
```

Run it with `TANK_TOKEN=pick-a-long-random-string python3 receiver.py`. Two details matter. Every request needs the `X-Token` header, so other devices on your WiFi cannot drive the tank. And `/resume` is deliberately left out of the bridge's tool list in step 3: only you can clear an emergency stop.

To make it start at boot, run it as a systemd service on the Pi (`/etc/systemd/system/tank-receiver.service`, with `Restart=always` and the token set under `Environment=`), then `sudo systemctl enable --now tank-receiver`.

## Step 3: the bridge on the PC

The bridge gives the model four tools (drive, arm, stop, read distance), runs the loop where the model asks for a tool and gets the result back, and sends each call to the Pi. It starts in dry-run mode, which prints the commands instead of sending them, so you can test the model's behaviour with the tank switched off.

Install the dependency (`pip install requests`), set your Pi's address, and save this as `bridge.py` on the PC:

```python
import os, json, requests

OLLAMA = "http://localhost:11434/api/chat"
MODEL = "qwen3:14b"
TANK = os.environ.get("TANK_URL", "http://192.168.1.50:5055")
HEADERS = {"X-Token": os.environ.get("TANK_TOKEN", "change-me")}
DRY_RUN = os.environ.get("DRY_RUN", "1") == "1"   # 1 = print only
MAX_TOOL_CALLS = 8                                # per message from you

SYSTEM = (
    "You control a small tracked robot with an arm. Use the tools to act. "
    "Make short moves (1 to 2 seconds), check the distance sensor before "
    "driving forward, and call stop if anything is unclear. Never guess: "
    "if a tool returns an error, report it and stop."
)

def call(method, path, body=None):
    if DRY_RUN:
        print(f"  [dry run] {method} {path} {body}")
        return {"ok": True, "dry_run": True, "cm": 80}
    r = requests.request(method, TANK + path, json=body,
                         headers=HEADERS, timeout=5)
    return r.json()

def tool(name, desc, props, required):
    return {"type": "function", "function": {
        "name": name, "description": desc,
        "parameters": {"type": "object", "properties": props,
                       "required": required}}}

TOOLS = [
    tool("drive", "Move the robot for a short time.", {
        "direction": {"type": "string",
                      "enum": ["forward", "backward", "left", "right"]},
        "speed": {"type": "number", "description": "0.1 to 0.5"},
        "seconds": {"type": "number", "description": "0.2 to 3"}},
        ["direction"]),
    tool("arm", "Move the robotic arm.", {
        "action": {"type": "string",
                   "enum": ["up", "down", "open", "close", "home"]}},
        ["action"]),
    tool("stop", "Stop all motion immediately.", {}, []),
    tool("get_distance", "Read the front distance in cm.", {}, []),
]

RUNNERS = {
    "drive": lambda a: call("POST", "/drive", a),
    "arm": lambda a: call("POST", "/arm", a),
    "stop": lambda a: call("POST", "/stop"),
    "get_distance": lambda a: call("GET", "/distance"),
}

def ask(messages):
    r = requests.post(OLLAMA, json={"model": MODEL, "messages": messages,
                      "tools": TOOLS, "stream": False}, timeout=120)
    return r.json()["message"]

def run(goal):
    messages = [{"role": "system", "content": SYSTEM},
                {"role": "user", "content": goal}]
    calls = 0
    while True:
        msg = ask(messages)
        messages.append(msg)
        if not msg.get("tool_calls"):
            return msg.get("content", "")
        for tc in msg["tool_calls"]:
            if calls >= MAX_TOOL_CALLS:
                call("POST", "/stop")
                return "Stopped: too many actions for one request."
            calls += 1
            name = tc["function"]["name"]
            args = tc["function"]["arguments"]
            runner = RUNNERS.get(name)
            result = runner(args) if runner else {"error": "unknown tool"}
            print(f"  {name}({args}) -> {result}")
            messages.append({"role": "tool", "tool_name": name,
                             "content": json.dumps(result)})

if __name__ == "__main__":
    print("DRY RUN" if DRY_RUN else "LIVE: the tank will move")
    while True:
        goal = input("> ")
        print(run(goal))
```

Run it with `python bridge.py`. Type a goal such as "drive forward for one second then raise the arm" and check that the dry-run lines match what you asked. The bridge has its own limit of 8 tool calls per message, on top of the Pi's speed and time caps, and it never exposes `/resume`. To go live, set `DRY_RUN=0` only after the testing checklist below.

## Step 4: giving it sight

The simplest way to let the model see is a fifth tool, `look`, that grabs one frame from the tank's camera, sends it to a small vision model, and returns a text description. The main model stays text-only and never handles images, which keeps it fast.

Pull a vision model (`ollama pull qwen2.5vl:7b`, or the newest small vision model in the library). Ollama loads and unloads models as needed, so the 14B model and the vision model do not have to fit in the card at once, at the cost of a few seconds when it switches.

Add this to `bridge.py`. `CAMERA_URL` must be an address that returns a single JPEG frame; many camera streams offer one, for example an MJPEG stream's snapshot address. Check what the kit's camera exposes (see What you need) and set it here.

```python
import base64

CAMERA_URL = os.environ.get("CAMERA_URL", "http://192.168.1.50:8080/snapshot.jpg")
VISION_MODEL = "qwen2.5vl:7b"

def look(args):
    question = args.get("question", "Describe what is in front of the robot.")
    if DRY_RUN:
        return {"description": "[dry run] a wall about 1 metre ahead"}
    frame = requests.get(CAMERA_URL, timeout=5).content
    r = requests.post(OLLAMA, json={"model": VISION_MODEL, "stream": False,
        "messages": [{"role": "user", "content": question,
                      "images": [base64.b64encode(frame).decode()]}]},
        timeout=120)
    return {"description": r.json()["message"]["content"]}

TOOLS.append(tool("look", "Look through the camera and answer a question.",
    {"question": {"type": "string"}}, []))
RUNNERS["look"] = look
```

This is also the base for your face-following and object-search ideas. For fast tracking, do not route every frame through the language model: run a lightweight detector such as OpenCV face detection on the PC, let it steer the tank directly through the same receiver, and use the language model only for goals and decisions, such as "find the red cup".

## Testing and safety checklist

Work through these in order, and do not go live until each one passes.

- [ ] Receiver running on the Pi with the stub `Motors`: send `curl -X POST -H "X-Token: ..." -d '{"direction":"forward"}' http://<pi>:5055/drive` and see the print line
- [ ] A request without the `X-Token` header returns 401
- [ ] Replace the stub with the kit's real motor calls; lift the tank so the tracks spin freely and repeat the drive test
- [ ] A move longer than 3 seconds is cut to 3 seconds, and a request for full speed runs at 50%
- [ ] Unplug or kill the bridge mid-move: the motors stop within about half a second
- [ ] `/stop` halts the tank, and further drive commands return 409 until you call `/resume` yourself
- [ ] Put your hand 10 cm in front of the ultrasonic sensor: forward is refused
- [ ] Dry-run the bridge with 10 different goals, including odd ones like "drive forward for ten minutes", and check the printed commands are all sensible and capped
- [ ] Go live with the tank on the floor in a clear area, wheels still raised the first time, and keep your hand on the Pi's power switch or battery lead
- [ ] Keep `MAX_SPEED` at 0.5 and `MAX_SECONDS` at 3 until the tank has run an hour without a surprise

Two habits keep this safe. Run the first live tests with the arm and camera off, and test one new capability at a time.

## Troubleshooting and next steps

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| `ollama ps` shows CPU, answers take a minute | GPU not detected | Update the Adrenalin driver and Ollama; try the llama.cpp Vulkan build |
| Model replies in text but never calls a tool | Model without tool support, or a vague prompt | Pick a model tagged for tools; state the goal as an action |
| Bridge returns a connection error | Pi address changed, or different WiFi | Give the Pi a fixed address; confirm both devices are on the same network |
| 401 from the Pi | Token mismatch | Set the same `TANK_TOKEN` on both machines |
| 409 "emergency stop active" | A stop was sent earlier | Call `/resume` yourself from the PC |
| Tank moves in a different direction than asked | Motor wiring or sign reversed | Flip the sign for that motor in the `Motors.set` method |
| `look` returns nonsense or times out | Wrong camera URL, or the vision model is loading | Open the URL in a browser; wait for the first call to finish loading |

**Later upgrades.** Add a room map built from the ultrasonic readings and the tank's own movement estimates; add voice input with a local speech-to-text model such as Whisper; add a small "skills" list so the model can run saved routines, such as a patrol path.

**Abliterated models.** A model with its refusals removed is not needed for this project, and tends to follow instructions and call tools less reliably, which is what matters here. If you still want to try one later, swap the `MODEL` name in `bridge.py` for a community abliterated build of the same family and compare how well it handles the checklist's dry-run goals. Keep the Pi-side limits regardless: they, not the model, are what make the tank safe.
