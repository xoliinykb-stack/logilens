// LogisimBridge — headless helper that drives the real Logisim engine.
// Compiled on first use (or by `logilens setup`) against the user's logisim.jar, which is GPL and not bundled.
//
// Usage:
//   java -cp logisim.jar:. LogisimBridge dump   <file.circ>
//   java -cp logisim.jar:. LogisimBridge table  <file.circ> [circuitName] [maxInputBits]
//   java -cp logisim.jar:. LogisimBridge render <file.circ> <out.png> [scale] [circuitName] [y0 y1]
//   java -cp logisim.jar:. LogisimBridge trace  <file.circ> <circuitName|-> <steps>
//        steps = ';'-separated; "t" = Propagator.tick() (all Clock components toggle, first tick = rising),
//        otherwise ','-separated bit strings (MSB first) for the input pins in table order.
//        ONE persistent CircuitState for the whole trace (sequential simulation).
//
// All structured output is JSON on stdout (Logisim's own stdout chatter is redirected to stderr).
// Errors: {"error": "..."} and exit code 2.

import com.cburch.logisim.circuit.Analyze;
import com.cburch.logisim.circuit.Circuit;
import com.cburch.logisim.circuit.CircuitState;
import com.cburch.logisim.circuit.Wire;
import com.cburch.logisim.comp.Component;
import com.cburch.logisim.comp.ComponentDrawContext;
import com.cburch.logisim.comp.EndData;
import com.cburch.logisim.data.Attribute;
import com.cburch.logisim.data.AttributeSet;
import com.cburch.logisim.data.BitWidth;
import com.cburch.logisim.data.Bounds;
import com.cburch.logisim.data.Location;
import com.cburch.logisim.data.Value;
import com.cburch.logisim.file.Loader;
import com.cburch.logisim.file.LogisimFile;
import com.cburch.logisim.instance.Instance;
import com.cburch.logisim.instance.StdAttr;
import com.cburch.logisim.proj.Project;
import com.cburch.logisim.std.wiring.Pin;

import java.awt.Canvas;
import java.awt.Color;
import java.awt.Graphics;
import java.awt.Graphics2D;
import java.awt.RenderingHints;
import java.awt.image.BufferedImage;
import java.io.File;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import javax.imageio.ImageIO;

public class LogisimBridge {

    // real stdout; System.out is redirected to stderr so that Logisim messages cannot corrupt the JSON
    static final java.io.PrintStream OUT = System.out;

    // ---------- tiny JSON writer (no dependencies) ----------
    static String q(String s) {
        if (s == null) return "null";
        StringBuilder b = new StringBuilder("\"");
        for (char c : s.toCharArray()) {
            switch (c) {
                case '"': b.append("\\\""); break;
                case '\\': b.append("\\\\"); break;
                case '\n': b.append("\\n"); break;
                case '\r': b.append("\\r"); break;
                case '\t': b.append("\\t"); break;
                default:
                    if (c < 0x20) b.append(String.format("\\u%04x", (int) c));
                    else b.append(c);
            }
        }
        return b.append('"').toString();
    }

    // Value.toString(): 0/1/x/E per bit, MSB first, space every 4 bits
    static String bits(Value v) { return v.toString().replace(" ", ""); }

    static LogisimFile load(String path) throws Exception {
        return new Loader(null).openLogisimFile(new File(path), new HashMap<File, File>());
    }

    static Circuit pick(LogisimFile f, String name) {
        if (name == null || name.isEmpty() || name.equals("-")) return f.getMainCircuit();
        for (Circuit c : f.getCircuits()) if (c.getName().equals(name)) return c;
        throw new IllegalArgumentException("no circuit named " + name);
    }

    @SuppressWarnings({"rawtypes", "unchecked"})
    static String attrsJson(AttributeSet as) {
        StringBuilder b = new StringBuilder("{");
        boolean first = true;
        for (Attribute a : as.getAttributes()) {
            Object v = as.getValue(a);
            if (v == null) continue;
            String s;
            try { s = a.toStandardString(v); } catch (Exception e) { s = String.valueOf(v); }
            if (!first) b.append(',');
            first = false;
            b.append(q(a.getName())).append(':').append(q(s));
        }
        return b.append('}').toString();
    }

