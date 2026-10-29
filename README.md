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

## Status

Kit assembled and running on the Pi. Code and notes to be added from my machines.
