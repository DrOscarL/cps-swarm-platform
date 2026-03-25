#include <ESP8266WiFi.h>
#include <ArduinoJson.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SH110X.h>

// ===== CONFIGURACIÓN =====
const char* ssid = "YOUR_WIFI_SSID";
const char* password = "YOUR_WIFI_PASSWORD";
//const char* ssid = "YueCasa";
//const char* password = "yue12345*";
const int tcpPort = 8080;

// ===== PINES =====
#define POT_PIN A0    // Potenciómetro
#define LED_R D5      // GPIO14 - Rojo con 270Ω
#define LED_G D6      // GPIO12 - Verde con 270Ω  
#define LED_B D7      // GPIO13 - Azul con 220Ω

// ===== OLED SH1106 =====
#define SCREEN_WIDTH 128
#define SCREEN_HEIGHT 64
#define OLED_RESET -1

Adafruit_SH1106G display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, OLED_RESET);

// Variables de estado
String currentState = "SEARCHING";
bool boredomActive = false;
int foodCollected = 0;
float posX = 0, posY = 0;
float distFood = 0, distNest = 0;
int iteration = 0;
float temperature = 25.0;
float pheromoneLevel = 0.1;  // Nivel de feromona local

WiFiServer server(tcpPort);
WiFiClient client;

unsigned long lastTempSend = 0;
const int TEMP_SEND_INTERVAL = 500;

void setup() {
  Serial.begin(115200);
  
  // Configurar pines
  pinMode(POT_PIN, INPUT);
  pinMode(LED_R, OUTPUT);
  pinMode(LED_G, OUTPUT);
  pinMode(LED_B, OUTPUT);
  
  // LED inicial apagado (ánodo común = HIGH apaga)
  setLED(0, 0, 0);
  
  // I2C
  Wire.begin(D2, D1);
  
  // OLED
  if (!display.begin(0x3C, true)) {
    Serial.println("Error OLED");
    while (1) delay(1000);
  }
  
  display.clearDisplay();
  display.setTextSize(1);
  display.setTextColor(SH110X_WHITE);
  display.setCursor(0, 0);
  display.println("NodeMCU Robot");
  display.println("+ Sensor Temp");
  display.println("+ LED RGB");
  display.display();
  
  // WiFi
  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    // Parpadeo mientras conecta
    setLED(50, 0, 50);
    delay(250);
    setLED(0, 0, 0);
  }
  
  Serial.println("WiFi OK");
  Serial.println(WiFi.localIP());
  
  display.clearDisplay();
  display.setCursor(0, 0);
  display.println("WiFi OK!");
  display.print("IP:");
  display.println(WiFi.localIP());
  display.println("\nEsperando");
  display.println("Webots...");
  display.display();
  
  server.begin();
  
  // LED verde = listo
  setLED(0, 255, 0);
  delay(1000);
  setLED(0, 0, 0);
}

void loop() {
  // Aceptar conexión
  if (!client || !client.connected()) {
    client = server.available();
    if (client) {
      Serial.println("Webots conectado!");
    }
  }
  
  // Leer y enviar temperatura
  if (client && client.connected()) {
    if (millis() - lastTempSend > TEMP_SEND_INTERVAL) {
      sendTemperature();
      lastTempSend = millis();
    }
    
    // Recibir datos
    if (client.available()) {
      String json = client.readStringUntil('\n');
      processData(json);
      updateDisplay();
      updateLED();  // Actualizar LED según convergencia
    }
  }
}

void sendTemperature() {
  int potValue = analogRead(POT_PIN);
  temperature = map(potValue, 0, 1023, 0, 500) / 10.0;
  
  StaticJsonDocument<64> doc;
  doc["temp"] = temperature;
  
  String json;
  serializeJson(doc, json);
  client.println(json);
  
  Serial.printf("Temp: %.1f°C\n", temperature);
}

void processData(String json) {
  StaticJsonDocument<256> doc;
  DeserializationError error = deserializeJson(doc, json);
  
  if (error) return;
  
  // Eventos
  if (doc.containsKey("evt")) {
    String evt = doc["evt"];
    
    if (evt == "FOOD") {
      foodCollected = doc["t"];
      
      // LED amarillo parpadeante
      for (int i = 0; i < 5; i++) {
        setLED(255, 255, 0);
        delay(100);
        setLED(0, 0, 0);
        delay(100);
      }
      
      display.clearDisplay();
      display.setTextSize(2);
      display.setCursor(10, 15);
      display.println("COMIDA!");
      display.setTextSize(1);
      display.setCursor(20, 45);
      display.print("Total: ");
      display.print(foodCollected);
      display.display();
      delay(1500);
    }
    else if (evt == "NEST") {
      // LED blanco parpadeante
      for (int i = 0; i < 3; i++) {
        setLED(255, 255, 255);
        delay(150);
        setLED(0, 0, 0);
        delay(150);
      }
      
      display.clearDisplay();
      display.setTextSize(2);
      display.setCursor(25, 25);
      display.println("NIDO");
      display.display();
      delay(1000);
    }
  }
  
  // Estado periódico
  if (doc.containsKey("x") && doc.containsKey("y")) {
    iteration = doc["i"];
    posX = doc["x"];
    posY = doc["y"];
    currentState = doc["s"].as<String>();
    boredomActive = doc["b"];
    foodCollected = doc["f"];
    distFood = doc["df"];
    distNest = doc["dn"];
    
    // Recibir nivel de feromona si está disponible
    if (doc.containsKey("p")) {
      pheromoneLevel = doc["p"];
    }
  }
}

