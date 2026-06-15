#include "esp_camera.h"
#include <WiFi.h>
#include <WiFiClient.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>

// ===== PIN ESP32-CAM =====
#define PWDN_GPIO_NUM     32
#define RESET_GPIO_NUM    -1
#define XCLK_GPIO_NUM      0
#define SIOD_GPIO_NUM     26
#define SIOC_GPIO_NUM     27
#define Y9_GPIO_NUM       35
#define Y8_GPIO_NUM       34
#define Y7_GPIO_NUM       39
#define Y6_GPIO_NUM       36
#define Y5_GPIO_NUM       21
#define Y4_GPIO_NUM       19
#define Y3_GPIO_NUM       18
#define Y2_GPIO_NUM        5
#define VSYNC_GPIO_NUM    25
#define HREF_GPIO_NUM     23
#define PCLK_GPIO_NUM     22

// ===== WIFI =====
const char* ssid = "Wifi Chua";
const char* password = "38383838";

// ===== LOCAL SERVER HTTP =====
const char* serverHost = "192.168.2.7";  // Không có http:// hoặc https://
const int   serverPort = 8000;
const char* serverPath = "/api/upload/";
const char* deviceToken = "abccc";

// ===== TỐC ĐỘ STREAM =====
const TickType_t FRAME_INTERVAL = pdMS_TO_TICKS(500);  // gần 2 fps
const uint32_t CONNECT_TIMEOUT_MS = 1200;
const uint32_t FIRST_BYTE_TIMEOUT_MS = 1500;
const uint32_t BODY_READ_TIMEOUT_MS = 1500;
const size_t WRITE_CHUNK_SIZE = 1024;

// ===== BIẾN TOÀN CỤC =====
WiFiClient client;
volatile bool isShooting = false;
volatile bool cardConfirmed = false;
char currentRFID[32] = "";

portMUX_TYPE sharedMux = portMUX_INITIALIZER_UNLOCKED;

// ===== JSON PARSE ĐƠN GIẢN =====
int extractJSONInt(const String& json, const String& key) {
  int keyIdx = json.indexOf(key);
  if (keyIdx == -1) return -1;
  int colonIdx = json.indexOf(':', keyIdx);
  if (colonIdx == -1) return -1;
  int commaIdx = json.indexOf(',', colonIdx);
  int braceIdx = json.indexOf('}', colonIdx);
  int endIdx = (commaIdx != -1 && commaIdx < braceIdx) ? commaIdx : braceIdx;
  if (endIdx == -1) endIdx = json.length();
  String valStr = json.substring(colonIdx + 1, endIdx);
  valStr.trim();
  return valStr.toInt();
}

String extractJSONString(const String& json, const String& key) {
  int keyIdx = json.indexOf(key);
  if (keyIdx == -1) return "";
  int colonIdx = json.indexOf(':', keyIdx);
  if (colonIdx == -1) return "";

  int valueStart = colonIdx + 1;
  while (valueStart < json.length() &&
         (json[valueStart] == ' ' || json[valueStart] == '\t' ||
          json[valueStart] == '\r' || json[valueStart] == '\n')) {
    valueStart++;
  }

  if (valueStart >= json.length() || json[valueStart] != '"') return "";

  int startQuote = valueStart;
  int endQuote = json.indexOf('"', startQuote + 1);
  if (endQuote == -1) return "";
  return json.substring(startQuote + 1, endQuote);
}

bool extractJSONBool(const String& json, const String& key) {
  int keyIdx = json.indexOf(key);
  if (keyIdx == -1) return false;
  int colonIdx = json.indexOf(':', keyIdx);
  if (colonIdx == -1) return false;

  int commaIdx = json.indexOf(',', colonIdx);
  int braceIdx = json.indexOf('}', colonIdx);
  int endIdx = (commaIdx != -1 && commaIdx < braceIdx) ? commaIdx : braceIdx;
  if (endIdx == -1) endIdx = json.length();

  String valStr = json.substring(colonIdx + 1, endIdx);
  valStr.trim();

  return (valStr == "true");
}

