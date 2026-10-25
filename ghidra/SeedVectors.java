// Create functions at every Thumb vector-table entry of a Cortex-M image loaded at its base.
// @category MkTypist
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;

public class SeedVectors extends GhidraScript {
    @Override
    protected void run() throws Exception {
        Address base = currentProgram.getMinAddress();
        // Flash is read-only, so literal-pool constants can be propagated into the decompile.
        for (ghidra.program.model.mem.MemoryBlock b : currentProgram.getMemory().getBlocks()) {
            b.setWrite(false);
            b.setExecute(true);
        }
        for (int i = 1; i < 64; i++) {
            long v = getInt(base.add(i * 4)) & 0xffffffffL;
            if (v == 0xffffffffL || (v & 1) == 0) continue;
            Address a = toAddr(v & ~1L);
            if (!currentProgram.getMemory().contains(a)) continue;
            if (getInstructionAt(a) == null) {
                try {
                    currentProgram.getProgramContext().setValue(
                        currentProgram.getProgramContext().getRegister("TMode"), a, a, java.math.BigInteger.ONE);
                } catch (Exception e) {
                    println("TMode not set at " + a + ": " + e.getMessage());
                }
                disassemble(a);
            }
            if (getFunctionAt(a) == null) createFunction(a, i == 1 ? "Reset_Handler" : String.format("vec_%02d", i));
        }
        analyzeAll(currentProgram);
    }
}
