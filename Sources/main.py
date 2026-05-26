import os
import sys
import time
import pandas as pd
import configparser
from datetime import timedelta
from PyQt6 import uic, QtWidgets
from PyQt6.QtWidgets import QApplication, QHeaderView, QMainWindow, QInputDialog, QLineEdit, QTableWidget, QTableWidgetItem, QMessageBox
from PyQt6.QtCore import QTimer, QUrl, Qt
from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as Canvas
import matplotlib.dates as mdates

from novus import read_temp, find_datalog_port
from fitsdll import fn_Handshake, fn_Query, fn_Log
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
        self.config = configparser.ConfigParser()
        try:
            self.config.read(r"C:\Projects\novus_Temp_log\Properties\Config.ini")
            self.LogPath = self.config["DEFAULT"].get("LogPath", "")
            self.tick_speed = self.config["DEFAULT"].getint("tick_speed", 10)
        except Exception as e:
            QMessageBox.critical(None, "Close Program", f"{e}\nPlease check config.ini")
            self.exit_confirm_enabled = False
            quit()

        # self.fits = FITS_Web_Serivce()
        # if self.fits.getStatusURL() != "OK":
        #     QMessageBox(self, "FITS Connection Failed", "Please check internet connnection to connect to Fabrinet server.")
        #     quit()

        if not os.path.exists(self.LogPath):
            os.makedirs(self.LogPath, exist_ok=True)

        uic.loadUi(r"C:\Projects\novus_Temp_log\Sources\GUI\Main_UI.ui", self)
        self.TableWidget.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

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
        
        self.trigger_region = None
        self.trigger_time = None
        self.stop_time = None
        self.triggered = False
        self.span = None

        self.serial_list = []

        # self.max_points = 600 
        # self.x_live = deque(maxlen=self.max_points)
        # self.y_live = deque(maxlen=self.max_points)
        self.x_live = []
        self.y_live = []

        (self.line,) = self.canvas.ax.plot([], [], linewidth = 2)

        self.oven_status = []

        self.canvas.draw()
        
        self.EN_Value.setFocus()
        self.EN_Value.returnPressed.connect(self.Oven_ID.setFocus)
        self.QuitButton.clicked.connect(self.on_quit_clicked)
        self.StartButton.clicked.connect(self.on_start_clicked)
        self.AddSNButton.clicked.connect(self.Add_Serials)

    def on_start_clicked(self):
        self.StartButton.setEnabled(False)
        print("start")
        self.reset_run()
        if len(self.EN_Value.text()) == 6:
            if not self.Oven_ID.text() == "":
                if self.TableWidget.rowCount() != 0:
                    self.Oven_Status.setText("Operate")
                    self.Oven_Status.setStyleSheet("background-color: orange; color black; font-weight: bold;")
                    self.temp_target = int(self.Target.currentText().split("°C")[0])
                    self.hold_seconds = int(self.Duration.currentText().split("(")[1].split("sec)")[0])
                    self.QuitButton.setEnabled(False)
                    self.timer = QTimer(self)
                    self.timer.timeout.connect(self.update_graph)
                    self.timer.start((self.tick_speed * 1000)) # read temp speed per point
                else:
                    QMessageBox.warning(self, "Start denied", """Please Press button "Add serial" to add serial before press start""")
            else:
                QMessageBox.warning(self, "Start denied", "Please scan Oven ID before press start")
        else:
            QMessageBox.warning(self, "Start denied", "employee ID must have 6 digit")

    def Add_Serials(self):
        cancal = False
        while not cancal:
            self.temp_target = int(self.Target.currentText().split("°C")[0])
            self.hold_seconds = int(self.Duration.currentText().split("(")[1].split("sec)")[0])
            serial, okPressed = QInputDialog.getText(self, "Insert Serial", "Please Insert serial:")
            if okPressed and serial:
                if serial in self.serial_list:
                    QMessageBox(self, "Duplicate Serial", f"Serial: {serial} already registered")
                    continue
                # query = self.fits.FIT_Query("*", "*", serial, "#NEXT_OPN,#SHIPDATE,#Part_No,#product").split(",")
                query = fn_Query("*", "*", serial, "#NEXT_OPN,#SHIPDATE,#Part_No,#product").split(",")
                print(query)
                if query == [''] or query == ['None']:
                    continue
                next_opn = query[0]
                shipdate = query[1]
                part_no = query[2]
                product = query[3]
                opn_list = self.config["Operation Config"].get(f"{self.temp_target}-{self.hold_seconds}", "").split(",")
                if shipdate == "" or shipdate == "-":
                    if next_opn in opn_list:
                        self.serial_list.append(serial)
                        row = self.TableWidget.rowCount()
                        self.TableWidget.insertRow(row)
                        self.TableWidget.setItem(row, 0, QTableWidgetItem(serial))
                        self.TableWidget.setItem(row, 1, QTableWidgetItem(part_no))
                        self.TableWidget.setItem(row, 2, QTableWidgetItem(product))
                        self.TableWidget.setItem(row, 3, QTableWidgetItem(next_opn))
                    else:
                        QMessageBox.critical(self, "FITS ERROR", f"Serial {serial} can not oven on this setting")
                elif query[1]:
                    QMessageBox.critical(self, "FITS ERROR", f"Serial {serial} has already shiped on {shipdate}")
                    continue
            else:
                cancal = True

    def update_graph(self):
        now, status, temp = read_temp(self.comport, 1)fgdfdhfgh
        # ----- live plot -----
        self.x_live.append(now)
        # self.y_live.append(temp+0.5)
        self.y_live.append(temp)

        x_num = mdates.date2num(list(self.x_live))
        self.line.set_data(x_num, list(self.y_live))

        if self.triggered and self.trigger_time is not None:
            self.oven_status.append("Heated")
            t0 = mdates.date2num(self.trigger_time)
            t1 = x_num[-1]

            if self.span is not None:
                self.span.remove()
            
            self.span = self.canvas.ax.axvspan(
                t0, 
                t1, 
                color="orange",
                alpha=0.25,
                zorder=0
            )
        else:
            self.oven_status.append("Warm-Up")

        # ----- trigger ครั้งแรก -----
        if self.trigger_time is None and temp >= self.temp_target:
            self.trigger_time = now
            self.stop_time = now + timedelta(seconds=self.hold_seconds)
            self.triggered = True

        # ----- countdown -----
        if self.stop_time is not None:
            remaining = int((self.stop_time - now).total_seconds() / 60)
            if remaining > 1:
                self.TimeLeftLabel.setText(f"{max(0, remaining)} mins.")
            else:
                self.TimeLeftLabel.setText("< 1 mins.")
            if now >= self.stop_time:
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
        mc_oven = self.Oven_ID.text().strip()
        df_result = pd.DataFrame({"Datetime": self.x_live, "Oven Tempture": self.y_live, "Oven Status": self.oven_status})
        # df_result_filtered = df_result["Oven Status"] == "Heated"
        # print(df_result_filtered)

        Qtable_df = self.qtable_to_df(self.TableWidget)
        # print(Qtable_df)
        
        datetimestart = df_result["Datetime"].iloc[0].strftime("%Y-%m-%d_%H-%M-%S")
        datetimeend = df_result["Datetime"].iloc[-1].strftime("%Y-%m-%d_%H-%M-%S")        

        img_filename = os.path.join(self.LogPath, f"_{{OPN}}_ORA{mc_oven}_{datetimeend}.jpg")
        self.canvas.save_image(img_filename)
        time.sleep(0.5)
        if os.path.exists(img_filename):
            pass
        else:
            QMessageBox.critical(self, "FAIL record fits", "Can not generate image file\nPlease contact Engineer",)
            return
        
        csv_filename = os.path.join(self.LogPath, f"_{{OPN}}_ORA{mc_oven}_{datetimeend}.csv")
        df_result.to_csv(csv_filename, index=False)
        en = self.EN_Value.text().strip()

        old_csv_filename = None
        old_img_filename = None
        
        for idx, row in Qtable_df.iterrows():
            serial = row["Serial Number"]
            # print("serial:\t", serial)
            pn = row["Part Number"]
            opn = row["Operation"]
            product = row["Product Model"]
            new_csv_filename = os.path.join(self.LogPath, serial + os.path.basename(csv_filename)).replace("{OPN}", opn)
            new_img_filename = os.path.join(self.LogPath, serial + os.path.basename(img_filename)).replace("{OPN}", opn)
            if not old_csv_filename:
                os.rename(csv_filename, new_csv_filename)
            else:
                os.rename(old_csv_filename, new_csv_filename)
            print(new_csv_filename)
            new_csv_filename = new_csv_filename.replace("\\","\\\\")
            if not old_img_filename:
                os.rename(img_filename, new_img_filename)
            else:
                os.rename(old_img_filename, new_img_filename)   
            print(new_img_filename)
            new_img_filename = new_img_filename.replace("\\","\\\\")
            print("===============================================================")
            df_fits = {
                "EN": str(en),
                "MC": str(self.MC),
                "PN": str(pn),
                "SN": str(serial),
                "Machine": str(mc_oven),
                "Temp target (°C)": str(self.temp_target),
                "Time target (minute)": str(int(self.hold_seconds/60)),
                "Start time": str(datetimestart),
                "End time": str(datetimeend),
                "Result (Graph)": new_img_filename,
                "Result (csv file)": new_csv_filename,
                "Result": "PASS"
            }

            parameters = ",".join(df_fits.keys())
            values = ",".join(df_fits.values())

            # log_status = self.fits.FIT_Log(product, opn, parameters, values)
            log_status = fn_Log(product, opn, parameters, values)
            if log_status == True:
                print(f"Serial: {serial} FITs Completed")
            else:
                print(f"Serial: {serial} FITs not Complete")
                print(log_status)
                QMessageBox.critical(self, "FITs insert failed", f"Please conact EXT:7763 Atthaphanp\n{log_status}")
            old_csv_filename = new_csv_filename
            old_img_filename = new_img_filename
            
        self.Oven_Status.setText("Idle")
        self.Oven_Status.setStyleSheet("background-color: rgb(170, 255, 127); color black; font-weight: bold;")
        self.TableWidget.setRowCount(0)
        print("===============================================================")
        os.rename(old_csv_filename, csv_filename)
        
        os.rename(old_img_filename, img_filename)
        QMessageBox.information(self, "Finish Oven Record", "Please remove unit out of oven")
        self.StartButton.setEnabled(True)
        self.QuitButton.setEnabled(True)

    def reset_run(self):
        self.trigger_time = None
        self.stop_time = None
        self.triggered = False

        self.temp_target = None
        self.hold_seconds = None

        self.serial_list.clear()

        self.x_live.clear()
        self.y_live.clear()
        self.oven_status.clear()

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