// ===== LOG THỜI GIAN =====
void logMs(const char* label, uint32_t t0) {
  Serial.printf("[TIME] %-28s +%lu ms\n", label, (unsigned long)(millis() - t0));
}

// ===== CAMERA =====
bool setupCamera() {
  camera_config_t config = {};
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer   = LEDC_TIMER_0;

  config.pin_d0 = Y2_GPIO_NUM; config.pin_d1 = Y3_GPIO_NUM;
  config.pin_d2 = Y4_GPIO_NUM; config.pin_d3 = Y5_GPIO_NUM;
  config.pin_d4 = Y6_GPIO_NUM; config.pin_d5 = Y7_GPIO_NUM;
  config.pin_d6 = Y8_GPIO_NUM; config.pin_d7 = Y9_GPIO_NUM;
  config.pin_xclk  = XCLK_GPIO_NUM;
  config.pin_pclk  = PCLK_GPIO_NUM;
  config.pin_vsync = VSYNC_GPIO_NUM;
  config.pin_href  = HREF_GPIO_NUM;
  config.pin_sccb_sda = SIOD_GPIO_NUM;
  config.pin_sccb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn  = PWDN_GPIO_NUM;
  config.pin_reset = RESET_GPIO_NUM;
  config.xclk_freq_hz = 20000000;
  config.pixel_format = PIXFORMAT_JPEG;

  config.frame_size   = FRAMESIZE_QVGA;
  config.jpeg_quality = 25;

  // ESP32-CAM AI Thinker thường có PSRAM. Nếu không có PSRAM, dùng 1 buffer cho an toàn.
  if (psramFound()) {
    config.fb_count = 2;
    config.fb_location = CAMERA_FB_IN_PSRAM;
    config.grab_mode = CAMERA_GRAB_LATEST;
  } else {
    config.fb_count = 1;
    config.fb_location = CAMERA_FB_IN_DRAM;
    config.grab_mode = CAMERA_GRAB_WHEN_EMPTY;
  }

  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("[CAM] esp_camera_init FAILED: 0x%x\n", err);
    return false;
  }

  Serial.println("[CAM] esp_camera_init OK");
  return true;
}

// ===== SOCKET / HTTP HELPER =====
bool waitAvailable(WiFiClient& c, uint32_t timeoutMs) {
  uint32_t start = millis();
  while (c.connected() && !c.available()) {
    if (millis() - start >= timeoutMs) return false;
    vTaskDelay(pdMS_TO_TICKS(1));
  }
  return c.available() > 0;
}

bool readLineHttp(WiFiClient& c, String& line, uint32_t timeoutMs) {
  line = "";
  uint32_t start = millis();

  while (millis() - start < timeoutMs) {
    while (c.available()) {
      char ch = (char)c.read();
      if (ch == '\r') continue;
      if (ch == '\n') return true;
      line += ch;

      // Chống header lỗi quá dài làm đầy RAM.
      if (line.length() > 512) return false;
    }

    if (!c.connected() && !c.available()) return false;
    vTaskDelay(pdMS_TO_TICKS(1));
  }

  return false;
}

bool writeAll(WiFiClient& c, const uint8_t* data, size_t len, size_t& totalSent) {
  size_t sent = 0;
  uint32_t start = millis();

  while (sent < len) {
    size_t remaining = len - sent;
    size_t chunkSize = remaining < WRITE_CHUNK_SIZE ? remaining : WRITE_CHUNK_SIZE;
    size_t n = c.write(data + sent, chunkSize);
    if (n > 0) {
      sent += n;
      totalSent += n;
      start = millis();
    } else {
      if (millis() - start > CONNECT_TIMEOUT_MS) return false;
      vTaskDelay(pdMS_TO_TICKS(1));
    }
  }

  return true;
}

