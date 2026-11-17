import os
import sys
import pandas as pd
import configparser
import pygetwindow as gw
from PyQt6 import uic, QtWidgets
from PyQt6.QtWidgets import QApplication, QHeaderView, QMainWindow, QInputDialog, QLineEdit, QTableWidget, QTableWidgetItem, QMessageBox
from PyQt6.QtCore import QTimer, QUrl, Qt
from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as Canvas
import matplotlib.dates as mdates
from novus import read_temp, find_datalog_port, LogboxReadError, STATUS_OK
from fitsdll import fn_Handshake, fn_Query, fn_Log
from oven_run import OvenRun
from recorder import LiveLog, record_results
# from webservice import FITS_Web_Serivce
# Matplotlib canvas class to create figure
class MplCanvas(Canvas):
    def __init__(self, parent=None):
        self.fig = Figure()
        self.ax = self.fig.add_subplot(111)
        super().__init__(self.fig)
        self.setParent(parent)
        # self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        self.updateGeometry()
    def save_image(self, filepath):
        self.figure.savefig(
            filepath,
            dpi=150,
            bbox_inches="tight"
        )
class MainAppWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = "--disable-gpu --disable-software-rasterizer"
        self.allow_close = False
        self.MC = os.environ.get('COMPUTERNAME')
        print(self.MC)
        self.config = configparser.ConfigParser()
        try:
            self.config.read(r"C:\Projects\novus_Temp_log\Properties\Config.ini")
            self.LogPath = self.config["DEFAULT"].get("LogPath", "")
            self.tick_speed = self.config["DEFAULT"].getint("tick_speed", 10)
        except Exception as e:
            QMessageBox.critical(None, "Close Program", f"{e}\nPlease check config.ini")
            self.exit_confirm_enabled = False
            quit()
        if not os.path.exists(self.LogPath):
            os.makedirs(self.LogPath, exist_ok=True)
        if self.MC not in self.config:
            QMessageBox.critical(None, "Close Program", f"Computer name '{self.MC}' not found in Config.ini\nPlease check config.ini")
            sys.exit(1)
        uic.loadUi(r"C:\Projects\novus_Temp_log\Sources\GUI\Main_UI.ui", self)
        self.TableWidget.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        comport_list = find_datalog_port()
        if not comport_list:
            QMessageBox.critical(self, "Datalog disconnect", "Datalog COMPORT not found\nPlease check USB cable from Data logger to PC")
            quit()
            
        print(comport_list)
        self.oven_port = {}
        for port, mac in comport_list.items():
            ORA_OVEN = self.config[self.MC].get(mac.replace(":", "-"), "").strip()
            if not ORA_OVEN:
                print(f"Datalog {mac} on {port} is not in Config.ini [{self.MC}], skipped")
                continue
            self.oven_port[ORA_OVEN.upper()] = port
        if not self.oven_port:
            QMessageBox.critical(self, "Datalog not in config", f"No datalog on this PC is listed in Config.ini [{self.MC}]\nPlease check config.ini")
            sys.exit(1)
        if not os.path.exists(self.LogPath):
            os.makedirs(self.LogPath, exist_ok= True)
        
        self.canvas = MplCanvas(self)
        layout = self.GraphWidget.layout()
        if layout is None:
            layout = QtWidgets.QVBoxLayout(self.GraphWidget)
            layout.setContentsMargins(0,0,0,0)
            layout.setSpacing(0)
            self.GraphWidget.setLayout(layout)
        layout.addWidget(self.canvas)
        self.canvas.ax.set_title("Oven Temperature")
        self.canvas.ax.set_xlabel("Time (H:M:S)")
        self.canvas.ax.set_ylabel("Temperature (°C)")
        self.canvas.ax.grid(True)
        self.canvas.ax.xaxis.set_major_formatter(
            mdates.DateFormatter("%H:%M:%S")
        )
        self.canvas.fig.autofmt_xdate()
        self.temp_target = None
        self.hold_seconds = None
        
        self.span = None
        self.serial_list = []
        self.read_fail_count = 0
        self.run = None    # OvenRun: readings + hold-time logic of the current bake
        self.live = None   # LiveLog: checkpoint file written on every reading
        (self.line,) = self.canvas.ax.plot([], [], linewidth = 2)
        self.canvas.draw()
        
        self.EN_Value.setFocus()
        self.QuitButton.clicked.connect(self.on_quit_clicked)
        self.StartButton.clicked.connect(self.on_start_clicked)
        self.AddSNButton.clicked.connect(self.Add_Serials)
        
        QTimer.singleShot(100, self.select_ORA)
    def select_ORA(self):
        ORA_list = list(self.oven_port.keys())
        ORA_list = list(map(str.upper, ORA_list))
        oven_name, ok = QInputDialog.getItem(self, "Choose Oven ORA#", "Choose Oven:", ORA_list, 0, False)
        if not ok:
            print("Quit Program")
            quit()
        port = self.oven_port[oven_name]
        WINDOW_NAME = f"Auto_TempLog_{port}"        
        windows = gw.getWindowsWithTitle(WINDOW_NAME)
        if not windows:
            self.setWindowTitle(WINDOW_NAME)
            self.COMPORT = port
            self.comport_value.setText(port)
            self.Oven_ID.setText(oven_name)
            return
        else:
            QMessageBox.warning(self, "Oven Occupied", f"{oven_name} already running!\nPlease change Oven")
            QTimer.singleShot(100, self.select_ORA)
    def on_start_clicked(self):
        print("start")
        if len(self.EN_Value.text()) != 6:
            QMessageBox.warning(self, "Start denied", "employee ID must have 6 digit")
            return
        if self.Oven_ID.text() == "":
            QMessageBox.warning(self, "Start denied", "Please scan Oven ID before press start")
            return
        if self.TableWidget.rowCount() == 0:
            QMessageBox.warning(self, "Start denied", 'Please Press button "Add serial" to add serial before press start')
            return
        temp_target = int(self.Target.currentText().split("°C")[0])
        hold_seconds = int(self.Duration.currentText().split("(")[1].split("sec)")[0])
        allowed = self.allowed_operations(temp_target, hold_seconds)
        bad = []
        for r in range(self.TableWidget.rowCount()):
            sn = self.TableWidget.item(r, 0)
            opn = self.TableWidget.item(r, 3)
            if opn is None or opn.text() not in allowed:
                bad.append(f"{sn.text() if sn else '?'} ({opn.text() if opn else '?'})")
        if bad:
            QMessageBox.warning(self, "Start denied",
                                f"These serials can not be baked at {temp_target}°C / {hold_seconds} sec:\n"
                                + "\n".join(bad) +
                                "\nPlease change Target / Duration or remove the serial.")
            return
        self.StartButton.setEnabled(False)
        self.reset_run()
        self.run = OvenRun(temp_target, hold_seconds)
        self.Oven_Status.setText("Operate")
        self.Oven_Status.setStyleSheet("background-color: orange; color black; font-weight: bold;")
        self.QuitButton.setEnabled(False)
        self.live = LiveLog(self.LogPath, self.Oven_ID.text().strip())
        self.live.start()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_graph)
        self.timer.start((self.tick_speed * 1000)) # read temp speed per point
    def Add_Serials(self):
        cancal = False
        while not cancal:
            self.temp_target = int(self.Target.currentText().split("°C")[0])
            self.hold_seconds = int(self.Duration.currentText().split("(")[1].split("sec)")[0])
            serial, okPressed = QInputDialog.getText(self, "Insert Serial", "Please Insert serial:")
            if okPressed and serial:
                if serial in self.serial_list:
                    QMessageBox.warning(self, "Duplicate Serial", f"Serial: {serial} already registered")
                    continue
                # query = self.fits.FIT_Query("*", "*", serial, "#NEXT_OPN,#SHIPDATE,#Part_No,#product").split(",")
                query_result = fn_Query("*", "*", serial, "#NEXT_OPN,#SHIPDATE,#Part_No,#product")
                if not query_result:
                    QMessageBox.critical(self, "FITS ERROR", "Can not query FITs\nPlease check FITs connection")
                    continue
                query = [q.strip() for q in query_result.split(",")]
                print(query)
                if len(query) < 4 or all(q in ("", "None") for q in query):
                    QMessageBox.warning(self, "Serial not found", f"Serial {serial} not found in FITs")
                    continue
                next_opn = query[0]
                shipdate = query[1]
                part_no = query[2]
                product = query[3]
                opn_list = self.allowed_operations(self.temp_target, self.hold_seconds)
                if shipdate == "" or shipdate == "-":
                    if next_opn in opn_list:
                        self.serial_list.append(serial)
                        row = self.TableWidget.rowCount()
                        self.TableWidget.insertRow(row)
                        self.TableWidget.setItem(row, 0, QTableWidgetItem(serial))
                        self.TableWidget.setItem(row, 1, QTableWidgetItem(part_no))
                        self.TableWidget.setItem(row, 2, QTableWidgetItem(product))
                        self.TableWidget.setItem(row, 3, QTableWidgetItem(next_opn))
                        if next_opn == "IN323":
                            target_header = "Sub-Serial"
                            baking_col = -1
                            # เช็คก่อนว่ามี column Baking Clamp อยู่แล้วไหม
                            for col in range(self.TableWidget.columnCount()):
                                header_item = self.TableWidget.horizontalHeaderItem(col)
                                if header_item is not None and header_item.text() == target_header:
                                    baking_col = col
                                    break
                            # ถ้ายังไม่มี ค่อยเพิ่ม column ใหม่
                            if baking_col == -1:
                                baking_col = self.TableWidget.columnCount()
                                self.TableWidget.insertColumn(baking_col)
                                self.TableWidget.setHorizontalHeaderItem(baking_col, QTableWidgetItem(target_header))
                            subserial, okPressed = QInputDialog.getText(self, "Scan Weight jig", "Please Insert serial Weight jig:")
                            if okPressed:
                                self.TableWidget.setItem(row, baking_col, QTableWidgetItem(subserial))
                    else:
                        QMessageBox.critical(self, "FITS ERROR", f"Serial {serial} can not oven on this setting")
                elif query[1]:
                    QMessageBox.critical(self, "FITS ERROR", f"Serial {serial} has already shiped on {shipdate}")
                    continue
            else:
                cancal = True
    def update_graph(self):
        try:
            now, status, temp = read_temp(self.COMPORT, 1)
        except LogboxReadError as e:
            self.handle_read_failure(str(e))
            return
        if status != STATUS_OK:
            # 2=Underflow, 3=Overflow, 4=Cold joint error, 5=Open sensor
            self.handle_read_failure(f"channel status = {status} (5 = open sensor)")
            return
        if self.read_fail_count:
            self.read_fail_count = 0
            self.Oven_Status.setText("Operate")
            self.Oven_Status.setStyleSheet("background-color: orange; color black; font-weight: bold;")
        # ----- store reading -----
        state = self.run.add_reading(now, temp)
        self.live.append(now, temp, state)
        # ----- live plot -----
        x_num = mdates.date2num(self.run.times)
        self.line.set_data(x_num, self.run.temps)
        if state == "Heated":
            if self.span is not None:
                self.span.remove()
            self.span = self.canvas.ax.axvspan(
                mdates.date2num(self.run.trigger_time),
                x_num[-1],
                color="orange",
                alpha=0.25,
                zorder=0
            )
        # ----- countdown -----
        minutes = self.run.minutes_left(now)
        if minutes is not None:
            self.TimeLeftLabel.setText(f"{minutes} mins." if minutes > 1 else "< 1 mins.")
            if self.run.is_finished(now):
                self.timer.stop()
                self.TimeLeftLabel.setText("Done")
                print("Done")
                QTimer.singleShot(100, self.Result_insert_and_record)
                return
        # ----- write Graph with new data -----
        self.canvas.ax.relim()
        self.canvas.ax.autoscale_view()
        self.canvas.draw_idle() # update Graph

    def Result_insert_and_record(self):
        try:
            failures = record_results(
                log_path=self.LogPath,
                run=self.run,
                oven_id=self.Oven_ID.text().strip(),
                employee_id=self.EN_Value.text().strip(),
                machine=self.MC,
                table_df=self.qtable_to_df(self.TableWidget),
                save_image=self.canvas.save_image,
                log_fn=fn_Log,
            )
        except Exception as e:
            QMessageBox.critical(self, "FAIL record fits", f"{e}\nPlease contact Engineer\n(LIVE file is kept in {self.LogPath})")
            self.StartButton.setEnabled(True)
            self.QuitButton.setEnabled(True)
            return
        if failures:
            detail = "\n".join(f"{sn}: {msg}" for sn, msg in failures)
            QMessageBox.critical(self, "FITs insert failed", f"Please conact EXT:7763 Atthaphanp\n{detail}")
        else:
            self.live.remove()  # checkpoint no longer needed
        self.Oven_Status.setText("Idle")
        self.Oven_Status.setStyleSheet("background-color: rgb(170, 255, 127); color black; font-weight: bold;")
        self.TableWidget.setRowCount(0)
        self.serial_list.clear()
        QMessageBox.information(self, "Finish Oven Record", "Please remove unit out of oven")
        self.StartButton.setEnabled(True)
        self.QuitButton.setEnabled(True)
    def reset_run(self):
        self.span = None
        self.canvas.ax.clear()
        self.canvas.ax.set_title("Oven Temperature")
        self.canvas.ax.set_xlabel("Time (H:M:S)")
        self.canvas.ax.set_ylabel("Temperature (°C)")
        self.canvas.ax.grid(True)
        self.canvas.ax.xaxis.set_major_formatter(
            mdates.DateFormatter("%H:%M:%S")
            )
        self.line, = self.canvas.ax.plot([], [], color= "black")
        self.canvas.draw_idle()
        self.TimeLeftLabel.setText("Waiting...")
    def on_quit_clicked(self):
        self.allow_close = True
        self.close()
    def closeEvent(self, event):
        if self.allow_close:
            print("Close Software")
            event.accept()
        else:
            event.ignore()
    def allowed_operations(self, temp_target, hold_seconds):
        raw = self.config["Operation Config"].get(f"{temp_target}-{hold_seconds}", "")
        return [o.strip() for o in raw.split(",") if o.strip()]
    # -------------------- Read errors --------------------
    def handle_read_failure(self, reason):
        self.read_fail_count += 1
        print(f"Read failed ({self.read_fail_count}): {reason}")
        self.Oven_Status.setText(f"Read error x{self.read_fail_count}")
        self.Oven_Status.setStyleSheet("background-color: red; color: white; font-weight: bold;")
    # -------------------- Helper --------------------
    def qtable_to_df(self, table):
        header = []
        cols = []
        
        for c in range(table.columnCount()):
            item = table.horizontalHeaderItem(c)
            if item is None:
                continue
            text = item.text().strip()
            if not text:
                continue
            header.append(text)
            cols.append(c)
        
        data = []
        for r in range(table.rowCount()):
            row = {}
            for h, c in zip(header, cols):
                cell = table.item(r, c)
                row[h] = cell.text() if cell else ""
            data.append(row)
        return pd.DataFrame(data)
    
if __name__ == "__main__":
    # QApplication.setAttribute(Qt.AA_DontCreateNativeWidgetSiblings, True)
    app = QApplication(sys.argv)
    main_window = MainAppWindow()
    main_window.showFullScreen()
    sys.exit(app.exec())