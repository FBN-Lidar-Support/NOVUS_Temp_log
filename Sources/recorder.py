"""Save the result of one bake: graph + csv, one named copy per serial, log to FITs.
No GUI code in here: the caller passes in how to save the graph image
(save_image) and how to log to FITs (log_fn).
"""
import os
import shutil
import time
from datetime import datetime
import pandas as pd
TIME_FMT = "%Y-%m-%d_%H-%M-%S"
class RecordError(Exception):
    pass
class LiveLog:
    """Writes every reading to disk as it arrives, so a crash does not lose the run."""
    def __init__(self, log_path: str, oven_id: str):
        stamp = datetime.now().strftime(TIME_FMT)
        self.path = os.path.join(log_path, f"LIVE_{oven_id}_{stamp}.csv")
    def start(self):
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                f.write("Datetime,Oven Tempture,Oven Status\n")
        except OSError as e:
            print(f"Can not create live file: {e}")
            self.path = None
    def append(self, now, temp, state):
        if not self.path:
            return
        try:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(f"{now:%Y-%m-%d %H:%M:%S},{temp},{state}\n")
        except OSError as e:
            print(f"Can not write live file: {e}")
    def remove(self):
        """Delete the checkpoint once everything is safely in FITs."""
        if not self.path:
            return
        try:
            os.remove(self.path)
        except OSError as e:
            print(f"Can not remove live file: {e}")
def record_results(log_path, run, oven_id, employee_id, machine, table_df, save_image, log_fn, settle_seconds=0.5):
    """Write graph + csv and log every serial in table_df to FITs.
    table_df columns: Serial Number, Part Number, Operation, Product Model
    (and Sub-Serial for IN323).
    Returns a list of (serial, message) for serials FITs refused; empty = all OK.
    Raises RecordError / OSError when the files can not be written.
    """
    if table_df.empty:
        raise RecordError("No serial to record")
    df_result = pd.DataFrame({
        "Datetime": run.times,
        "Oven Tempture": run.temps,
        "Oven Status": run.states,
    })
    datetimestart = run.times[0].strftime(TIME_FMT)
    datetimeend = run.times[-1].strftime(TIME_FMT)
    # {OPN} is replaced per serial below
    img_filename = os.path.join(log_path, f"_{{OPN}}_ORA{oven_id}_{datetimeend}.jpg")
    save_image(img_filename)
    time.sleep(settle_seconds)
    if not os.path.exists(img_filename):
        raise RecordError("Can not generate image file")
    csv_filename = os.path.join(log_path, f"_{{OPN}}_ORA{oven_id}_{datetimeend}.csv")
    df_result.to_csv(csv_filename, index=False)
    if not os.path.exists(csv_filename):
        raise RecordError(f"Can not create csv file: {csv_filename}")
    failures = []
    for _, row in table_df.iterrows():
        serial = row["Serial Number"]
        pn = row["Part Number"]
        opn = row["Operation"]
        product = row["Product Model"]
        # All serials of the batch share one csv/graph. Each serial gets its own
        # copy named with its SN, so FITs can pick it up (and even delete it)
        # without affecting the next serial.
        new_csv_filename = os.path.join(log_path, serial + os.path.basename(csv_filename)).replace("{OPN}", opn)
        new_img_filename = os.path.join(log_path, serial + os.path.basename(img_filename)).replace("{OPN}", opn)
        try:
            shutil.copyfile(csv_filename, new_csv_filename)
            shutil.copyfile(img_filename, new_img_filename)
        except OSError as e:
            failures.append((serial, f"Can not prepare files: {e}"))
            continue
        print(new_csv_filename)
        print(new_img_filename)
        new_csv_filename = new_csv_filename.replace("\\", "\\\\")
        new_img_filename = new_img_filename.replace("\\", "\\\\")
        print("===============================================================")
        df_fits = {
            "EN": str(employee_id),
            "MC": str(machine),
            "PN": str(pn),
            "SN": str(serial),
            "Oven Machine": str(oven_id),
            "Temp target (°C)": str(run.temp_target),
            "Time target (minute)": str(int(run.hold_seconds / 60)),
            "Start time": str(datetimestart),
            "End time": str(datetimeend),
            "Result (Graph)": new_img_filename,
            "Result (csv file)": new_csv_filename,
            "Result": "PASS",
        }
        if opn == "IN323":
            df_fits["Fixture"] = row["Sub-Serial"]
        parameters = ",".join(df_fits.keys())
        values = ",".join(df_fits.values())
        try:
            log_status = log_fn(product, opn, parameters, values)
        except Exception as e:
            log_status = f"{type(e).__name__}: {e}"
        if log_status == True:
            print(f"Serial: {serial} FITs Completed")
        else:
            print(f"Serial: {serial} FITs not Complete")
            print(log_status)
            failures.append((serial, str(log_status)))
        print()
    print("===============================================================")
    for path in (csv_filename, img_filename):   # the shared {OPN} originals are no longer needed
        try:
            os.remove(path)
        except OSError as e:
            print(f"Can not remove {path}: {e}")
    return failures