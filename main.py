import wx
import wx.grid
import serial
import matplotlib.pyplot as plt
from matplotlib.backends.backend_wxagg import FigureCanvasWxAgg as FigureCanvas
from collections import deque
import threading
import time

class SwitchMonitor(wx.Frame):
    def __init__(self):
        super().__init__(None, title="Arduino Switch Monitor", size=(1200, 800))
        
        # Инициализация данных
        self.num_pots = 8  # Аналоговые входы
        self.history_size = 100
        self.timestamps = deque(maxlen=self.history_size)
        self.voltage_data = [deque(maxlen=self.history_size) for _ in range(self.num_pots)]
        self.raw_data = [deque(maxlen=self.history_size) for _ in range(self.num_pots)]
        self.switch_state = [False, False, False]  # [Pos1, Neutral, Pos2]
        
        # Цвета
        self.colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728',
                     '#9467bd', '#8c564b', '#e377c2', '#7f7f7f']
        
        # Настройка интерфейса
        self.init_ui()
        
        # Подключение к Arduino
        self.serial_port = None
        self.serial_thread = None
        self.running = False
        self.connect_serial()
        
        # Таймер
        self.timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.update_display, self.timer)
        self.timer.Start(100)
        
        self.start_time = time.time()
    
    def init_ui(self):
        panel = wx.Panel(self)
        vbox = wx.BoxSizer(wx.VERTICAL)
        
        # Панель состояния переключателя
        switch_box = wx.StaticBox(panel, label="Switch State")
        switch_sizer = wx.StaticBoxSizer(switch_box, wx.HORIZONTAL)
        
        self.switch_labels = [
            wx.StaticText(panel, label="Left 1 (D9): OFF"),
            wx.StaticText(panel, label="Right (D12): OFF"),
        ]
        
        for label in self.switch_labels:
            switch_sizer.Add(label, 1, wx.EXPAND|wx.ALL, 10)
        
        vbox.Add(switch_sizer, 0, wx.EXPAND|wx.ALL, 10)
        
        # Таблица аналоговых значений
        self.grid = wx.grid.Grid(panel)
        self.grid.CreateGrid(self.num_pots, 3)
        self.grid.SetColLabelValue(0, "Channel")
        self.grid.SetColLabelValue(1, "Raw Value")
        self.grid.SetColLabelValue(2, "Voltage (V)")
        
        for i in range(self.num_pots):
            self.grid.SetRowLabelValue(i, f"A{i}")
            self.grid.SetCellValue(i, 0, f"A{i}")
            self.grid.SetCellAlignment(i, 0, wx.ALIGN_CENTER, wx.ALIGN_CENTER)
            self.grid.SetCellAlignment(i, 1, wx.ALIGN_CENTER, wx.ALIGN_CENTER)
            self.grid.SetCellAlignment(i, 2, wx.ALIGN_CENTER, wx.ALIGN_CENTER)
            self.grid.SetReadOnly(i, 0, True)
        
        vbox.Add(self.grid, 0, wx.EXPAND|wx.LEFT|wx.RIGHT|wx.BOTTOM, 10)
        
        # График
        self.figure = plt.figure(figsize=(12, 5))
        self.ax = self.figure.add_subplot(111)
        self.setup_plot()
        self.canvas = FigureCanvas(panel, -1, self.figure)
        vbox.Add(self.canvas, 1, wx.EXPAND|wx.LEFT|wx.RIGHT|wx.BOTTOM, 10)
        
        # Панель управления
        control_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.status_label = wx.StaticText(panel, label="Status: Disconnected")
        control_sizer.Add(self.status_label, 1, wx.ALIGN_CENTER_VERTICAL|wx.LEFT, 10)
        
        self.connect_btn = wx.Button(panel, label="Connect")
        self.connect_btn.Bind(wx.EVT_BUTTON, self.on_connect)
        control_sizer.Add(self.connect_btn, 0, wx.ALL, 5)
        
        self.clear_btn = wx.Button(panel, label="Clear Data")
        self.clear_btn.Bind(wx.EVT_BUTTON, self.on_clear)
        control_sizer.Add(self.clear_btn, 0, wx.ALL, 5)
        
        vbox.Add(control_sizer, 0, wx.EXPAND|wx.BOTTOM, 10)
        panel.SetSizer(vbox)
        
        self.Layout()
    
    def setup_plot(self):
        self.ax.clear()
        self.ax.set_title('Analog Inputs Monitoring')
        self.ax.set_xlabel('Time (s)')
        self.ax.set_ylabel('Voltage (V)')
        self.ax.set_ylim(-0.1, 5.2)
        self.ax.grid(True, linestyle='--', alpha=0.6)
        
        self.lines = []
        for i, color in enumerate(self.colors):
            line, = self.ax.plot([], [], color=color, linewidth=2, label=f'A{i}')
            self.lines.append(line)
        
        self.ax.legend(bbox_to_anchor=(1.02, 1), loc='upper left')
        self.figure.tight_layout(rect=[0, 0, 0.85, 1])
    
    def connect_serial(self):
        if self.running:
            self.running = False
            if self.serial_thread:
                self.serial_thread.join(timeout=1)
        
        try:
            self.serial_port = serial.Serial('COM3', 115200, timeout=1)
            time.sleep(2)
            self.running = True
            self.serial_thread = threading.Thread(target=self.read_serial_data)
            self.serial_thread.daemon = True
            self.serial_thread.start()
            self.status_label.SetLabel("Status: Connected to COM3")
            self.connect_btn.SetLabel("Reconnect")
            return True
        except serial.SerialException as e:
            self.status_label.SetLabel(f"Status: Error - {str(e)}")
            return False
    
    def read_serial_data(self):
        buffer = ""
        while self.running and self.serial_port and self.serial_port.is_open:
            try:
                if self.serial_port.in_waiting:
                    buffer += self.serial_port.read(self.serial_port.in_waiting).decode('ascii', errors='ignore')
                    
                    if '\n' in buffer:
                        lines = buffer.split('\n')
                        for line in lines[:-1]:
                            self.process_data(line.strip())
                        buffer = lines[-1]
                time.sleep(0.01)
            except Exception as e:
                print(f"Serial error: {e}")
                time.sleep(0.1)
    
    def process_data(self, line):
        if not line.startswith('SW:'):
            return
        
        # Разделяем строку на части
        parts = line.split('|')
        if len(parts) < 2:
            return
        
        # Обработка состояния переключателей
        if len(parts[0]) >= 5:  # "SW:01"
            switch_part = parts[0][3:5]
            self.switch_state = [
                switch_part[0] == '1',
                switch_part[1] == '1'
            ]
        
        # Обновляем временную метку
        current_time = time.time() - self.start_time
        self.timestamps.append(current_time)
        
        # Обработка аналоговых данных
        for part in parts[1:]:
            if not part.startswith('A'):
                continue
                
            try:
                channel_part, data_part = part.split(':', 1)
                channel_num = int(channel_part[1:])
                
                if 0 <= channel_num < self.num_pots:
                    raw_str, voltage_str = data_part.split(';')
                    raw_value = int(raw_str)
                    voltage = float(voltage_str[:-1])  # Удаляем 'V'
                    
                    self.raw_data[channel_num].append(raw_value)
                    self.voltage_data[channel_num].append(voltage)
                    
                    # Отладочный вывод
                    print(f"A{channel_num}: {voltage:.2f}V")
                    
            except (ValueError, IndexError) as e:
                print(f"Error parsing data: {e}")

    def update_display(self, event):
        # Обновление состояния переключателей
        states = ["OFF", "ON"]
        self.switch_labels[0].SetLabel(f"Left (D9): {states[self.switch_state[0]]}")
        self.switch_labels[1].SetLabel(f"Right (D12): {states[self.switch_state[1]]}")
        
        # Цветовая индикация
        for i, label in enumerate(self.switch_labels):
            label.SetForegroundColour(wx.GREEN if self.switch_state[i] else wx.RED)
        
        # Обновление таблицы
        for i in range(self.num_pots):
            if self.voltage_data[i]:
                voltage = self.voltage_data[i][-1]
                raw = self.raw_data[i][-1]
                
                self.grid.SetCellValue(i, 1, str(raw))
                self.grid.SetCellValue(i, 2, f"{voltage:.2f}")
                
                # Подсветка активных каналов
                color = wx.YELLOW if raw > 10 else wx.WHITE
                self.grid.SetCellBackgroundColour(i, 1, color)
                self.grid.SetCellBackgroundColour(i, 2, color)
        
        # Обновление графика
        if len(self.timestamps) > 0:
            for i in range(self.num_pots):
                if len(self.voltage_data[i]) > 0:
                    # Синхронизируем данные по времени
                    min_len = min(len(self.timestamps), len(self.voltage_data[i]))
                    x_data = list(self.timestamps)[-min_len:]
                    y_data = list(self.voltage_data[i])[-min_len:]
                    self.lines[i].set_data(x_data, y_data)
            
            # Автомасштабирование
            self.ax.relim()
            self.ax.autoscale_view()
            if len(self.timestamps) > 1:
                self.ax.set_xlim(max(0, self.timestamps[0]), self.timestamps[-1] + 0.1)
        
        self.canvas.draw()
        self.grid.ForceRefresh()
    
    def on_connect(self, event):
        if self.connect_serial():
            wx.MessageBox("Connected successfully!", "Info", wx.OK|wx.ICON_INFORMATION)
    
    def on_clear(self, event):
        self.timestamps.clear()
        for i in range(self.num_pots):
            self.voltage_data[i].clear()
            self.raw_data[i].clear()
            self.grid.SetCellValue(i, 1, "")
            self.grid.SetCellValue(i, 2, "")
            self.grid.SetCellBackgroundColour(i, 1, wx.WHITE)
            self.grid.SetCellBackgroundColour(i, 2, wx.WHITE)
        self.setup_plot()
        self.canvas.draw()
    
    def on_exit(self, event):
        self.running = False
        if self.serial_port:
            self.serial_port.close()
        self.Destroy()

if __name__ == "__main__":
    app = wx.App(False)
    frame = SwitchMonitor()
    frame.Show()
    app.MainLoop()