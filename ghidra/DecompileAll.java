// Decompile every function in the current program and write C to the file given as script arg.
// @category MkTypist
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.program.model.listing.Function;
import java.io.PrintWriter;

public class DecompileAll extends GhidraScript {
    @Override
    protected void run() throws Exception {
        String out = getScriptArgs()[0];
        DecompInterface di = new DecompInterface();
        di.openProgram(currentProgram);
        try (PrintWriter pw = new PrintWriter(out)) {
            for (Function f : currentProgram.getFunctionManager().getFunctions(true)) {
                DecompileResults r = di.decompileFunction(f, 60, monitor);
                pw.println("// ==== " + f.getName() + " @ " + f.getEntryPoint());
                if (r.decompileCompleted()) {
                    pw.println(r.getDecompiledFunction().getC());
                } else {
                    pw.println("// decompile failed: " + r.getErrorMessage());
                }
            }
        }
    }
}
