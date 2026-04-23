from win32com.client import Dispatch 
from datetime import datetime
import glob
import re
import os

def fn_Handshake(model : str, operation : str, serial : str):
    print("fn_Handshake")
    lib = Dispatch("FITSDLL.clsDB")
    fn_initDB = lib.fn_InitDB(f"{model}",f"{operation}","2.90","dbInnoviz")
    if fn_initDB == "True":
        fn_handshake = lib.fn_Handshake(f"{model}",f"{operation}","2.90",f"{serial}")
        if fn_handshake == "True":
            lib.closeDB()
            return True
        else:
            lib.closeDB()
            return fn_handshake
    else:
        lib.closeDB()
        return False

def fn_Log(model : str, operation : str, parameters : str, values : str):
    list_parameters = {}
    lib = Dispatch("FITSDLL.clsDB")
    ## Define Shift 
    start_day_shift = datetime.strptime("07:00","%H:%M").time()
    end_day_shift = datetime.strptime("19:00","%H:%M").time()
    if start_day_shift <= datetime.now().time() <= end_day_shift:
        list_parameters["Shift"] = "DAY"
    else:
        list_parameters["Shift"] = "NIGHT"
    list_parameters["MC"] = os.environ['COMPUTERNAME']
    parameters = parameters + "," + "Shift" + "," + "MC"
    values =  values + "," + list_parameters["Shift"] + "," + list_parameters["MC"]
    fn_initDB = lib.fn_InitDB(f"{model}",f"{operation}","2.90","dbInnoviz")
    if fn_initDB == "True":
        fn_log = lib.fn_Log(f"{model}",f"{operation}","2.90",f"{parameters}",f"{values}",",")
        print(fn_log)
        if fn_log == "True":
            lib.closeDB()
            return True
        else:
            lib.closeDB()
            return fn_log 
    else:
        lib.closeDB()
        return False

def fn_Query(model : str, operation : str, serial : str, query_parameters : str):
    lib = Dispatch("FITSDLL.clsDB")
    query_array = []

    fn_initDB = lib.fn_InitDB(f"{model}",f"{operation}","2.90","dbInnoviz")
    if fn_initDB == "True":
        for param in query_parameters.split(','):
            fn_query = lib.fn_Query(f"{model}",f"{operation}","2.90",f"{serial}",f"{param}",",")
            fn_query = str(fn_query)
            query_values = fn_query.replace("-,","").replace(",-","").replace("-","")
            query_array.append(query_values)
        query_result = ",".join(query_array)
        lib.closeDB()
        return query_result
    else:
        lib.closeDB()
        return False
    
def fn_FitsDebugging():
    FitsLog_Dir = "C:\\TEMP\\FITSDLL_LOG\\*.log"
    datetime_pattern = r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}"
    newest_datetime = None
    newest_log = None

    files = glob.glob(FitsLog_Dir)
    max_file = max(files, key=os.path.getctime)
    with open(max_file, "r") as read_log:
        for line in read_log:
            match = re.search(datetime_pattern, line)
            if match:
                current_datetime = datetime.strptime(match.group(), "%Y-%m-%d %H:%M:%S")
                
                if newest_datetime is None or current_datetime > newest_datetime:
                    newest_datetime = current_datetime
                    newest_log = line

    if newest_datetime:
        # print("Newest Log:\t", newest_log)
        output = newest_log.split("\n")[0]
    else:
        # print("No valid log")
        output = "No valid log"

    return output

# parameters = "EN,MC,PN,SN,Oven Machine,Temp target (°C),Time target (minute),Start time,End time,Result (Graph),Result (csv file),Result,Shift"
# values = "524161,NOTE-DELL5588,TEST,COBTESTOB240,MC,25,1,2026-01-22_14-07-15,2026-01-22_14-08-15,C:\Projects\\novus_Temp_log\\Log\\Plot_Oven_2026-02-25_10-52-06 copy.jpg,C:\\Projects\\novus_Temp_log\\Log\\COBTESTOB240_OB240_ORA848066_2026-03-19_11-32-18 copy.csv,PASS,DAYs"
# a = fn_Log("OB assy", "OB240", parameters, values)
# print(a)
# print(fn_Handshake("*", "IN260", "CIN254300296"))

# # lib = Dispatch("FITSDLL.clsDB")
# # print(dir(lib))
# print(fn_Query("*", "*", "CIN260500007", "#next_opn"))


# x = "C:\Projects\novus_Temp_log\Log\COBTESTOB240Plot_Oven_2026-01-22_13-38-02.jpg"
# print(repr(x).replace("'", ""))