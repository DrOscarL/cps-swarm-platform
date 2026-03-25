# Hardware Wiring Reference

## NodeMCU v3 (ESP8266) Pin Map

```
NodeMCU v3
─────────────────────────────
Pin     │ Component       │ Notes
────────┼─────────────────┼──────────────────────────
A0      │ Potentiometer   │ 10kΩ, wiper to A0
        │ (temp proxy)    │ ends to 3.3V and GND
────────┼─────────────────┼──────────────────────────
D5/GPIO14│ RGB LED — Red  │ 270Ω resistor in series
D6/GPIO12│ RGB LED — Green│ 270Ω resistor in series
D7/GPIO13│ RGB LED — Blue │ 220Ω resistor in series
        │ (common anode)  │ anode to 3.3V
────────┼─────────────────┼──────────────────────────
D1/GPIO5│ OLED SCL        │ SH1106 / SSD1306 I2C
D2/GPIO4│ OLED SDA        │ address 0x3C
        │ OLED VCC        │ → 3.3V
        │ OLED GND        │ → GND
────────┼─────────────────┼──────────────────────────
VIN     │ 9V battery (+)  │ via DC jack or VIN pin
GND     │ 9V battery (−)  │
─────────────────────────────
```

## Schematic Notes

- The RGB LED used is **common anode** type. The firmware inverts PWM values accordingly (`analogWrite(LED_R, (255 - r) * 4)`).
- If using a **common cathode** LED, remove the inversion in `setLED()`.
- The potentiometer simulates a temperature sensor in the range 0–50°C. To use a real sensor (DHT22, DS18B20), replace `analogRead(POT_PIN)` with the appropriate library call — no protocol changes needed.

## Recommended Substitutions for Production Deployment

| Proxy component | Production sensor | Cost | Accuracy |
|-----------------|-------------------|------|----------|
| 10kΩ potentiometer | DHT22 | ~$2 | ±0.5°C |
| 10kΩ potentiometer | DS18B20 | ~$1.50 | ±0.5°C |
| (none) | INA219 (current) | ~$3.50 | ±1 mA |

Substitution requires only a library change in the firmware — the TCP/IP protocol and JSON message format remain unchanged.

## Power Budget (per node)

| Condition | Current draw |
|-----------|-------------|
| Idle (WiFi connected) | ~80 mA |
| Active transmission | ~170 mA |
| OLED on | +20 mA |
| **Total (typical)** | **~100–200 mA** |

A 9V / 500 mAh battery provides approximately **2–4 hours** of continuous operation.
