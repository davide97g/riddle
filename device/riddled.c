// riddled - reMarkable 2 side agent for the Tom Riddle diary.
//
// The tablet ships no python at all on firmware 3.28 (and on 3.15 before it,
// a build stripped of ctypes, socket, fcntl and mmap), and rm2fb cannot be
// used because xochitl is Qt6 while the prebuilt shim is Qt5. So this
// agent talks to the digitizer directly and is driven over an ssh pipe by the
// host: pen samples go out on stdout, drawing commands come in on stdin.
//
// Injection works because a write() to an evdev node is fed back through the
// input core with input_inject_event(), so xochitl sees our synthetic strokes
// as if they came from the pen itself. That is what lets the diary erase what
// you wrote and answer in ink without touching the framebuffer.

#include <errno.h>
#include <fcntl.h>
#include <linux/input.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/select.h>
#include <time.h>
#include <unistd.h>

#define PEN_DEVICE "/dev/input/event1"
#define TOUCH_DEVICE "/dev/input/event2"

static int pen_fd = -1;
static int touch_fd = -1;

// Injected events come straight back at us: the input core broadcasts them to
// every reader of the node, ourselves included. We keep the exact sequence we
// wrote and cancel it against what comes back, so that ink written by hand
// while the diary is drawing is still reported rather than swallowed whole.
#define ECHO_MAX 16384
#define ECHO_SCAN 24
#define ECHO_TTL_MS 2000

static struct {
    uint16_t type;
    uint16_t code;
    int32_t value;
} echo[ECHO_MAX];

static int echo_head = 0;
static int echo_tail = 0;
static long echo_stamp = 0;

static long now_ms(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return ts.tv_sec * 1000L + ts.tv_nsec / 1000000L;
}

static void sleep_ms(long ms) {
    struct timespec ts = {ms / 1000, (ms % 1000) * 1000000L};
    nanosleep(&ts, NULL);
}

static void echo_push(uint16_t type, uint16_t code, int32_t value) {
    int next = (echo_tail + 1) % ECHO_MAX;
    if (next == echo_head) echo_head = (echo_head + 1) % ECHO_MAX;
    echo[echo_tail].type = type;
    echo[echo_tail].code = code;
    echo[echo_tail].value = value;
    echo_tail = next;
    echo_stamp = now_ms();
}

// The input core silently drops an absolute value that did not change, so an
// event we wrote may never come back. Scanning a short way ahead keeps the two
// streams aligned when that happens.
static int echo_take(const struct input_event *ev) {
    if (echo_head == echo_tail) return 0;
    if (now_ms() - echo_stamp > ECHO_TTL_MS) {
        echo_head = echo_tail;
        return 0;
    }
    int i = echo_head;
    for (int scanned = 0; i != echo_tail && scanned < ECHO_SCAN; scanned++) {
        if (echo[i].type == ev->type && echo[i].code == ev->code &&
            echo[i].value == ev->value) {
            echo_head = (i + 1) % ECHO_MAX;
            return 1;
        }
        i = (i + 1) % ECHO_MAX;
    }
    return 0;
}

static void emit_to(int fd, uint16_t type, uint16_t code, int32_t value) {
    struct input_event ev;
    memset(&ev, 0, sizeof(ev));
    ev.type = type;
    ev.code = code;
    ev.value = value;
    if (write(fd, &ev, sizeof(ev)) != (ssize_t)sizeof(ev))
        fprintf(stderr, "riddled: inject failed: %s\n", strerror(errno));
}

static void emit(uint16_t type, uint16_t code, int32_t value) {
    echo_push(type, code, value);
    emit_to(pen_fd, type, code, value);
}

static void syn(void) { emit(EV_SYN, SYN_REPORT, 0); }

// The pen reports itself as either a nib or an eraser; xochitl picks the tool
// from whichever BTN_TOOL_* is currently asserted.
static int current_tool = BTN_TOOL_PEN;

static void set_tool(int tool) {
    if (tool == current_tool) return;
    emit(EV_KEY, current_tool, 0);
    syn();
    current_tool = tool;
}

