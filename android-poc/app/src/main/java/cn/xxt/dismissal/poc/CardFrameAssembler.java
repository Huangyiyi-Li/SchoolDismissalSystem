package cn.xxt.dismissal.poc;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

/** Turns a byte stream into fixed four-byte card IDs without assuming read boundaries. */
final class CardFrameAssembler {
    static final long PARTIAL_TIMEOUT_MS = 700;
    private final byte[] pending = new byte[4];
    private int size;
    private long lastByteAt;

    List<byte[]> accept(byte[] chunk, long nowMs) {
        List<byte[]> frames = new ArrayList<>();
        expire(nowMs);
        for (byte value : chunk) {
            pending[size++] = value;
            lastByteAt = nowMs;
            if (size == 4) {
                frames.add(Arrays.copyOf(pending, 4));
                size = 0;
            }
        }
        return frames;
    }

    int pendingSize() { return size; }

    int expire(long nowMs) {
        if (size == 0 || nowMs - lastByteAt <= PARTIAL_TIMEOUT_MS) return 0;
        int dropped = size;
        size = 0;
        return dropped;
    }
}
