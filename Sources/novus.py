from pymodbus.client import ModbusSerialClient
import time
from datetime import datetime
import matplotlib.pyplot as plt

def read_temp(comport: str="COM4", channel:int=1): 
    logbox = ModbusSerialClient(port=comport, baudrate=9600, timeout=1)
    if channel == 1:
        ch_state = 78
        ch_value = 79
    elif channel == 2:
        ch_state = 82
        ch_value = 83
    elif channel == 3:
        ch_state = 86
        ch_value = 87
    else:
        ch_state = 78
        ch_value = 79
    result = logbox.read_holding_registers(address=0x03, count=100)
    logbox.close()
    now = datetime.now()
    # print(f"full return is {result.registers}")
    return now, result.registers[ch_state], int(result.registers[ch_value])/10

def readmuti_temp(comport: str="COM4", channel_list:list=[1, 2, 3]):
    log_array = []
    now = datetime.now()
    log_array.append(now)

    logbox = ModbusSerialClient(port=comport, baudrate=9600, timeout=1)
    result = logbox.read_holding_registers(address=0x03, count=100)

    if 1 in channel_list:
        log_array.append(result.registers[78])
        log_array.append(int(result.registers[79])/10)
    if 2 in channel_list:
        log_array.append(result.registers[82])
        log_array.append(int(result.registers[83])/10)
    if 3 in channel_list:
        log_array.append(result.registers[86])
        log_array.append(int(result.registers[87])/10)
    logbox.close()
    # print(f"full return is {result.registers}")
    return log_array

# while True:
#     try: 
#         temp_value = readmuti_temp("COM4",1)
#         # temp_value = read_TempAll("COM4")
#         print(temp_value)
#         time.sleep(1)
#     except KeyboardInterrupt:
#         quit()