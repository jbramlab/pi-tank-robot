# receiver.py - runs on the Raspberry Pi. Accepts a fixed set of commands, caps speed and time,
# refuses forward motion near obstacles and stops by itself if commands stop arriving.
# See docs/local-ai-control.md (step 2).

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