// A stroke has to start with the tool hovering before it touches down, the way
// a real pen approaches the glass, or xochitl drops the first samples.
static void stroke_begin(int x, int y, int pressure) {
    emit(EV_KEY, current_tool, 1);
    emit(EV_ABS, ABS_X, x);
    emit(EV_ABS, ABS_Y, y);
    emit(EV_ABS, ABS_DISTANCE, 40);
    emit(EV_ABS, ABS_TILT_X, 0);
    emit(EV_ABS, ABS_TILT_Y, 0);
    emit(EV_ABS, ABS_PRESSURE, 0);
    syn();
    sleep_ms(8);
    emit(EV_ABS, ABS_DISTANCE, 0);
    emit(EV_ABS, ABS_PRESSURE, pressure);
    emit(EV_KEY, BTN_TOUCH, 1);
    syn();
}

static void stroke_move(int x, int y, int pressure) {
    emit(EV_ABS, ABS_X, x);
    emit(EV_ABS, ABS_Y, y);
    emit(EV_ABS, ABS_PRESSURE, pressure);
    syn();
}

static void stroke_end(void) {
    emit(EV_ABS, ABS_PRESSURE, 0);
    emit(EV_KEY, BTN_TOUCH, 0);
    syn();
    emit(EV_ABS, ABS_DISTANCE, 60);
    emit(EV_KEY, current_tool, 0);
    syn();
}

// Taps are recorded and replayed in the touchscreen's own coordinates, so
// nothing here needs to know where the toolbar is or how touch maps to the
// panel: whatever the finger did, we can do again.
static int tracking_id = 700;

static void tap(int x, int y, int hold_ms) {
    if (touch_fd < 0) {
        fprintf(stderr, "riddled: no touch device\n");
        return;
    }
    emit_to(touch_fd, EV_ABS, ABS_MT_SLOT, 0);
    emit_to(touch_fd, EV_ABS, ABS_MT_TRACKING_ID, tracking_id++);
    emit_to(touch_fd, EV_ABS, ABS_MT_POSITION_X, x);
    emit_to(touch_fd, EV_ABS, ABS_MT_POSITION_Y, y);
    emit_to(touch_fd, EV_ABS, ABS_MT_PRESSURE, 90);
    emit_to(touch_fd, EV_ABS, ABS_MT_TOUCH_MAJOR, 18);
    emit_to(touch_fd, EV_ABS, ABS_MT_TOUCH_MINOR, 18);
    emit_to(touch_fd, EV_ABS, ABS_MT_ORIENTATION, 0);
    emit_to(touch_fd, EV_KEY, BTN_TOUCH, 1);
    emit_to(touch_fd, EV_SYN, SYN_REPORT, 0);

    sleep_ms(hold_ms);

    emit_to(touch_fd, EV_ABS, ABS_MT_SLOT, 0);
    emit_to(touch_fd, EV_ABS, ABS_MT_TRACKING_ID, -1);
    emit_to(touch_fd, EV_KEY, BTN_TOUCH, 0);
    emit_to(touch_fd, EV_SYN, SYN_REPORT, 0);
}

static void report_axis(const char *name, int axis) {
    struct input_absinfo info;
    if (ioctl(pen_fd, EVIOCGABS(axis), &info) == 0)
        printf("AXIS %s %d %d\n", name, info.minimum, info.maximum);
}

// Everything the host sends is one command per line; keeping it textual makes
// the whole pipeline greppable when a stroke comes out in the wrong place.
static void handle_command(char *line) {
    int x, y, p, ms;
    if (strncmp(line, "DOWN ", 5) == 0 && sscanf(line + 5, "%d %d %d", &x, &y, &p) == 3)
        stroke_begin(x, y, p);
    else if (strncmp(line, "MOVE ", 5) == 0 && sscanf(line + 5, "%d %d %d", &x, &y, &p) == 3)
        stroke_move(x, y, p);
    else if (strncmp(line, "UP", 2) == 0)
        stroke_end();
    else if (strncmp(line, "TOOL PEN", 8) == 0)
        set_tool(BTN_TOOL_PEN);
    else if (strncmp(line, "TOOL RUBBER", 11) == 0)
        set_tool(BTN_TOOL_RUBBER);
    else if (strncmp(line, "SLEEP ", 6) == 0 && sscanf(line + 6, "%d", &ms) == 1)
        sleep_ms(ms);
    else if (strncmp(line, "TAP ", 4) == 0 && sscanf(line + 4, "%d %d %d", &x, &y, &ms) >= 2) {
        if (sscanf(line + 4, "%d %d %d", &x, &y, &ms) < 3) ms = 90;
        tap(x, y, ms);
    }
    else if (strncmp(line, "PING", 4) == 0)
        printf("PONG\n");
    else if (strncmp(line, "QUIT", 4) == 0)
        exit(0);
    else
        fprintf(stderr, "riddled: unknown command: %s\n", line);
    fflush(stdout);
}