    // ---------- dump: components, ends (exact port positions), wires ----------
    static void dump(String path) throws Exception {
        LogisimFile f = load(path);
        StringBuilder out = new StringBuilder("{\"main\":").append(q(f.getMainCircuit().getName())).append(",\"circuits\":[");
        boolean fc = true;
        for (Circuit c : f.getCircuits()) {
            if (!fc) out.append(',');
            fc = false;
            out.append("{\"name\":").append(q(c.getName())).append(",\"components\":[");
            boolean first = true;
            for (Component comp : c.getNonWires()) {
                if (!first) out.append(',');
                first = false;
                Location l = comp.getLocation();
                String lib = comp.getFactory().getClass().getPackage().getName();
                out.append("{\"name\":").append(q(comp.getFactory().getName()))
                   .append(",\"pkg\":").append(q(lib))
                   .append(",\"loc\":[").append(l.getX()).append(',').append(l.getY()).append(']')
                   .append(",\"attrs\":").append(attrsJson(comp.getAttributeSet()))
                   .append(",\"ends\":[");
                List<EndData> ends = comp.getEnds();
                for (int i = 0; i < ends.size(); i++) {
                    EndData e = ends.get(i);
                    if (i > 0) out.append(',');
                    String t = e.isInput() && e.isOutput() ? "inout" : e.isOutput() ? "output" : "input";
                    out.append("{\"i\":").append(i)
                       .append(",\"x\":").append(e.getLocation().getX())
                       .append(",\"y\":").append(e.getLocation().getY())
                       .append(",\"width\":").append(e.getWidth().getWidth())
                       .append(",\"type\":").append(q(t)).append('}');
                }
                out.append("]}");
            }
            out.append("],\"wires\":[");
            first = true;
            for (Wire w : c.getWires()) {
                if (!first) out.append(',');
                first = false;
                out.append('[').append(w.getEnd0().getX()).append(',').append(w.getEnd0().getY()).append(',')
                   .append(w.getEnd1().getX()).append(',').append(w.getEnd1().getY()).append(']');
            }
            out.append("]}");
        }
        out.append("]}");
        OUT.println(out);
    }

    // ---------- table: exhaustive simulation with a fresh state per row ----------
    static void table(String path, String circName, int maxBits) throws Exception {
        LogisimFile f = load(path);
        Project proj = new Project(f);
        Circuit c = pick(f, circName);
        Map<Instance, String> labels = Analyze.getPinLabels(c);
        List<Instance> ins = new ArrayList<>(), outs = new ArrayList<>();
        List<String> inL = new ArrayList<>(), outL = new ArrayList<>();
        for (Map.Entry<Instance, String> e : labels.entrySet()) {
            if (Pin.FACTORY.isInputPin(e.getKey())) { ins.add(e.getKey()); inL.add(e.getValue()); }
            else { outs.add(e.getKey()); outL.add(e.getValue()); }
        }
        int[] inW = new int[ins.size()];
        int total = 0;
        for (int i = 0; i < ins.size(); i++) {
            inW[i] = ins.get(i).getAttributeValue(StdAttr.WIDTH).getWidth();
            total += inW[i];
        }
        if (total > maxBits) {
            OUT.println("{\"error\":" + q("too many input bits: " + total + " > " + maxBits) + "}");
            System.exit(2);
        }
        StringBuilder out = new StringBuilder("{\"circuit\":").append(q(c.getName())).append(",\"inputs\":[");
        for (int i = 0; i < ins.size(); i++) {
            if (i > 0) out.append(',');
            out.append("{\"label\":").append(q(inL.get(i))).append(",\"width\":").append(inW[i]).append('}');
        }
        out.append("],\"outputs\":[");
        for (int i = 0; i < outs.size(); i++) {
            if (i > 0) out.append(',');
            out.append("{\"label\":").append(q(outL.get(i))).append(",\"width\":")
               .append(outs.get(i).getAttributeValue(StdAttr.WIDTH).getWidth()).append('}');
        }
        out.append("],\"rows\":[");
        long rows = 1L << total;
        for (long r = 0; r < rows; r++) {
            CircuitState st = new CircuitState(proj, c);
            int shift = total;
            StringBuilder inStr = new StringBuilder();
            for (int i = 0; i < ins.size(); i++) {
                shift -= inW[i];
                int v = (int) ((r >> shift) & ((1L << inW[i]) - 1));
                Value val = Value.createKnown(BitWidth.create(inW[i]), v);
                Pin.FACTORY.setValue(st.getInstanceState(ins.get(i)), val);
                if (i > 0) inStr.append(' ');
                inStr.append(bits(val));
            }
            st.getPropagator().propagate();
            boolean osc = st.getPropagator().isOscillating();
            if (r > 0) out.append(',');
            out.append("{\"in\":").append(q(inStr.toString())).append(",\"out\":[");
            for (int i = 0; i < outs.size(); i++) {
                if (i > 0) out.append(',');
                out.append(q(bits(Pin.FACTORY.getValue(st.getInstanceState(outs.get(i))))));
            }
            out.append("],\"osc\":").append(osc).append('}');
        }
        out.append("]}");
        OUT.println(out);
    }

