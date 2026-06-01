#include <Arduino.h>
#include <SPI.h>
#include <MFRC522.h>
#include "AudioGeneratorMP3.h"
#include "AudioOutputI2S.h"
#include "AudioFileSourcePROGMEM.h"

// ===== CẤU HÌNH RFID =====
#define SS_PIN 5
#define RST_PIN 22 
MFRC522 rfid(SS_PIN, RST_PIN);
unsigned long lastScanTime = 0; 

// ===== CÁC MẢNG ÂM THANH I2S (MAX98357A) =====
// 1. Quét thẻ thành công
const uint8_t success_mp3[] PROGMEM = {
  //tôi cắt ra bớt để bớt dài, ko cần quan tâm cái này
};

// 2. Lỗi Ngủ gật
const uint8_t alarm_sleep_mp3[] PROGMEM = {
  //tôi cắt ra bớt để bớt dài, ko cần quan tâm cái này

};

// 3. Lỗi Điện thoại
const uint8_t alarm_phone_mp3[] PROGMEM = {
 //tôi cắt ra bớt để bớt dài, ko cần quan tâm cái này

};

// 4. Lỗi Mất tập trung/Quay đầu
const uint8_t alarm_turn_mp3[] PROGMEM = {
 //tôi cắt ra bớt để bớt dài, ko cần quan tâm cái này

};

AudioGeneratorMP3 *mp3;
AudioFileSourcePROGMEM *file;
AudioOutputI2S *out;
bool isPlaying = false; 

void setup() {
  Serial.begin(115200); 
  Serial2.begin(115200, SERIAL_8N1, 16, 17); // Giao tiếp UART với ESP32-CAM
  
  // Chống treo mạch khi đọc UART
  Serial2.setTimeout(20);
  
  SPI.begin();
  rfid.PCD_Init();

  audioLogger = &Serial;
  out = new AudioOutputI2S();
  out->SetPinout(26, 25, 27); // BCLK=26, LRC=25, DIN=27
  out->SetGain(0.8); 
  
  mp3 = new AudioGeneratorMP3();
  Serial.println("\n[ESP32 THUONG] San sang quet the va phat 4 loai am thanh...");
}

void loop() {
  // 1. DUY TRÌ LUỒNG ÂM THANH KHÔNG BLOCK
  if (isPlaying && mp3->isRunning()) {
    if (!mp3->loop()) {
      mp3->stop();
      delete file; 
      isPlaying = false;
      Serial.println("[LOA] Da phat xong am thanh.");
    }
  }

  // 2. NHẬN LỆNH BÁO ĐỘNG TỪ ESP32-CAM
  if (Serial2.available()) {
    String cmd = Serial2.readStringUntil('\n');
    cmd.trim(); 
    
    if (!isPlaying) {
      if (cmd == "UART_CMD:SLEEP") {
        Serial.println("[!] LOI: NGU GAT -> Phat loa");
        file = new AudioFileSourcePROGMEM(alarm_sleep_mp3, sizeof(alarm_sleep_mp3));
        mp3->begin(file, out);
        isPlaying = true;
      } 
      else if (cmd == "UART_CMD:PHONE") {
        Serial.println("[!] LOI: DIEN THOAI -> Phat loa");
        file = new AudioFileSourcePROGMEM(alarm_phone_mp3, sizeof(alarm_phone_mp3));
        mp3->begin(file, out);
        isPlaying = true;
      }
      else if (cmd == "UART_CMD:TURN") {
        Serial.println("[!] LOI: MAT TAP TRUNG -> Phat loa");
        file = new AudioFileSourcePROGMEM(alarm_turn_mp3, sizeof(alarm_turn_mp3));
        mp3->begin(file, out);
        isPlaying = true;
      }
    }
  }

  // 3. KIỂM TRA THẺ RFID 
  if (rfid.PICC_IsNewCardPresent() && rfid.PICC_ReadCardSerial()) {
    if (millis() - lastScanTime >= 1500) {
      String uid = "";
      for (byte i = 0; i < rfid.uid.size; i++) {
        uid += String(rfid.uid.uidByte[i] < 0x10 ? "0" : "");
        uid += String(rfid.uid.uidByte[i], HEX);
      }
      uid.toUpperCase();

      Serial.println("[RFID] Da quet the: " + uid);
      Serial2.println(uid); 

      if (!isPlaying) {
        Serial.println("[LOA] Phat: Quet the thanh cong");
        file = new AudioFileSourcePROGMEM(success_mp3, sizeof(success_mp3));
        mp3->begin(file, out);
        isPlaying = true;
      }
      lastScanTime = millis(); 
    }
    rfid.PICC_HaltA();
    rfid.PCD_StopCrypto1();
  }
}