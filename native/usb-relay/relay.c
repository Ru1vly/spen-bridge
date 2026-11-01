#define _POSIX_C_SOURCE 200809L
#include "relay.h"
#include <errno.h>
#include <poll.h>
#include <pthread.h>
#include <stdatomic.h>
#include <string.h>
#include <sys/socket.h>
#include <time.h>

#define CHUNK 16384
#define IO_TIMEOUT_MS 25
#define STALL_NS 2000000000LL
#define PEER_IDLE_NS 3000000000LL
struct session {
    int fd;
    struct spen_bulk bulk;
    atomic_bool stopped;
    atomic_int error;
    atomic_int_fast64_t last_from_usb;
    int64_t deadline;
    uint64_t to_host, to_usb;
};
static int64_t now_ns(void) {
    struct timespec t;
    clock_gettime(CLOCK_MONOTONIC, &t);
    return (int64_t)t.tv_sec * 1000000000LL + t.tv_nsec;
}
static void stop(struct session *s, int error) {
    if (error) {
        int expected = 0;
        atomic_compare_exchange_strong(&s->error, &expected, error);
    }
    atomic_store(&s->stopped, 1);
    shutdown(s->fd, SHUT_RDWR);
}
static int active(struct session *s) {
    int64_t now = now_ns();
    if (now >= s->deadline) stop(s, 0);
    else if (now - atomic_load(&s->last_from_usb) >= PEER_IDLE_NS)
        stop(s, SPEN_RELAY_PEER_IDLE);
    return !atomic_load(&s->stopped);
}
static int socket_ready(struct session *s, short events) {
    struct pollfd p = {.fd=s->fd, .events=events};
    int rc = poll(&p, 1, IO_TIMEOUT_MS);
    if (rc < 0 && errno != EINTR) { stop(s, -1); return 0; }
    if (rc <= 0) return 0;
    if (p.revents & POLLNVAL) { stop(s, -1); return 0; }
    /* Drain readable bytes before handling EOF/HUP. */
    return p.revents & (events | POLLHUP | POLLERR);
}
static int send_socket(struct session *s, unsigned char *data, int length) {
    int offset = 0;
    int64_t progress = now_ns();
    while (offset < length && active(s)) {
        if (now_ns() - progress > STALL_NS) { stop(s, -2); break; }
        if (!socket_ready(s, POLLOUT)) continue;
        ssize_t n = send(s->fd, data + offset, (size_t)(length-offset), MSG_NOSIGNAL | MSG_DONTWAIT);
        if (n < 0 && (errno == EINTR || errno == EAGAIN || errno == EWOULDBLOCK)) continue;
        if (n <= 0) { stop(s, -3); break; }
        offset += (int)n;
        s->to_host += (uint64_t)n;
        progress = now_ns();
    }
    return offset == length;
}
static void *from_usb(void *arg) {
    struct session *s = arg;
    unsigned char data[CHUNK];
    while (active(s)) {
        int n = 0;
        int status = s->bulk.transfer(s->bulk.context, 1, data, CHUNK, &n, IO_TIMEOUT_MS);
        if (n < 0 || n > CHUNK || (status != 0 && status != -7)) { stop(s, -4); break; }
        if (n) {
            atomic_store(&s->last_from_usb, now_ns());
            if (!send_socket(s, data, n)) break;
        }
        /* Zero-length USB packets are not a byte-stream EOF. */
    }
    return NULL;
}
static void *to_usb(void *arg) {
    struct session *s = arg;
    unsigned char data[CHUNK];
    while (active(s)) {
        if (!socket_ready(s, POLLIN)) continue;
        ssize_t length = recv(s->fd, data, CHUNK, MSG_DONTWAIT);
        if (length < 0 && (errno == EINTR || errno == EAGAIN || errno == EWOULDBLOCK)) continue;
        if (length <= 0) { stop(s, length < 0 ? -5 : 0); break; }
        int offset = 0;
        int64_t progress = now_ns();
        while (offset < length && active(s)) {
            int n = 0;
            int status = s->bulk.transfer(s->bulk.context, 0, data + offset,
                                         (int)length-offset, &n, IO_TIMEOUT_MS);
            if (n < 0 || n > length-offset || (status != 0 && status != -7)) { stop(s, -6); break; }
            offset += n;
            s->to_usb += (uint64_t)n;
            if (n) progress = now_ns();
            if (now_ns()-progress > STALL_NS) { stop(s, -7); break; }
        }
    }
    return NULL;
}
int spen_relay_run(int socket_fd, struct spen_bulk bulk, unsigned int seconds,
                   struct spen_relay_stats *stats) {
    if (!stats) return -1;
    *stats = (struct spen_relay_stats){0};
    if (!bulk.transfer || socket_fd < 0 || seconds < 1 || seconds > 60) { stats->error=-8; return -1; }
    struct session s = {.fd=socket_fd, .bulk=bulk,
        .deadline=now_ns()+(int64_t)seconds*1000000000LL};
    atomic_init(&s.stopped, 0);
    atomic_init(&s.error, 0);
    atomic_init(&s.last_from_usb, now_ns());
    pthread_t reader, writer;
    if (pthread_create(&reader, NULL, from_usb, &s)) { stats->error=-8; return -1; }
    if (pthread_create(&writer, NULL, to_usb, &s)) {
        stop(&s, -8);
        pthread_join(reader, NULL);
        stats->error=-8;
        return -1;
    }
    pthread_join(writer, NULL);
    stop(&s, 0);
    pthread_join(reader, NULL);
    *stats = (struct spen_relay_stats){s.to_host, s.to_usb, atomic_load(&s.error)};
    return stats->error ? -1 : 0;
}
