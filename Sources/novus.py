from pymodbus.client import ModbusSerialClient
import serial.tools.list_ports
from datetime import datetime

def find_datalog_port():
    DATALOG_LIST = {}
    port_list = []
    ports = serial.tools.list_ports.comports()
    for p in ports:
        if p.description.startswith('LogBox-WiFi'):
            port_list.append(p.device)
    if not port_list:
        return None
    for comport in port_list:
        logbox = ModbusSerialClient(port=comport, baudrate=9600, timeout=1)
        result = logbox.read_holding_registers(address=0x03, count=100)
        mac_index = result.registers[2:5]
        # print(mac_index)
        mac_bytes = []
        for reg in mac_index:
            high_byte = (reg >> 8) & 0xFF
            low_byte = reg & 0xFF
            mac_bytes.extend([high_byte, low_byte])
            mac_str = ":".join(f"{b:02X}" for b in mac_bytes)
        # print("MAC ADDRSS: ", mac_str)
        DATALOG_LIST[comport] = mac_str
    return DATALOG_LIST
        
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

# x = find_datalog_port()
# print(x)