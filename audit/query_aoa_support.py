"""Read AOA protocol version only. Never sends START or changes USB mode."""
import ctypes as C
import ctypes.util
import json
from pathlib import Path

class Descriptor(C.Structure):
    _fields_=[('length',C.c_uint8),('type',C.c_uint8),('usb',C.c_uint16),('device_class',C.c_uint8),('subclass',C.c_uint8),('protocol',C.c_uint8),('packet_size',C.c_uint8),('vendor',C.c_uint16),('product',C.c_uint16),('release',C.c_uint16),('manufacturer',C.c_uint8),('product_string',C.c_uint8),('serial',C.c_uint8),('configs',C.c_uint8)]

lib=C.CDLL(ctypes.util.find_library('usb-1.0'))
lib.libusb_init.argtypes=[C.POINTER(C.c_void_p)];lib.libusb_init.restype=C.c_int
lib.libusb_get_device_list.argtypes=[C.c_void_p,C.POINTER(C.POINTER(C.c_void_p))];lib.libusb_get_device_list.restype=C.c_ssize_t
lib.libusb_get_device_descriptor.argtypes=[C.c_void_p,C.POINTER(Descriptor)];lib.libusb_get_device_descriptor.restype=C.c_int
lib.libusb_open.argtypes=[C.c_void_p,C.POINTER(C.c_void_p)];lib.libusb_open.restype=C.c_int
lib.libusb_control_transfer.argtypes=[C.c_void_p,C.c_uint8,C.c_uint8,C.c_uint16,C.c_uint16,C.POINTER(C.c_ubyte),C.c_uint16,C.c_uint];lib.libusb_control_transfer.restype=C.c_int
lib.libusb_close.argtypes=[C.c_void_p];lib.libusb_free_device_list.argtypes=[C.POINTER(C.c_void_p),C.c_int];lib.libusb_exit.argtypes=[C.c_void_p]
context=C.c_void_p();assert lib.libusb_init(C.byref(context))==0
listing=C.POINTER(C.c_void_p)();results=[]
try:
 count=lib.libusb_get_device_list(context,C.byref(listing))
 for i in range(count):
  descriptor=Descriptor()
  if lib.libusb_get_device_descriptor(listing[i],C.byref(descriptor)) or descriptor.vendor!=0x04e8:continue
  handle=C.c_void_p();opened=lib.libusb_open(listing[i],C.byref(handle))
  result=dict(vendor=hex(descriptor.vendor),product=hex(descriptor.product),open_result=opened,usb_mode_changed=False)
  if opened==0:
   try:
    data=(C.c_ubyte*2)()
    status=lib.libusb_control_transfer(handle,0xc0,51,0,0,data,2,1000)
    result['get_protocol_result']=status
    if status==2:result['aoa_protocol_version']=int(data[0])|(int(data[1])<<8)
   finally:lib.libusb_close(handle)
  results.append(result)
finally:
 if listing:lib.libusb_free_device_list(listing,1)
 lib.libusb_exit(context)
out=Path('audit/evidence/passive-tracing-2026-10-31/aoa-support.json');out.write_text(json.dumps(results,indent=2));print(json.dumps(results,indent=2))
