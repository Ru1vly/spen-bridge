// Compile against Protocol.kt's output and kotlin-stdlib; no Android SDK needed.
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.util.Collections;
import java.util.HexFormat;
import java.util.List;
import com.spenbridge.app.Protocol;

public class ProtocolProbe {
    public static void main(String[] args) {
        Protocol.Event event = new Protocol.Event(
            (byte) 3, (byte) 0, (short) 5, .25f, .75f, .5f, -30f, 45f);
        byte[] normal = Protocol.INSTANCE.packEvents(List.of(event), (short) 42);
        System.out.println("normal=" + HexFormat.of().formatHex(normal));
        try {
            Protocol.INSTANCE.packEvents(Collections.nCopies(2731, event), (short) 1);
            throw new AssertionError("Oversized batch accepted");
        } catch (IllegalArgumentException expected) {
            System.out.println("oversized batch rejected");
        }
        List<byte[]> batches = Protocol.INSTANCE.packEventBatches(Collections.nCopies(2731, event), (short) 1);
        int records = 0;
        for (byte[] batch : batches) {
            int size = Short.toUnsignedInt(ByteBuffer.wrap(batch).order(ByteOrder.LITTLE_ENDIAN).getShort(7));
            if (size != batch.length - 9) throw new AssertionError("Payload length mismatch");
            records += size / 24;
        }
        if (records != 2731) throw new AssertionError("Lost records");
        System.out.println("all 2731 records preserved across " + batches.size() + " frames");
    }
}
