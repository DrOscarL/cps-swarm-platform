# CPS Swarm Platform

**Low-Cost Cyber-Physical Experimentation Platform for Swarm Robotics Research**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Webots](https://img.shields.io/badge/Webots-R2025a-blue.svg)](https://cyberbotics.com)
[![Platform](https://img.shields.io/badge/Hardware-ESP8266%20NodeMCU-red.svg)](https://www.nodemcu.com)
[![Python](https://img.shields.io/badge/Python-3.8%2B-green.svg)](https://python.org)

> Open-source platform combining the [Webots](https://cyberbotics.com) simulator with low-cost ESP8266 microcontrollers (~$8 USD) for scalable swarm robotics experimentation. Achieves **125× cost reduction** compared to traditional platforms while enabling true bidirectional cyber-physical coupling.

---

## Overview

This platform implements a three-layer architecture:

```
┌─────────────────────────────────────────────────┐
│  VIRTUAL LAYER — Webots R2025a                  │
│  N differential-drive robots (e-puck)           │
│  ACO + Boredom (Chua oscillator) controller     │
└──────────────────┬──────────────────────────────┘
                   │ TCP/IP (JSON, 2 Hz)
┌──────────────────▼──────────────────────────────┐
│  COMMUNICATION LAYER — Python Supervisor        │
│  Bidirectional data exchange                    │
│  Virtual → Physical: position, state, battery  │
│  Physical → Virtual: temperature modulation    │
└──────────────────┬──────────────────────────────┘
                   │ WiFi 802.11n
┌──────────────────▼──────────────────────────────┐
│  PHYSICAL LAYER — M NodeMCU ESP8266 nodes       │
│  RGB LED (swarm state visualization)            │
│  SH1106 OLED display (real-time telemetry)      │
│  Potentiometer (temperature proxy sensor)       │
└─────────────────────────────────────────────────┘
```

### Key Results (from paper)

| Metric | Value |
|--------|-------|
| Food collected (5000 iterations) | 120 units |
| Communication uptime | 99.2% |
| Average latency | 73 ms (σ = 12 ms) |
| Update rate | 2 Hz |
| Cost per physical node | ~$8 USD |
| Cost reduction vs. e-puck | **125×** |

---

## Repository Structure

```
cps-swarm-platform/
├── webots/
│   ├── worlds/
│   │   └── hybrid_swarmv2.wbt       # Webots simulation world (5×5 m arena)
│   └── controllers/
│       └── hybrid_controller/
│           └── hybrid_controller.py  # Supervisor: ACO + Boredom + TCP server
├── nodemcu/
│   └── RobotciberfisicoLed.ino      # ESP8266 firmware (Arduino)
├── docs/
│   └── wiring_diagram.md            # Hardware wiring reference
├── .gitignore
├── LICENSE
└── README.md
```

---

## Requirements

### Software

| Component | Version |
|-----------|---------|
| [Webots](https://cyberbotics.com/doc/guide/installing-webots) | R2025a |
| Python | 3.8+ |
| numpy | ≥ 1.21 |
| matplotlib | ≥ 3.4 (optional, for plots) |
| [Arduino IDE](https://www.arduino.cc/en/software) | 2.x |
| ESP8266 board package | ≥ 3.1 |

### Arduino Libraries (install via Library Manager)

- `ArduinoJson` ≥ 6.x
- `Adafruit GFX Library`
- `Adafruit SH110X`

### Hardware (per physical node, ~$10 USD total)

| Component | Cost |
|-----------|------|
| NodeMCU v3 (ESP8266) | ~$4 |
| RGB LED (common anode) | ~$0.20 |
| 3× resistors (270Ω, 270Ω, 220Ω) | ~$0.10 |
| 10kΩ potentiometer | ~$0.30 |
| SSD1306/SH1106 OLED 128×64 I2C (optional) | ~$3 |
| 9V battery + connector | ~$2 |

---

## Quick Start

### 1. Clone the repository

```bash
git clone https://github.com/oscar-loyola/cps-swarm-platform.git
cd cps-swarm-platform
```

### 2. Configure NodeMCU firmware

Open `nodemcu/RobotciberfisicoLed.ino` in Arduino IDE and set your credentials:

```cpp
const char* ssid     = "YOUR_WIFI_SSID";
const char* password = "YOUR_WIFI_PASSWORD";
const int   tcpPort  = 8080;
```

Flash each NodeMCU board via USB. Each board will display its assigned IP on the OLED after connecting.

### 3. Configure the Python supervisor

Open `webots/controllers/hybrid_controller/hybrid_controller.py` and update the NodeMCU IP addresses:

```python
NODEMCU_CONFIG = [
    {'ip': '192.168.1.X', 'port': 8080, 'robot_id': 0},
    {'ip': '192.168.1.Y', 'port': 8080, 'robot_id': 1},
    # Add entries for each physical node
]
WIFI_ENABLED = True   # Set to False to run simulation-only mode
```

> **Tip:** Set `WIFI_ENABLED = False` to run the full simulation without any physical hardware.

### 4. Launch the simulation

Open `webots/worlds/hybrid_swarmv2.wbt` in Webots R2025a. The supervisor starts automatically and:
- Connects to all configured NodeMCU nodes
- Runs the ACO + Boredom foraging task for `MAX_ITERATIONS` steps
- Saves plots to `simulation_results/` upon completion

---

## Communication Protocol

All messages use JSON over TCP/IP (port 8080).

**Physical → Virtual** (NodeMCU sends every 500 ms):
```json
{"temp": 28.3}
```

**Virtual → Physical** (Supervisor sends every ~1 s):
```json
{
  "i": 1250,
  "x": 1.2, "y": -0.5,
  "s": "SEARCHING",
  "b": false,
  "f": 3,
  "df": 1.4,
  "dn": 3.2,
  "p": 15.2,
  "bat": 73.5,
  "energy": 0.42,
  "e": false
}
```

**Temperature–speed coupling:**

$$v_{actual} = v_{base} \cdot f_T(T)$$

Where $f_T(T) = 0.5 + T/30$ if $T < 15°C$, $1.0$ if $15 \leq T \leq 35°C$, and $1.0 + (T-35)/30$ if $T > 35°C$.

---

## LED State Encoding

| Color | State | Condition |
|-------|-------|-----------|
| 🔵 Blue (dim–bright) | SEARCHING | Brightness ∝ local pheromone τ |
| 🟠 Orange | Emerging path | τ ∈ [0.5, 2.0] |
| 🟡 Yellow | Consolidated route | τ ∈ [2.0, 10.0] |
| 🟢 Green (solid) | RETURNING | Agent carrying food to nest |
| 🔴 Red (5 Hz blink) | EMERG | Battery < 20% |

---

## Scaling Beyond 5 Nodes

The platform was validated with up to 5 physical nodes (2.4 GHz WiFi). For larger deployments:

- **5–20 nodes:** Use 5 GHz WiFi (requires ESP32 upgrade)
- **20+ nodes:** Switch to MQTT publish-subscribe (planned in future work)
- **Wired option:** ESP32 + LAN8720 Ethernet (~$5 extra per node)

---

## Citation

If you use this platform in your research, please cite:

```bibtex
@article{loyola2026cpsswarm,
  title   = {Low-Cost Cyber-Physical Experimentation Platform for Swarm Robotics Research},
  author  = {Loyola-Valenzuela, Oscar and Brethé, Jean-François and Sandoval, César},
  journal = {Revista Facultad de Ingeniería, Universidad de Antioquia},
  year    = {2026},
  note    = {Under review}
}
```

---

## Related Work

This platform builds on the ACO + boredom navigation algorithm:

> Loyola, O., Kern, J., & Urrea, C. (2021). Novel algorithm for agent navigation based on intrinsic motivation due to boredom. *Information Technology and Control*, 50, 485–494.

---

## Authors

- **Oscar Loyola-Valenzuela** — Facultad de Ingeniería y Negocios, Universidad de las Américas, Santiago, Chile · [ORCID](https://orcid.org/0000-0001-9355-2346)
- **Jean-François Brethé** — GREAH, Le Havre Normandy University, Le Havre, France · [ORCID](https://orcid.org/0000-0001-8750-3281)
- **César Sandoval** — Facultad de Ingeniería y Negocios, Universidad de las Américas, Santiago, Chile · [ORCID](https://orcid.org/0000-0002-4754-4721)

---

## License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.