void updateLED() {
  // Si está volviendo con comida, siempre verde brillante
  if (currentState == "RETURNING") {
    setLED(0, 255, 0);
    return;
  }
  
  // GRADIENTE DE CONVERGENCIA basado en feromona
  // Feromona baja (0.1-0.5) → Rojo (explorando, zona nueva)
  // Feromona media (0.5-2.0) → Naranja (camino emergente)
  // Feromona alta (2.0-10.0) → Amarillo (ruta consolidándose)
  // Feromona muy alta (10.0-30.0) → Verde (ruta óptima)
  // Feromona máxima (>30.0) → Azul (convergencia total)
  
  int r, g, b;
  
  if (pheromoneLevel < 0.5) {
    // ROJO: Zona inexplorada, boredom alto
    r = 255;
    g = 0;
    b = 0;
  }
  else if (pheromoneLevel < 2.0) {
    // ROJO → NARANJA: Explorando
    float t = (pheromoneLevel - 0.5) / 1.5;  // 0 a 1
    r = 255;
    g = (int)(t * 165);  // 0 a 165
    b = 0;
  }
  else if (pheromoneLevel < 10.0) {
    // NARANJA → AMARILLO: Camino emergente
    float t = (pheromoneLevel - 2.0) / 8.0;  // 0 a 1
    r = 255;
    g = (int)(165 + t * 90);  // 165 a 255
    b = 0;
  }
  else if (pheromoneLevel < 30.0) {
    // AMARILLO → VERDE: Ruta consolidada
    float t = (pheromoneLevel - 10.0) / 20.0;  // 0 a 1
    r = (int)(255 * (1 - t));  // 255 a 0
    g = 255;
    b = 0;
  }
  else {
    // VERDE → AZUL: Convergencia total
    float t = min((pheromoneLevel - 30.0) / 20.0, 1.0);  // 0 a 1, max en 50
    r = 0;
    g = (int)(255 * (1 - t));  // 255 a 0
    b = (int)(255 * t);  // 0 a 255
  }
  
  setLED(r, g, b);
  
  // Debug
  Serial.printf("Pher: %.1f | RGB: (%d,%d,%d)\n", pheromoneLevel, r, g, b);
}

void updateDisplay() {
  display.clearDisplay();
  display.setTextSize(1);
  
  // Encabezado con temperatura
  display.setCursor(0, 0);
  display.print("R4 It:"); //Actualizar según robot
  display.print(iteration);
  display.print(" T:");
  display.print(temperature, 0);
  display.println("C");
  display.drawLine(0, 9, 128, 9, SH110X_WHITE);
  
  // Posición
  display.setCursor(0, 12);
  display.print("Pos:(");
  display.print(posX, 1);
  display.print(",");
  display.print(posY, 1);
  display.println(")");
  
  // Estado
  display.setCursor(0, 22);
  display.print("Estado:");
  if (currentState == "SEARCHING") {
    display.println("BUSCANDO");
  } else {
    display.println("VOLVIENDO");
  }
  
  // Boredom y Feromona
  display.setCursor(0, 32);
  display.print("Bored:");
  display.print(boredomActive ? "SI" : "no");
  display.print(" Ph:");
  display.println(pheromoneLevel, 1);
  
  // Distancias
  display.setCursor(0, 42);
  display.print("aComida:");
  display.print(distFood, 1);
  display.setCursor(0, 52);
  display.print("aNido:");
  display.print(distNest, 1);
  
  // Food en la esquina
  display.setCursor(70, 52);
  display.print("Food:");
  display.print(foodCollected);
  
  // Barra de temperatura visual
  display.drawRect(90, 42, 35, 8, SH110X_WHITE);
  int barWidth = map(constrain(temperature, 0, 50), 0, 50, 0, 33);
  display.fillRect(91, 43, barWidth, 6, SH110X_WHITE);
  
  display.display();
}

void setLED(int r, int g, int b) {
  // ===== ÁNODO COMÚN: Invertir valores =====
  // 0 → 1023 (encendido máximo)
  // 255 → 0 (apagado)
  
  analogWrite(LED_R, (255 - r) * 4);
  analogWrite(LED_G, (255 - g) * 4);
  analogWrite(LED_B, (255 - b) * 4);
}

