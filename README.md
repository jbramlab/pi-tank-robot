# Pi Tank Robot

A tracked robot built from the XiaoR Geek TH Tank kit, running on a Raspberry Pi 3B, with a WiFi camera, a robotic arm and an HC-SR04 ultrasonic sensor on the front.

## Plan

- The Pi stays on the tank as the receiver: it streams video and runs the motors, arm and sensors.
- Heavy processing runs on my PC over WiFi.
- Next steps: follow a face, then search for chosen objects and shapes.
- Later: map the room with the ultrasonic sensor, and have a model on the PC act as the tank's "brain", carrying out tasks I ask for.

## Layout

| Folder | What goes here |
| --- | --- |
| `pi` | Code that runs on the Raspberry Pi (motor, arm and sensor control, video stream, command server). |
| `pc` | Code that runs on the PC (vision, face following, control client, planning). |
| `docs` | Wiring, setup notes and the implementation plan. |

## Running it

1. On the Pi: `pip3 install -r pi/requirements.txt`, then `TANK_TOKEN=<long random string> python3 pi/receiver.py`. The `Motors` class is a stub that prints; fill it in with the kit's motor, arm and sensor calls.
2. On the PC: install Ollama and pull a tool-calling model, then `pip install -r pc/requirements.txt` and `python pc/bridge.py`. It starts in dry-run mode; set `DRY_RUN=0` only after the testing checklist in the docs passes.

The full plan, safety limits and testing checklist are in `docs/local-ai-control.md`.

## Status

Kit assembled and running on the Pi. Receiver and bridge written, not yet tested on the hardware; the kit's own control interface still needs confirming.