bool writeAllString(WiFiClient& c, const String& s, size_t& totalSent) {
  return writeAll(c, (const uint8_t*)s.c_str(), s.length(), totalSent);
}

bool readHttpResponseBody(WiFiClient& c, String& body, int& statusCode, int& contentLength, uint32_t tFrame) {
  body = "";
  statusCode = -1;
  contentLength = -1;

  if (!waitAvailable(c, FIRST_BYTE_TIMEOUT_MS)) {
    Serial.println("[HTTP] Timeout waiting first response byte");
    return false;
  }

  logMs("server bat dau phan hoi", tFrame);

  String line;
  if (!readLineHttp(c, line, FIRST_BYTE_TIMEOUT_MS)) {
    Serial.println("[HTTP] Cannot read status line");
    return false;
  }

  // Ví dụ: HTTP/1.1 200 OK
  int firstSpace = line.indexOf(' ');
  if (firstSpace > 0 && line.length() >= firstSpace + 4) {
    statusCode = line.substring(firstSpace + 1, firstSpace + 4).toInt();
  }

  // Đọc header đến dòng rỗng.
  while (true) {
    if (!readLineHttp(c, line, FIRST_BYTE_TIMEOUT_MS)) {
      Serial.println("[HTTP] Header read timeout/error");
      return false;
    }

    if (line.length() == 0) break;

    String lower = line;
    lower.toLowerCase();
    if (lower.startsWith("content-length:")) {
      String v = line.substring(line.indexOf(':') + 1);
      v.trim();
      contentLength = v.toInt();
    }
  }

  if (contentLength < 0) {
    Serial.println("[HTTP] Missing Content-Length -> close socket");
    return false;
  }

  body.reserve(contentLength + 1);

  uint32_t lastByteTime = millis();
  while ((int)body.length() < contentLength) {
    while (c.available() && (int)body.length() < contentLength) {
      body += (char)c.read();
      lastByteTime = millis();
    }

    if ((int)body.length() >= contentLength) break;

    if (millis() - lastByteTime > BODY_READ_TIMEOUT_MS) {
      Serial.printf("[HTTP] Body timeout: got %d/%d bytes\n", body.length(), contentLength);
      return false;
    }

    if (!c.connected() && !c.available()) {
      Serial.printf("[HTTP] Socket closed early: got %d/%d bytes\n", body.length(), contentLength);
      return false;
    }

    vTaskDelay(pdMS_TO_TICKS(1));
  }

  logMs("doc xong response", tFrame);
  return true;
}

void handleServerJson(const String& jsonOnly) {
  bool invalidCard = extractJSONBool(jsonOnly, "\"invalid_card\"");
  bool cardValid = extractJSONBool(jsonOnly, "\"card_valid\"");
  bool isViolation = extractJSONBool(jsonOnly, "\"created\"");
  int streakVal = extractJSONInt(jsonOnly, "\"eye_closed_streak\"");
  int turnVal = extractJSONInt(jsonOnly, "\"head_turn_score\"");
  String kind = extractJSONString(jsonOnly, "\"violation_kind\"");
  String pStatus = extractJSONString(jsonOnly, "\"phone_status\"");

  Serial.printf("[AI] card_valid=%d, invalid_card=%d, created=%d, streak=%d, turn=%d, kind=%s, phone=%s\n",
                cardValid, invalidCard, isViolation, streakVal, turnVal, kind.c_str(), pStatus.c_str());

  if (invalidCard) {
    portENTER_CRITICAL(&sharedMux);
    isShooting = false;
    cardConfirmed = false;
    currentRFID[0] = '\0';
    portEXIT_CRITICAL(&sharedMux);

    Serial.println("UART_CMD:INVALID_CARD");
    return;
  }

  if (isViolation) {
    portENTER_CRITICAL(&sharedMux);
    cardConfirmed = true;
    portEXIT_CRITICAL(&sharedMux);

    if (kind == "eye") {
      Serial.println("UART_CMD:SLEEP");
    } else if (pStatus == "PHONE" || kind == "phone") {
      Serial.println("UART_CMD:PHONE");
    } else if (kind == "head") {
      Serial.println("UART_CMD:TURN");
    }
    return;
  }

  if (cardValid) {
    bool shouldNotifyCardOk = false;

    portENTER_CRITICAL(&sharedMux);
    if (!cardConfirmed) {
      cardConfirmed = true;
      shouldNotifyCardOk = true;
    }
    portEXIT_CRITICAL(&sharedMux);

    if (shouldNotifyCardOk) {
      Serial.println("UART_CMD:CARD_OK");
    }
  }
}

