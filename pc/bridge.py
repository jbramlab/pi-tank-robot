# bridge.py - runs on the PC. Connects a local tool-calling model (Ollama) to the tank receiver.
# Starts in dry-run mode (DRY_RUN=1). See docs/local-ai-control.md (steps 3 and 4).

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

# ---- camera tool (step 4) ----
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

if __name__ == "__main__":
    print("DRY RUN" if DRY_RUN else "LIVE: the tank will move")
    while True:
        goal = input("> ")
        print(run(goal))
