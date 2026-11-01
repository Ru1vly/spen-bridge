/* Exercise production descriptor/CLI validation without opening any device. */
#define main relay_program_main
#include "../../native/usb-relay/main.c"
#undef main
#include <assert.h>
int main(void) {
    struct libusb_device_descriptor d={.idVendor=0x18d1, .idProduct=0x2d00};
    assert(accessory(&d));
    d.idProduct=0x2d05; assert(accessory(&d));
    d.idProduct=0x2d02; assert(!accessory(&d));
    d.idVendor=0x04e8; d.idProduct=0x2d00; assert(!accessory(&d));
    struct libusb_endpoint_descriptor ep[2]={
        {.bEndpointAddress=0x81, .bmAttributes=LIBUSB_TRANSFER_TYPE_BULK},
        {.bEndpointAddress=0x02, .bmAttributes=LIBUSB_TRANSFER_TYPE_BULK}};
    struct libusb_interface_descriptor alt[2]={
        {.bInterfaceNumber=0, .bInterfaceClass=0xff, .bInterfaceSubClass=0xff,
         .bInterfaceProtocol=0, .bNumEndpoints=2, .endpoint=ep},
        {.bInterfaceNumber=1, .bInterfaceClass=0xff, .bInterfaceSubClass=0x42,
         .bInterfaceProtocol=1, .bNumEndpoints=2, .endpoint=ep}};
    struct libusb_interface interfaces[2]={
        {.altsetting=&alt[0], .num_altsetting=1}, {.altsetting=&alt[1], .num_altsetting=1}};
    struct libusb_config_descriptor config={.bNumInterfaces=2, .interface=interfaces};
    struct usb_session s={0};
    assert(endpoints_from_config(&config, &s) == 0 && s.in == 0x81 && s.out == 0x02);
    alt[0].bInterfaceProtocol=1; assert(endpoints_from_config(&config, &s) < 0);
    alt[0].bInterfaceProtocol=0;
    alt[0].bAlternateSetting=1; assert(endpoints_from_config(&config, &s) < 0);
    alt[0].bAlternateSetting=0;
    ep[1].bEndpointAddress=0x82; assert(endpoints_from_config(&config, &s) < 0);
    ep[1].bEndpointAddress=0x02;
    ep[1].bmAttributes=LIBUSB_TRANSFER_TYPE_INTERRUPT; assert(endpoints_from_config(&config, &s) < 0);
    ep[1].bmAttributes=LIBUSB_TRANSFER_TYPE_BULK;
    alt[1].bInterfaceSubClass=0xff; alt[1].bInterfaceProtocol=0;
    assert(endpoints_from_config(&config, &s) < 0); /* Ambiguous duplicate. */
    assert(number("65535", 65535) == 65535);
    assert(number("65536", 65535) < 0 && number("-1", 65535) < 0);
    assert(number("1.5", 65535) < 0 && number("1x", 65535) < 0 && number("", 65535) < 0);
    return 0;
}