int main(void) {
    setvbuf(stdout, NULL, _IOLBF, 0);

    pen_fd = open(PEN_DEVICE, O_RDWR);
    if (pen_fd < 0) {
        fprintf(stderr, "riddled: cannot open %s: %s\n", PEN_DEVICE, strerror(errno));
        return 1;
    }

    touch_fd = open(TOUCH_DEVICE, O_RDWR);
    if (touch_fd < 0)
        fprintf(stderr, "riddled: cannot open %s: %s\n", TOUCH_DEVICE, strerror(errno));

    report_axis("X", ABS_X);
    report_axis("Y", ABS_Y);
    report_axis("PRESSURE", ABS_PRESSURE);
    printf("READY\n");

    char cmdbuf[512];
    size_t cmdlen = 0;
    int x = 0, y = 0, pressure = 0, touching = 0, dirty = 0;
    int tx = -1, ty = -1, finger = 0;

    for (;;) {
        fd_set fds;
        FD_ZERO(&fds);
        FD_SET(pen_fd, &fds);
        FD_SET(STDIN_FILENO, &fds);
        int maxfd = pen_fd > STDIN_FILENO ? pen_fd : STDIN_FILENO;
        if (touch_fd >= 0) {
            FD_SET(touch_fd, &fds);
            if (touch_fd > maxfd) maxfd = touch_fd;
        }

        if (select(maxfd + 1, &fds, NULL, NULL, NULL) < 0) {
            if (errno == EINTR) continue;
            return 1;
        }

        if (FD_ISSET(pen_fd, &fds)) {
            struct input_event ev;
            ssize_t n = read(pen_fd, &ev, sizeof(ev));
            if (n == (ssize_t)sizeof(ev) && !echo_take(&ev)) {
                if (ev.type == EV_ABS && ev.code == ABS_X) { x = ev.value; dirty = 1; }
                else if (ev.type == EV_ABS && ev.code == ABS_Y) { y = ev.value; dirty = 1; }
                else if (ev.type == EV_ABS && ev.code == ABS_PRESSURE) { pressure = ev.value; dirty = 1; }
                else if (ev.type == EV_KEY && ev.code == BTN_TOUCH) {
                    touching = ev.value;
                    if (!touching) printf("U %ld\n", now_ms());
                    dirty = 0;
                } else if (ev.type == EV_SYN && ev.code == SYN_REPORT) {
                    if (touching && dirty)
                        printf("P %ld %d %d %d\n", now_ms(), x, y, pressure);
                    dirty = 0;
                }
            }
        }

        if (touch_fd >= 0 && FD_ISSET(touch_fd, &fds)) {
            struct input_event ev;
            ssize_t n = read(touch_fd, &ev, sizeof(ev));
            if (n == (ssize_t)sizeof(ev)) {
                if (ev.type == EV_ABS && ev.code == ABS_MT_POSITION_X) tx = ev.value;
                else if (ev.type == EV_ABS && ev.code == ABS_MT_POSITION_Y) ty = ev.value;
                else if (ev.type == EV_ABS && ev.code == ABS_MT_TRACKING_ID)
                    finger = ev.value >= 0;
                else if (ev.type == EV_SYN && ev.code == SYN_REPORT && finger &&
                         tx >= 0 && ty >= 0)
                    printf("T %d %d\n", tx, ty);
            }
        }

        if (FD_ISSET(STDIN_FILENO, &fds)) {
            char c;
            ssize_t n = read(STDIN_FILENO, &c, 1);
            if (n <= 0) return 0;
            if (c == '\n') {
                cmdbuf[cmdlen] = '\0';
                if (cmdlen) handle_command(cmdbuf);
                cmdlen = 0;
            } else if (cmdlen < sizeof(cmdbuf) - 1) {
                cmdbuf[cmdlen++] = c;
            }
        }
    }
}
