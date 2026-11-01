import java.io.*;
import java.net.*;
import java.nio.*;
import java.nio.file.*;
import java.security.*;
import java.security.cert.*;
import java.util.*;
import java.util.concurrent.atomic.*;
import java.util.concurrent.locks.LockSupport;
import javax.crypto.*;
import javax.crypto.spec.*;
import javax.net.ssl.*;

/** Isolated app-UID synthetic probe. Never reads app pairing or injects OS input. */
public final class USBLatencyProbe {
    static final byte[] VERSION = new byte[]{'S','P','B','2'};
    static byte[] frame(int kind, int seq, byte[] payload) {
        ByteBuffer b=ByteBuffer.allocate(9+payload.length).order(ByteOrder.LITTLE_ENDIAN);
        b.put(new byte[]{'S','P','E','N'}).put((byte)kind).putShort((short)seq).putShort((short)payload.length).put(payload);
        return b.array();
    }
    static byte[] read(DataInputStream in, int expectedKind, int expectedSeq) throws Exception {
        byte[] h=new byte[9];in.readFully(h);
        ByteBuffer b=ByteBuffer.wrap(h).order(ByteOrder.LITTLE_ENDIAN);
        if(b.getInt()!=0x4e455053 || (b.get()&255)!=expectedKind || (b.getShort()&65535)!=expectedSeq) throw new IOException("Unexpected response");
        int size=b.getShort()&65535;
        if(size>36) throw new IOException("Oversized response");
        byte[] p=new byte[size];in.readFully(p);return p;
    }
    static byte[] proof(String code, byte[] nonce, String role) throws Exception {
        Mac m=Mac.getInstance("HmacSHA256");m.init(new SecretKeySpec(code.getBytes("US-ASCII"),"HmacSHA256"));
        m.update(VERSION);m.update(role.getBytes("US-ASCII"));m.update((byte)0);m.update(nonce);
        ByteArrayOutputStream out=new ByteArrayOutputStream();out.write(VERSION);out.write(m.doFinal());return out.toByteArray();
    }
    static String hex(byte[] b) {
        StringBuilder s=new StringBuilder();for(byte v:b)s.append(String.format(Locale.ROOT,"%02x",v&255));return s.toString();
    }
    static String stats(long[] ns) {
        long[] v=ns.clone();Arrays.sort(v);
        return String.format(Locale.ROOT,"{\"p50_us\":%.3f,\"p95_us\":%.3f,\"p99_us\":%.3f,\"max_us\":%.3f}",v[(int)Math.ceil(v.length*.5)-1]/1000.0,v[(int)Math.ceil(v.length*.95)-1]/1000.0,v[(int)Math.ceil(v.length*.99)-1]/1000.0,v[v.length-1]/1000.0);
    }
    public static void main(String[] args) throws Exception {
        Properties p=new Properties();try(InputStream f=new FileInputStream(args[0])){p.load(f);}
        final String pin=p.getProperty("fingerprint");
        int port=Integer.parseInt(p.getProperty("port"));
        int count=Integer.parseInt(p.getProperty("count","5000")),warm=500,total=count+warm;
        if(count<2 || count>10000)throw new IllegalArgumentException("Diagnostic count must be 2..10000");
        X509TrustManager tm=new X509TrustManager(){
            public X509Certificate[] getAcceptedIssuers(){return new X509Certificate[0];}
            public void checkClientTrusted(X509Certificate[] c,String a)throws CertificateException{throw new CertificateException("No client certificates");}
            public void checkServerTrusted(X509Certificate[] c,String a)throws CertificateException{
                try{if(c.length==0)throw new CertificateException("Missing certificate");c[0].checkValidity();if(!pin.equals(hex(MessageDigest.getInstance("SHA-256").digest(c[0].getEncoded()))))throw new CertificateException("Pin mismatch");}
                catch(GeneralSecurityException e){throw new CertificateException(e);}
            }
        };
        SSLContext ctx=SSLContext.getInstance("TLS");ctx.init(null,new TrustManager[]{tm},null);
        try(Socket raw=new Socket()) {
            raw.setTcpNoDelay(true);raw.connect(new InetSocketAddress("127.0.0.1",port),5000);
            try(SSLSocket socket=(SSLSocket)ctx.getSocketFactory().createSocket(raw,"127.0.0.1",port,true)) {
                socket.setEnabledProtocols(new String[]{"TLSv1.2","TLSv1.3"});socket.setSoTimeout(10000);socket.startHandshake();
                DataInputStream in=new DataInputStream(socket.getInputStream());OutputStream out=socket.getOutputStream();
                byte[] challenge=read(in,4,0);
                if(challenge.length!=36 || !Arrays.equals(Arrays.copyOf(challenge,4),VERSION))throw new IOException("Invalid challenge");
                byte[] nonce=Arrays.copyOfRange(challenge,4,36);String code=p.getProperty("code");
                out.write(frame(4,0,proof(code,nonce,"client")));out.flush();
                if(!MessageDigest.isEqual(read(in,4,0),proof(code,nonce,"server")))throw new IOException("Invalid server proof");
                AtomicLongArray sent=new AtomicLongArray(total);long[] rtt=new long[count],intervals=new long[count-1],writes=new long[count];
                AtomicReference<Throwable> failure=new AtomicReference<>();
                Thread receiver=new Thread(()->{
                    try{for(int i=0;i<total;i++){
                        if(read(in,3,i).length!=0)throw new IOException("Invalid PONG");
                        if(i>=warm)rtt[i-warm]=System.nanoTime()-sent.get(i);
                    }}catch(Throwable e){failure.set(e);try{socket.close();}catch(IOException ignored){}}
                },"SPenAuditReceiver");receiver.start();
                long next=System.nanoTime(),last=0,first=0,end=0,lateSlots=0;
                for(int i=0;i<total;i++) {
                    while(true){long remaining=next-System.nanoTime();if(remaining<=0)break;LockSupport.parkNanos(remaining);}
                    long now=System.nanoTime();if(now-next>=1000000){lateSlots+=(now-next)/1000000;next=now;}
                    if(i>=warm){if(i==warm)first=now;else intervals[i-warm-1]=now-last;last=now;end=now;}
                    ByteBuffer ev=ByteBuffer.allocate(24).order(ByteOrder.LITTLE_ENDIAN);
                    ev.put((byte)4).put((byte)0).putShort((short)4).putFloat(i/20000f).putFloat(.5f).putFloat(.7f).putFloat(0).putFloat(0);
                    byte[] event=frame(1,i,ev.array()),ping=frame(2,i,new byte[0]),both=new byte[42];
                    System.arraycopy(event,0,both,0,33);System.arraycopy(ping,0,both,33,9);
                    sent.set(i,System.nanoTime());long start=sent.get(i);out.write(both);out.flush();
                    if(i>=warm)writes[i-warm]=System.nanoTime()-start;
                    if(failure.get()!=null)throw new IOException("Receiver failed",failure.get());
                    next+=1000000;
                }
                receiver.join(15000);if(receiver.isAlive())throw new IOException("Receiver did not complete");if(failure.get()!=null)throw new IOException("Receiver failed",failure.get());
                System.out.println("{\"scope\":\"Android app-UID synthetic TLS/event+PING over real ADB reverse, no sensor or OS injection\",\"warmup\":"+warm+",\"samples\":"+count+",\"target_hz\":1000,\"actual_send_hz\":"+String.format(Locale.ROOT,"%.3f",(count-1)*1e9/(end-first))+",\"missed_pacing_slots\":"+lateSlots+",\"round_trip\":"+stats(rtt)+",\"write_duration\":"+stats(writes)+",\"send_interval\":"+stats(intervals)+"}");
            }
        }
    }
}
