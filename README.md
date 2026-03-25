# CPS Swarm Platform

**Low-Cost Cyber-Physical Experimentation Platform for Swarm Robotics Research**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Webots](https://img.shields.io/badge/Webots-R2025a-blue)](https://cyberbotics.com/)
[![Platform](https://img.shields.io/badge/Hardware-ESP8266%20NodeMCU-red)](https://www.nodemcu.com/)

> Open-source platform combining the [Webots](https://cyberbotics.com/) simulator with low-cost ESP8266 microcontrollers (~$8 USD) for scalable swarm robotics experimentation. Achieves bidirectional cyber-physical coupling at 2 Hz with 99.2% communication uptime and 73 ms average latency.

---

## Overview

This platform addresses the gap between expensive physical robot platforms (~$1000/unit) and pure simulation environments that lack hardware integration. It enables:

- **Virtual → Physical**: Robot state, pheromone levels, and behavioral events transmitted to NodeMCU physical nodes
- **Physical → Virtual**: Analog sensor readings (temperature proxy via potentiometer) modulate virtual robot speed and behavior
- **Hybrid architecture**: N virtual + M physical agents operating simultaneously

The platform was validated through a multi-agent foraging case study using Ant Colony Optimization (ACO) with boredom-driven exploration, collecting 120 food items over 5000 iterations.

---

## Repository Structure

```
cps-swarm-platform/
├── webots/
│   ├── hybrid_controller.py     # Webots supervisor (Python): ACO + boredom + TCP server
│   └── hybrid_swarmv2.wbt       # Webots world: 5x5m arena, 5 e-puck robots
├── firmware/
│   └── RobotciberfisicoLed.ino  # NodeMCU Arduino firmware: WiFi client + LED + OLED
├── docs/
│   └── wiring.md                # Hardware wiring guide (coming soon)
├── .gitignore
├── LICENSE
└── README.md
```

---

## Hardware Requirements

### Per Physical Node (~$8–10 USD)

| Component | Spec | Approx. Cost |
|---|---|---|
| NodeMCU v3 | ESP8266, 80 MHz, 80 KB RAM, WiFi 802.11n | $3–5 |
| RGB LED (common anode) | 3-channel, PWM-controlled | $0.50 |
| Potentiometer | 10 kΩ, connected to A0 | $0.20 |
| OLED Display (optional) | SSD1306 / SH1106, 128×64, I2C | $2–3 |
| 9V battery + holder | Power supply | $1–2 |
| Resistors | 270Ω (R, G), 220Ω (B) | $0.10 |

**Total for 5-node setup: ~$50–60 USD**

### Software Requirements

- [Webots R2025a](https://cyberbotics.com/doc/guide/installation-procedure) (free, open-source)
- Python 3.8+ with `numpy` and `matplotlib`
- [Arduino IDE 2.x](https://www.arduino.cc/en/software) with ESP8266 board support
- Arduino libraries: `ArduinoJson`, `Adafruit GFX`, `Adafruit SH110X`

---

## Quick Start

### 1. Webots Supervisor Setup

```bash
pip install numpy matplotlib
```

1. Open `webots/hybrid_swarmv2.wbt` in Webots R2025a
2. Place `webots/hybrid_controller.py` in your Webots project `controllers/hybrid_controller/` folder
3. Edit the NodeMCU IP addresses at the top of `hybrid_controller.py`:

```python
NODEMCU_CONFIG = [
    {'ip': '192.168.X.X', 'port': 8080, 'robot_id': 0},
    {'ip': '192.168.X.X', 'port': 8080, 'robot_id': 1},
    # Add one entry per physical node
]
```

4. Set `WIFI_ENABLED = False` to run in simulation-only mode (no NodeMCU required)

### 2. NodeMCU Firmware Setup

1. Open `firmware/RobotciberfisicoLed.ino` in Arduino IDE
2. Configure your network credentials:

```cpp
const char* ssid     = "YOUR_WIFI_SSID";
const char* password = "YOUR_WIFI_PASSWORD";
```

3. Update the robot ID label in `updateDisplay()`:

```cpp
display.print("R0 It:");  // Change R0 to match this node's robot ID (R0–R4)
```

4. Select board: **NodeMCU 1.0 (ESP-12E Module)**, upload speed 115200
5. Upload firmware via USB — the node auto-connects on power-up

### 3. Run the Experiment

1. Power on all NodeMCU boards (they connect to WiFi automatically)
2. Press **Play** in Webots — the supervisor starts the TCP server and connects to nodes
3. The simulation runs for 5000 iterations (~160 seconds simulation time)
4. Results and plots are saved to `simulation_results/`

---

## Communication Protocol

JSON over TCP/IP at 2 Hz (500 ms period).

**Physical → Virtual (upstream, every 500 ms):**
```json
{"temp": 28.3}
```

**Virtual → Physical (downstream, every 30 iterations):**
```json
{
  "i": 1200, "x": 1.2, "y": -0.5,
  "s": "SEARCHING", "b": false,
  "f": 3, "df": 1.8, "dn": 3.4,
  "p": 15.2, "bat": 73.5,
  "energy": 12.4, "e": false
}
```

**Event messages:**
```json
{"evt": "FOOD", "t": 4}   // Robot found food (t = total collected)
{"evt": "NEST"}            // Robot returned to nest
```

---

## LED Color Encoding

The RGB LED encodes swarm convergence state via pheromone level:

| Color | Pheromone Level | Meaning |
|---|---|---|
| 🔴 Red | < 0.5 | Unexplored zone, high boredom |
| 🟠 Orange | 0.5 – 2.0 | Exploring, emerging path |
| 🟡 Yellow | 2.0 – 10.0 | Consolidating route |
| 🟢 Green | 10.0 – 30.0 | Optimal foraging route |
| 🔵 Blue | > 30.0 | Full convergence |
| 🟢 Green (solid) | — | RETURNING state (carrying food) |
| ⚪ White (blink) | — | Arrived at nest |
| 🟡 Yellow (blink) | — | Food found event |

---

## Key Parameters

Edit at the top of `hybrid_controller.py`:

| Parameter | Default | Description |
|---|---|---|
| `NUM_ROBOTS` | 5 | Number of virtual agents |
| `MAX_ITERATIONS` | 5000 | Simulation length |
| `EVAPORATION_RATE` | 0.995 | ACO pheromone evaporation |
| `PHEROMONE_DEPOSIT` | 5.0 | Pheromone deposited on return |
| `BOREDOM_THRESHOLD` | 0.3 | Threshold for boredom exploration |
| `ENERGY_CRITICAL` | 20.0% | Battery level triggering emergency return |
| `WIFI_ENABLED` | True | Set False for simulation-only mode |

---

## Experimental Results

Validated with 5 virtual agents + 5 NodeMCU physical nodes:

| Metric | Value |
|---|---|
| Total food collected | 120 units |
| Convergence iteration | ~800 |
| Communication uptime | 99.2% |
| Average latency | 73 ms (σ = 12 ms) |
| Packet loss | 0.3% |
| Cost per node | ~$8 USD |
| Cost reduction vs. e-puck | 125× |

---



## Authors

- **Oscar Loyola-Valenzuela** — Facultad de Ingeniería y Negocios, Universidad de las Américas, Chile · [ORCID](https://orcid.org/0000-0001-9355-2346)
- **Jean-François Brethé** — GREAH, Le Havre Normandy University, France · [ORCID](https://orcid.org/0000-0001-8750-3281)
- **César Sandoval** — Facultad de Ingeniería y Negocios, Universidad de las Américas, Chile · [ORCID](https://orcid.org/0000-0002-4754-4721)

---

## License

This project is licensed under the MIT License — see [LICENSE](LICENSE) for details.
