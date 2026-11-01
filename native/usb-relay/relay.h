#ifndef SPEN_USB_RELAY_H
#define SPEN_USB_RELAY_H
#include <stddef.h>
#include <stdint.h>

/* One reader and one writer may run concurrently. bulk must return within
 * timeout_ms, report partial progress even on timeout, and never retain data.
 * status 0=success, -7=timeout; other statuses terminate the session. */
struct spen_bulk {
    void *context;
    int (*transfer)(void *, int input, unsigned char *, int, int *, unsigned int);
};
/* No inbound phone bytes for three seconds: disconnect the receiver.
 * Production pen heartbeat is one second, including while no pen is moving. */
#define SPEN_RELAY_PEER_IDLE (-9)
struct spen_relay_stats { uint64_t to_host, to_usb; int error; };
/* Owns neither socket nor transport. Caller releases them after return only.
 * Fixed buffers, no batching timer, no TLS termination or protocol parsing. */
int spen_relay_run(int socket_fd, struct spen_bulk bulk, unsigned int seconds,
                   struct spen_relay_stats *stats);
#endif