// ===== GỬI ẢNH =====
bool sendPhotoFast(const char* rfid_uid) {
  uint32_t tFrame = millis();

  camera_fb_t* fb = esp_camera_fb_get();
  if (!fb) {
    Serial.println("[CAM] esp_camera_fb_get FAILED");
    return false;
  }

  logMs("chup anh xong", tFrame);
  Serial.printf("[CAM] image size = %u bytes\n", (unsigned int)fb->len);
  Serial.printf("[WiFi] RSSI = %d dBm\n", WiFi.RSSI());

  bool ok = false;
  size_t totalSent = 0;

  // Use a fresh socket per frame so a late response cannot corrupt the next request.
  client.stop();
  uint32_t tConnect = millis();
  if (!client.connect(serverHost, serverPort, CONNECT_TIMEOUT_MS)) {
    Serial.println("[NET] Connect FAILED -> close socket");
    client.stop();
    esp_camera_fb_return(fb);
    return false;
  }
  Serial.printf("[NET] Connected in %lu ms\n", (unsigned long)(millis() - tConnect));
  client.setNoDelay(true);

  String boundary = "----ESP32";
  String head1 = "--" + boundary + "\r\n"
                 "Content-Disposition: form-data; name=\"card_uid\"\r\n\r\n";

  String head2 = "\r\n--" + boundary + "\r\n"
                 "Content-Disposition: form-data; name=\"image\"; filename=\"c.jpg\"\r\n"
                 "Content-Type: image/jpeg\r\n\r\n";

  String tail = "\r\n--" + boundary + "--\r\n";

  uint32_t contentLen = head1.length()
                      + strlen(rfid_uid)
                      + head2.length()
                      + fb->len
                      + tail.length();

  String reqHeader = String("POST ") + serverPath + " HTTP/1.1\r\n" +
                     "Host: " + serverHost + "\r\n" +
                     "Connection: close\r\n" +
                     "Content-Type: multipart/form-data; boundary=" + boundary + "\r\n" +
                     "X-DEVICE-TOKEN: " + deviceToken + "\r\n" +
                     "Content-Length: " + String(contentLen) + "\r\n\r\n";

  uint32_t tWrite = millis();
  bool sendOk = writeAllString(client, reqHeader, totalSent)
             && writeAllString(client, head1, totalSent)
             && writeAll(client, (const uint8_t*)rfid_uid, strlen(rfid_uid), totalSent)
             && writeAllString(client, head2, totalSent)
             && writeAll(client, fb->buf, fb->len, totalSent)
             && writeAllString(client, tail, totalSent);
  Serial.printf("[NET] write_ms = %lu\n", (unsigned long)(millis() - tWrite));

  logMs("gui xong request", tFrame);

  size_t expectedSent = reqHeader.length() + contentLen;
  Serial.printf("[HTTP] sent=%u/%u bytes\n", (unsigned int)totalSent, (unsigned int)expectedSent);

  esp_camera_fb_return(fb);

  if (!sendOk || totalSent != expectedSent) {
    Serial.println("[HTTP] Send incomplete/error -> close socket");
    client.stop();
    return false;
  }

  String responseBody;
  int statusCode = -1;
  int responseLen = -1;

  if (!readHttpResponseBody(client, responseBody, statusCode, responseLen, tFrame)) {
    Serial.println("[HTTP] Read response FAILED -> close socket");
    client.stop();
    return false;
  }

  Serial.printf("[HTTP] status=%d, content_length=%d, body_read=%d\n",
                statusCode, responseLen, responseBody.length());

  if (statusCode < 200 || statusCode >= 300) {
    Serial.println("[HTTP] Bad status -> close socket");
    client.stop();
    return false;
  }

  int jsonBodyStart = responseBody.indexOf('{');
  if (jsonBodyStart != -1) {
    String jsonOnly = responseBody.substring(jsonBodyStart);
    handleServerJson(jsonOnly);
  } else {
    Serial.println("[HTTP] Body has no JSON object");
  }

  logMs("tong thoi gian frame", tFrame);
  client.stop();
  ok = true;
  return ok;
}

