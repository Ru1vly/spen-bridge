CC ?= cc
PKG_CONFIG ?= pkg-config
CFLAGS ?= -O2 -g
CFLAGS += -std=c11 -Wall -Wextra -Werror -pthread
LDLIBS += $(shell $(PKG_CONFIG) --libs libusb-1.0) -pthread
CPPFLAGS += $(shell $(PKG_CONFIG) --cflags libusb-1.0)

spen-usb-relay: main.c relay.c relay.h
	$(CC) $(CPPFLAGS) $(CFLAGS) main.c relay.c -o $@ $(LDFLAGS) $(LDLIBS)

clean:
	rm -f spen-usb-relay
.PHONY: clean
