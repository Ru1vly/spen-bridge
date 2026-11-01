#define _POSIX_C_SOURCE 200809L
#include "relay.h"
#include <arpa/inet.h>
#include <errno.h>
#include <fcntl.h>
#include <libusb.h>
#include <netinet/tcp.h>
#include <poll.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <unistd.h>

struct usb_session { libusb_device_handle *handle; unsigned char in, out; };
static int transfer(void *context, int input, unsigned char *data, int size,
                     int *transferred, unsigned int timeout_ms) {
    struct usb_session *s = context;
    return libusb_bulk_transfer(s->handle, input ? s->in : s->out,
                               data, size, transferred, timeout_ms);
}
static int accessory(const struct libusb_device_descriptor *d) {
    return d->idVendor == 0x18d1 && (d->idProduct == 0x2d00 || d->idProduct == 0x2d01 ||
                                    d->idProduct == 0x2d04 || d->idProduct == 0x2d05);
}
/* Identify accessory bulk only, never the composite device's ADB interface. */
static int endpoints_from_config(const struct libusb_config_descriptor *config, struct usb_session *s) {
    int result = -1, matches = 0;
    for (unsigned int i=0; i<config->bNumInterfaces; i++) {
        const struct libusb_interface *interface = &config->interface[i];
        for (int j=0; j<interface->num_altsetting; j++) {
            const struct libusb_interface_descriptor *a = &interface->altsetting[j];
            if (a->bAlternateSetting || a->bInterfaceClass != 0xff ||
                a->bInterfaceSubClass != 0xff || a->bInterfaceProtocol != 0 || a->bNumEndpoints != 2) continue;
            unsigned char in = 0, out = 0;
            for (unsigned int k=0; k<a->bNumEndpoints; k++) {
                const struct libusb_endpoint_descriptor *e = &a->endpoint[k];
                if ((e->bmAttributes & LIBUSB_TRANSFER_TYPE_MASK) != LIBUSB_TRANSFER_TYPE_BULK) continue;
                if (e->bEndpointAddress & LIBUSB_ENDPOINT_IN) in = e->bEndpointAddress;
                else out = e->bEndpointAddress;
            }
            if (in && out) { matches++; result = a->bInterfaceNumber; s->in=in; s->out=out; }
        }
    }
    return matches == 1 ? result : -1;
}
static int endpoints(libusb_device *device, struct usb_session *s) {
    struct libusb_config_descriptor *config = NULL;
    if (libusb_get_active_config_descriptor(device, &config)) return -1;
    int result = endpoints_from_config(config, s);
    libusb_free_config_descriptor(config);
    return result;
}
static int number(const char *text, unsigned long max) {
    char *end;
    if (*text < '0' || *text > '9') return -1;
    errno = 0;
    unsigned long n = strtoul(text, &end, 10);
    return errno || *end || n > max ? -1 : (int)n;
}
static int connect_local(int port) {
    int fd = socket(AF_INET, SOCK_STREAM | SOCK_CLOEXEC | SOCK_NONBLOCK, 0);
    if (fd < 0) return -1;
    struct sockaddr_in addr = {.sin_family=AF_INET, .sin_port=htons((uint16_t)port)};
    addr.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    int result = connect(fd, (struct sockaddr *)&addr, sizeof(addr));
    if (result && errno == EINPROGRESS) {
        struct pollfd p = {.fd=fd, .events=POLLOUT};
        result = poll(&p, 1, 1000);
        int error = 0;
        socklen_t size = sizeof(error);
        result = result > 0 && !getsockopt(fd, SOL_SOCKET, SO_ERROR, &error, &size) && !error ? 0 : -1;
    }
    if (result) { close(fd); return -1; }
    int enabled = 1;
    if (setsockopt(fd, IPPROTO_TCP, TCP_NODELAY, &enabled, sizeof(enabled))) { close(fd); return -1; }
    return fd;
}
int main(int argc, char **argv) {
    int bus=-1, address=-1, port=-1, seconds=15, list=0;
    if (argc == 2 && !strcmp(argv[1], "--list")) list=1;
    else {
        for (int i=1; i<argc; i+=2) {
            if (i+1 >= argc) goto usage;
            if (!strcmp(argv[i], "--bus")) bus=number(argv[i+1], 255);
            else if (!strcmp(argv[i], "--address")) address=number(argv[i+1], 127);
            else if (!strcmp(argv[i], "--port")) port=number(argv[i+1], 65535);
            else if (!strcmp(argv[i], "--seconds")) seconds=number(argv[i+1], 60);
            else goto usage;
        }
        if (bus < 0 || address < 1 || port < 1 || seconds < 1) goto usage;
    }
    libusb_context *context=NULL;
    int rc=libusb_init(&context);
    if (rc) { fprintf(stderr, "libusb initialization failed: %s\n", libusb_error_name(rc)); return 1; }
    libusb_device **devices=NULL, *selected=NULL;
    ssize_t count=libusb_get_device_list(context, &devices);
    if (count < 0) { libusb_exit(context); return 1; }
    struct usb_session usb={0};
    int interface=-1;
    for (ssize_t i=0; i<count; i++) {
        struct libusb_device_descriptor d;
        if (libusb_get_device_descriptor(devices[i], &d) || !accessory(&d)) continue;
        struct usb_session candidate={0};
        int found=endpoints(devices[i], &candidate);
        if (found < 0) continue;
        if (list) printf("{\"bus\":%u,\"address\":%u,\"interface\":%d,\"in\":%u,\"out\":%u}\n",
                          libusb_get_bus_number(devices[i]), libusb_get_device_address(devices[i]), found, candidate.in, candidate.out);
        else if (libusb_get_bus_number(devices[i]) == bus && libusb_get_device_address(devices[i]) == address) {
            selected=devices[i]; usb=candidate; interface=found;
        }
    }
    int fd=-1, claimed=0, result=list ? 0 : 1;
    if (list) goto cleanup;
    if (!selected) { fprintf(stderr, "No selected device already in accessory mode; USB mode was not changed\n"); goto cleanup; }
    rc=libusb_open(selected, &usb.handle);
    if (rc) { fprintf(stderr, "USB open failed: %s\n", libusb_error_name(rc)); goto cleanup; }
    /* Never detach a kernel driver or change USB configuration/mode. */
    rc=libusb_claim_interface(usb.handle, interface);
    if (rc) { fprintf(stderr, "USB claim failed: %s\n", libusb_error_name(rc)); goto cleanup; }
    claimed=1;
    fd=connect_local(port);
    if (fd < 0) { fprintf(stderr, "Local receiver connection failed\n"); goto cleanup; }
    struct spen_relay_stats stats={0};
    struct spen_bulk bulk={.context=&usb, .transfer=transfer};
    result=spen_relay_run(fd, bulk, (unsigned int)seconds, &stats) ? 1 : 0;
    printf("{\"to_host_bytes\":%llu,\"to_usb_bytes\":%llu,\"error\":%d,\"usb_mode_changed\":false}\n",
           (unsigned long long)stats.to_host, (unsigned long long)stats.to_usb, stats.error);
cleanup:
    if (fd >= 0) close(fd);
    if (claimed) libusb_release_interface(usb.handle, interface);
    if (usb.handle) libusb_close(usb.handle);
    libusb_free_device_list(devices, 1);
    libusb_exit(context);
    return result;
usage:
    fprintf(stderr, "Usage: spen-usb-relay --list\n"
                    "  or: spen-usb-relay --bus N --address N --port N [--seconds 1..60]\n"
                    "Only devices ALREADY in AOA mode are supported. No mode switching.\n");
    return 2;
}
