#include <Wire.h>
#include <LiquidCrystal.h>

LiquidCrystal lcd(2, 3, 4, 5, 6, 7);

// Параметры голосования
const byte voting_modes[10][2] = {{2,3}, {2,4}, {2,5}, {2,6}, {3,4}, {3,5}, {3,6}, {4,5}, {4,6}, {5,6}};
byte current_mode = 0;
bool averaging_mode = false;
byte selected_channel = 0;

// Потенциометры подключены к A7-A2
const int num_pots = 6;
const int pot_pins[num_pots] = {A7, A6, A5, A4, A3, A2};
int pot_values[num_pots];
const int threshold = 10; // Порог различия значений

// Для хранения результатов голосования
struct VotingResult {
  bool success;
  byte matched_channels[num_pots];
  byte match_count;
  float result_value;
} voting_result;

// Для 3-позиционного переключателя
bool last_switch9_state = HIGH;
bool last_switch12_state = HIGH;
unsigned long last_debounce_time = 0;
const unsigned long debounce_delay = 50;

void lcd_write(byte row, byte column, const String &text) {
  if (row > 1) row = 1;
  if (column > 15) column = 15;
  lcd.setCursor(column, row);
  lcd.print(text);
}

void lcd_clean(bool animate = false) {
  if (animate) {
    for (int i = 0; i < 16; i++) {
      lcd.setCursor(i, 0);
      lcd.print(" ");
      lcd.setCursor(i, 1);
      lcd.print(" ");
      delay(50);
    }
  } else {
    lcd.clear();
  }
}

void setup() {
  Serial.begin(115200);
  lcd.begin(16, 2);
  pinMode(9, INPUT_PULLUP);   // Левый переключатель (канал)
  pinMode(12, INPUT_PULLUP);  // Правый переключатель (режим)
  
  lcd_write(0, 0, "Kaf KTSIU");
  lcd_write(1,0, "lab maj reserv");
  delay(1500);
  lcd_clean(true);
  lcd_write(0,0, "git_src:");
  lcd_write(1,0, "Lolja4you/reserv");
  delay(2750);
  lcd_clean(true);
}

void change_mode() {
  current_mode = (current_mode + 1) % 11; // 10 режимов + усреднение
  if (current_mode == 10) {
    averaging_mode = true;
  } else {
    averaging_mode = false;
  }
}

void change_channel() {
  selected_channel = (selected_channel + 1) % num_pots;
}

void check_voting(int n, int m) {
  // Сбрасываем результаты
  memset(&voting_result, 0, sizeof(voting_result));
  
  // Создаем массив для хранения кластеров совпадающих каналов
  byte clusters[num_pots][num_pots] = {0};
  byte cluster_sizes[num_pots] = {0};
  byte num_clusters = 0;
  bool assigned[num_pots] = {false};
  
  // Формируем кластеры близких значений
  for (int i = 0; i < num_pots; i++) {
    if (!assigned[i]) {
      // Создаем новый кластер
      clusters[num_clusters][cluster_sizes[num_clusters]++] = i;
      assigned[i] = true;
      
      // Ищем все каналы, близкие к текущему
      for (int j = i+1; j < num_pots; j++) {
        if (!assigned[j] && abs(pot_values[i] - pot_values[j]) <= threshold) {
          clusters[num_clusters][cluster_sizes[num_clusters]++] = j;
          assigned[j] = true;
        }
      }
      
      num_clusters++;
    }
  }
  
  // Ищем кластер, удовлетворяющий условиям голосования
  for (int i = 0; i < num_clusters; i++) {
    if (cluster_sizes[i] >= n) { // Проверяем условие n из m
      voting_result.success = true;
      
      // Записываем совпавшие каналы
      for (int j = 0; j < cluster_sizes[i]; j++) {
        voting_result.matched_channels[voting_result.match_count++] = clusters[i][j];
      }
      
      // Рассчитываем среднее значение для этого кластера
      long sum = 0;
      for (int j = 0; j < cluster_sizes[i]; j++) {
        sum += pot_values[clusters[i][j]];
      }
      voting_result.result_value = sum / (float)cluster_sizes[i];
      
      break; // Используем первый подходящий кластер
    }
  }
}

float calculate_average() {
  long sum = 0;
  for (int i = 0; i < num_pots; i++) {
    sum += pot_values[i];
  }
  return sum / (float)num_pots;
}

void send_serial_data() {
  String data = "SW:";
  data += digitalRead(9) ? "0" : "1";
  data += digitalRead(12) ? "0" : "1";
  
  data += "|MODE:";
  if (averaging_mode) {
    data += "AVG";
  } else {
    data += String(voting_modes[current_mode][0]) + "/" + String(voting_modes[current_mode][1]);
  }
  
  data += "|CH:" + String(selected_channel);
  
  for (int i = 0; i < num_pots; i++) {
    data += "|A";
    data += i;
    data += ":";
    data += pot_values[i];
    data += ";";
    data += String(pot_values[i] * 5.0 / 1023.0, 2);
    data += "V";
  }
  
  // Добавляем результат голосования
  if (voting_result.success) {
    data += "|UMJ:" + String(voting_result.result_value, 0);
    data += "|OK:";
    for (int i = 0; i < voting_result.match_count; i++) {
      data += String(voting_result.matched_channels[i]);
    }
  } else {
    data += "|UMJ:0|OK:0";
  }
  
  Serial.println(data);
}

void loop() {
  // Чтение потенциометров
  for (int i = 0; i < num_pots; i++) {
    pot_values[i] = analogRead(pot_pins[i]);
  }
  
  // Обработка переключателей с защитой от дребезга
  bool switch9_state = digitalRead(9);
  bool switch12_state = digitalRead(12);
  
  if ((millis() - last_debounce_time) > debounce_delay) {
    if (switch9_state == LOW && last_switch9_state == HIGH) {
      change_channel();
      last_debounce_time = millis();
    }
    if (switch12_state == LOW && last_switch12_state == HIGH) {
      change_mode();
      last_debounce_time = millis();
    }
  }
  
  last_switch9_state = switch9_state;
  last_switch12_state = switch12_state;
  
  // Проверка голосования (только в режиме голосования)
  if (!averaging_mode) {
    check_voting(voting_modes[current_mode][0], voting_modes[current_mode][1]);
  }
  
  // Обновление дисплея
  update_display();
  
  // Отправка данных
  send_serial_data();
  
  delay(100);
}

void update_display() {
  lcd_clean();
  
  // Первая строка
  String line1;
  if (averaging_mode) {
    line1 = "AVG Mode";
  } else {
    line1 = String(voting_modes[current_mode][0]) + "/" + String(voting_modes[current_mode][1]);
    
    if (voting_result.success) {
      line1 += " OK:";
      for (int i = 0; i < voting_result.match_count && line1.length() < 16; i++) {
        line1 += String(voting_result.matched_channels[i]);
      }
    } else {
      line1 += " NO";
    }
    
    // Обрезаем строку, если она слишком длинная
    if (line1.length() > 16) {
      line1 = line1.substring(0, 16);
    }
  }
  lcd_write(0, 0, line1);
  
  // Вторая строка
  String line2 = "U" + String(selected_channel) + ":";
  line2 += String(pot_values[selected_channel]);
  
  if (averaging_mode) {
    line2 += " AVG:";
    line2 += String(calculate_average(), 0);
  } else {
    line2 += " UMJ:";
    if (voting_result.success) {
      line2 += String(voting_result.result_value, 0);
    } else {
      line2 += "---";
    }
  }
  
  lcd_write(1, 0, line2);
}