// ===== LUỒNG CAMERA CORE 0 =====
void cameraStreamTask(void *parameter) {
  for (;;) {
    TickType_t frameStart = xTaskGetTickCount();

    if (WiFi.status() != WL_CONNECTED) {
      Serial.println("[WiFi] Disconnected -> reconnect");
      client.stop();
      WiFi.disconnect();
      WiFi.reconnect();
      vTaskDelay(pdMS_TO_TICKS(1000));
      continue;
    }

    bool shootingNow;
    char rfidCopy[32];

    portENTER_CRITICAL(&sharedMux);
    shootingNow = isShooting;
    strlcpy(rfidCopy, currentRFID, sizeof(rfidCopy));
    portEXIT_CRITICAL(&sharedMux);

    if (shootingNow) {
      bool ok = sendPhotoFast(rfidCopy);
      if (!ok) {
        Serial.println("[FRAME] sendPhotoFast FAILED");
      }
    }

    TickType_t elapsed = xTaskGetTickCount() - frameStart;
    if (elapsed < FRAME_INTERVAL) {
      vTaskDelay(FRAME_INTERVAL - elapsed);
    }
  }
}

// ===== SETUP =====
void setup() {
  Serial.begin(115200);
  Serial.setTimeout(20);
  pinMode(4, OUTPUT);

  if (!setupCamera()) {
    Serial.println("[BOOT] Camera init failed. Restarting...");
    delay(2000);
    ESP.restart();
  }

  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) {
    delay(300);
    Serial.println("Connecting WiFi...");
  }
  WiFi.setSleep(false);

  Serial.print("[WiFi] OK, IP=");
  Serial.println(WiFi.localIP());
  Serial.printf("[WiFi] sleep=OFF, RSSI=%d dBm\n", WiFi.RSSI());
  Serial.println("WiFi OK. Quet the de bat dau...");

  xTaskCreatePinnedToCore(
    cameraStreamTask, "CameraTask", 10240, NULL, 1, NULL, 0
  );
}

// ===== LOOP CORE 1 =====
void loop() {
  if (Serial.available()) {
    String rfid_code = Serial.readStringUntil('\n');
    rfid_code.trim();

    if (rfid_code.length() >= 6 &&
        rfid_code.indexOf("UART") == -1 &&
        rfid_code.indexOf("WiFi") == -1) {

      digitalWrite(4, HIGH);
      delay(100);
      digitalWrite(4, LOW);

      portENTER_CRITICAL(&sharedMux);
      isShooting = true;
      cardConfirmed = false;
      strlcpy(currentRFID, rfid_code.c_str(), sizeof(currentRFID));
      portEXIT_CRITICAL(&sharedMux);

      Serial.println("BAT DAU STREAM VOI THE: " + rfid_code);
    }
  }

  vTaskDelay(pdMS_TO_TICKS(10));
}