    // ---------- trace: persistent state, input pokes and clock ticks ----------
    static void trace(String path, String circName, String steps) throws Exception {
        LogisimFile f = load(path);
        Project proj = new Project(f);
        Circuit c = pick(f, circName);
        Map<Instance, String> labels = Analyze.getPinLabels(c);
        List<Instance> ins = new ArrayList<>(), outs = new ArrayList<>();
        List<String> inL = new ArrayList<>(), outL = new ArrayList<>();
        for (Map.Entry<Instance, String> e : labels.entrySet()) {
            if (Pin.FACTORY.isInputPin(e.getKey())) { ins.add(e.getKey()); inL.add(e.getValue()); }
            else { outs.add(e.getKey()); outL.add(e.getValue()); }
        }
        CircuitState st = new CircuitState(proj, c);
        st.getPropagator().propagate();
        StringBuilder out = new StringBuilder("{\"circuit\":").append(q(c.getName())).append(",\"inputs\":[");
        for (int i = 0; i < ins.size(); i++) {
            if (i > 0) out.append(',');
            out.append("{\"label\":").append(q(inL.get(i))).append(",\"width\":")
               .append(ins.get(i).getAttributeValue(StdAttr.WIDTH).getWidth()).append('}');
        }
        out.append("],\"outputs\":[");
        for (int i = 0; i < outs.size(); i++) {
            if (i > 0) out.append(',');
            out.append("{\"label\":").append(q(outL.get(i))).append(",\"width\":")
               .append(outs.get(i).getAttributeValue(StdAttr.WIDTH).getWidth()).append('}');
        }
        out.append("],\"rows\":[");
        String[] parts = steps.isEmpty() ? new String[0] : steps.split(";");
        for (int r = 0; r < parts.length; r++) {
            String step = parts[r].trim();
            if (step.equals("t")) {
                st.getPropagator().tick();
            } else {
                String[] vals = step.split(",");
                if (vals.length != ins.size())
                    throw new IllegalArgumentException("step " + r + ": expected " + ins.size() + " input values");
                for (int i = 0; i < ins.size(); i++) {
                    int w = ins.get(i).getAttributeValue(StdAttr.WIDTH).getWidth();
                    Value val = Value.createKnown(BitWidth.create(w), (int) Long.parseLong(vals[i].trim(), 2));
                    Pin.FACTORY.setValue(st.getInstanceState(ins.get(i)), val);
                    st.getInstanceState(ins.get(i)).fireInvalidated(); // schedule the pin like the Poke tool does
                }
            }
            st.getPropagator().propagate();
            if (r > 0) out.append(',');
            out.append("{\"op\":").append(q(step)).append(",\"out\":[");
            for (int i = 0; i < outs.size(); i++) {
                if (i > 0) out.append(',');
                out.append(q(bits(Pin.FACTORY.getValue(st.getInstanceState(outs.get(i))))));
            }
            out.append("],\"osc\":").append(st.getPropagator().isOscillating()).append('}');
        }
        out.append("]}");
        OUT.println(out);
    }

    // ---------- render: printer-view PNG, optional vertical crop ----------
    static void render(String path, String png, double scale, String circName, Integer y0, Integer y1) throws Exception {
        LogisimFile f = load(path);
        Project proj = new Project(f);
        Circuit c = pick(f, circName);
        BufferedImage tmp = new BufferedImage(10, 10, BufferedImage.TYPE_INT_RGB);
        Bounds bds = c.getBounds(tmp.getGraphics()).expand(10);
        int top = y0 != null ? y0 : bds.getY();
        int height = (y0 != null && y1 != null) ? (y1 - y0) : bds.getHeight();
        int w = (int) Math.round(bds.getWidth() * scale), h = (int) Math.round(height * scale);
        BufferedImage img = new BufferedImage(w, h, BufferedImage.TYPE_INT_RGB);
        Graphics base = img.getGraphics();
        Graphics2D g = (Graphics2D) base.create();
        g.setRenderingHint(RenderingHints.KEY_ANTIALIASING, RenderingHints.VALUE_ANTIALIAS_ON);
        g.setRenderingHint(RenderingHints.KEY_TEXT_ANTIALIASING, RenderingHints.VALUE_TEXT_ANTIALIAS_ON);
        g.setColor(Color.white);
        g.fillRect(0, 0, w, h);
        g.setColor(Color.black);
        g.scale(scale, scale);
        g.translate(-bds.getX(), -top);
        CircuitState st = new CircuitState(proj, c);
        st.getPropagator().propagate();
        c.draw(new ComponentDrawContext(new Canvas(), c, st, base, g, true), null);
        ImageIO.write(img, "PNG", new File(png));
        OUT.println("{\"png\":" + q(png) + ",\"width\":" + w + ",\"height\":" + h + "}");
    }

    public static void main(String[] a) {
        try {
            System.setOut(System.err);
            if (a.length < 2) throw new IllegalArgumentException("usage: dump|table|render|trace <file.circ> ...");
            switch (a[0]) {
                case "dump": dump(a[1]); break;
                case "table": table(a[1], a.length > 2 ? a[2] : null, a.length > 3 ? Integer.parseInt(a[3]) : 20); break;
                case "render":
                    render(a[1], a[2], a.length > 3 ? Double.parseDouble(a[3]) : 2.0, a.length > 4 ? a[4] : null,
                           a.length > 6 ? Integer.valueOf(a[5]) : null, a.length > 6 ? Integer.valueOf(a[6]) : null);
                    break;
                case "trace": trace(a[1], a.length > 2 ? a[2] : null, a.length > 3 ? a[3] : ""); break;
                default: throw new IllegalArgumentException("unknown command " + a[0]);
            }
            System.exit(0);
        } catch (Throwable t) {
            OUT.println("{\"error\":" + q(t.getClass().getSimpleName() + ": " + t.getMessage()) + "}");
            System.exit(2);
        }
    }
}
