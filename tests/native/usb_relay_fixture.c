#define _POSIX_C_SOURCE 200809L
/* Socket-backed bulk fixture. Not linked into the production executable. */
#include "relay.h"
#include <errno.h>
#include <poll.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/socket.h>
#include <time.h>
#include <unistd.h>
struct fake { int fd, mode, zero_packets; };
static int transfer(void *arg, int input, unsigned char *data, int size,
                    int *transferred, unsigned int timeout_ms) {
    struct fake *f=arg;
    if (f->mode == 4 && input && f->zero_packets++ < 3) { *transferred=0; return 0; }
    if (f->mode == 2 && input) { *transferred=size+1; return 0; }
    if (f->mode == 3 && !input) {
        struct timespec t={.tv_sec=0, .tv_nsec=(long)timeout_ms*1000000};
        nanosleep(&t, NULL);
        *transferred=0; return -7;
    }
    struct pollfd p={.fd=f->fd, .events=input ? POLLIN : POLLOUT};
    int ready=poll(&p, 1, (int)timeout_ms);
    *transferred=0;
    if (!ready || (ready < 0 && errno == EINTR)) return -7;
    if (ready < 0) return -1;
    if (f->mode == 1 && size > 7) size=7;
    ssize_t n=input ? recv(f->fd, data, (size_t)size, MSG_DONTWAIT) :
                      send(f->fd, data, (size_t)size, MSG_DONTWAIT | MSG_NOSIGNAL);
    if (n < 0 && (errno == EAGAIN || errno == EWOULDBLOCK || errno == EINTR)) return -7;
    if (n <= 0) return -4;
    *transferred=(int)n;
    /* Every successful operation in mode 1 also reports timeout. The relay
     * must retain those bytes and resume at the exact offset, never replay. */
    return f->mode == 1 ? -7 : 0;
}
int main(int argc, char **argv) {
    if (argc != 5) return 2;
    struct fake f={.fd=atoi(argv[2]), .mode=atoi(argv[3])};
    struct spen_bulk bulk={&f, transfer};
    struct spen_relay_stats stats={0};
    int result=spen_relay_run(atoi(argv[1]), bulk, (unsigned int)atoi(argv[4]), &stats);
    printf("{\"to_host\":%llu,\"to_usb\":%llu,\"error\":%d}\n",
           (unsigned long long)stats.to_host, (unsigned long long)stats.to_usb, stats.error);
    close(f.fd); close(atoi(argv[1]));
    return result ? 1 : 0;
}
