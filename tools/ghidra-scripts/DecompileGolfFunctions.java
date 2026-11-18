import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;

import java.io.File;
import java.io.PrintWriter;
import java.nio.charset.StandardCharsets;

public class DecompileGolfFunctions extends GhidraScript {
    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length < 2) throw new IllegalArgumentException("output path and at least one address required");
        DecompInterface decompiler = new DecompInterface();
        decompiler.openProgram(currentProgram);
        try (PrintWriter out = new PrintWriter(new File(args[0]), StandardCharsets.UTF_8)) {
            for (int i = 1; i < args.length; i++) {
                Address address = currentProgram.getAddressFactory().getDefaultAddressSpace().getAddress(args[i]);
                Function function = getFunctionAt(address);
                if (function == null) function = getFunctionContaining(address);
                out.println("ADDRESS: " + args[i]);
                if (function == null) {
                    out.println("No function found");
                    continue;
                }
                out.println("FUNCTION: " + function.getName() + " @ " + function.getEntryPoint());
                DecompileResults result = decompiler.decompileFunction(function, 120, monitor);
                out.println("COMPLETED: " + result.decompileCompleted());
                out.println(result.getDecompiledFunction() == null ? result.getErrorMessage() : result.getDecompiledFunction().getC());
            }
        } finally {
            decompiler.dispose();
        }
    }
}
