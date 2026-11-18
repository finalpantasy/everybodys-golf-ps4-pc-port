import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.mem.MemoryBlock;
import ghidra.program.model.symbol.Reference;

import java.io.File;
import java.io.PrintWriter;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;

public class ExportGolfEvidence extends GhidraScript {
    private static final String[] TERMS = {
        "Month Item List",
        "VsEventRegulation",
        "NoticeBox",
        "Notice Box",
        "National Tournament",
        "sceNpMatching2GetServerId",
        "sceNpCommerceShowPsStoreIcon",
        "libSceAppContent",
        "libSceNpTus",
        "libSceNpMatching2",
        "libSceNpSignaling",
        "libSceRudp",
        "libSceNpWebApi"
    };

    private List<Integer> find(byte[] data, byte[] needle) {
        List<Integer> matches = new ArrayList<>();
        for (int i = 0; i + needle.length <= data.length; i++) {
            int j = 0;
            while (j < needle.length && data[i + j] == needle[j]) j++;
            if (j == needle.length) matches.add(i);
        }
        return matches;
    }

    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length != 1) throw new IllegalArgumentException("output path required");
        try (PrintWriter out = new PrintWriter(new File(args[0]), StandardCharsets.UTF_8)) {
            out.println("Program: " + currentProgram.getName());
            for (String term : TERMS) {
                out.println();
                out.println("TERM: " + term);
                byte[] needle = term.getBytes(StandardCharsets.US_ASCII);
                int count = 0;
                for (MemoryBlock block : currentProgram.getMemory().getBlocks()) {
                    if (!block.isInitialized() || block.getSize() > 128 * 1024 * 1024) continue;
                    byte[] data = new byte[(int) block.getSize()];
                    block.getBytes(block.getStart(), data);
                    for (int offset : find(data, needle)) {
                        Address address = block.getStart().add(offset);
                        out.println("  string " + address + " in " + block.getName());
                        Reference[] references = getReferencesTo(address);
                        out.println("    direct references: " + references.length);
                        for (Reference reference : references) {
                            Address from = reference.getFromAddress();
                            Function function = getFunctionContaining(from);
                            out.println("    " + from + " function=" +
                                (function == null ? "<none>" : function.getName() + " @ " + function.getEntryPoint()));
                        }
                        count++;
                    }
                }
                out.println("  occurrences: " + count);
            }
        }
    }
}
