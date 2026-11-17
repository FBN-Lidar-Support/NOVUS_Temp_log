from pymodbus.client import ModbusSerialClient
import serial.tools.list_ports
from datetime import datetime
# CHx_STATUS register: 1=OK, 2=Underflow, 3=Overflow, 4=Cold joint error, 5=Open sensor
STATUS_OK = 1
# (status, value) index inside the block read from address 0x03 (count=100)
CH_REGS = {1: (78, 79), 2: (82, 83), 3: (86, 87)}
class LogboxReadError(Exception):
    """Raised when a LogBox can not be opened or returns a Modbus error."""
def _read_block(comport: str):
    client = ModbusSerialClient(port=comport, baudrate=9600, timeout=1)
    try:
        if not client.connect():
            raise LogboxReadError(f"Can not open {comport}")
        result = client.read_holding_registers(address=0x03, count=100)
        if result is None or result.isError():
            raise LogboxReadError(f"Modbus error on {comport}: {result}")
        return result.registers
    except LogboxReadError:
        raise
    except Exception as e:
        raise LogboxReadError(f"{comport}: {e}") from e
    finally:
        client.close()
def _signed16(value: int) -> int:
    return value - 65536 if value >= 32768 else value
def _channel(registers, channel: int):
    ch_state, ch_value = CH_REGS.get(channel, CH_REGS[1])
    return registers[ch_state], _signed16(int(registers[ch_value])) / 10
def find_datalog_port():
    DATALOG_LIST = {}
    for p in serial.tools.list_ports.comports():
        if not p.description.startswith('LogBox-WiFi'):
            continue
        try:
            registers = _read_block(p.device)
        except LogboxReadError as e:
            print(f"Skip {p.device}: {e}")
            continue
        mac_bytes = []
        for reg in registers[2:5]:
            mac_bytes.extend([(reg >> 8) & 0xFF, reg & 0xFF])
        DATALOG_LIST[p.device] = ":".join(f"{b:02X}" for b in mac_bytes)
    return DATALOG_LIST or None
def read_temp(comport: str = "COM4", channel: int = 1):
    """Return (datetime, status, temp_C). Raises LogboxReadError on failure."""
    registers = _read_block(comport)
    now = datetime.now()
    status, temp = _channel(registers, channel)
    return now, status, temp
def readmuti_temp(comport: str = "COM4", channel_list: list = [1, 2, 3]):
    """Return [datetime, status1, temp1, status2, temp2, ...]. Raises LogboxReadError."""
    registers = _read_block(comport)
    log_array = [datetime.now()]
    for ch in (1, 2, 3):
        if ch in channel_list:
            status, temp = _channel(registers, ch)
            log_array.extend([status, temp])
    return log_array