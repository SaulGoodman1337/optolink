// Proprietary M16C RAM bytes are never included in this script or its output.
// Run only on SHA-verified locally captured controller SRAM snapshots or controls.
// A blind instruction decode CANNOT demonstrate RAM contents are firmware.
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.listing.InstructionIterator;
import ghidra.program.model.mem.MemoryBlock;
import java.util.TreeMap;
import java.util.Map;

public class Wb2aM16cCacheProbe extends GhidraScript {
    @Override
    protected void run() throws Exception {
        MemoryBlock[] blocks = currentProgram.getMemory().getBlocks();
        MemoryBlock b = null;
        for (MemoryBlock block : blocks) {
            println("MEMORY_BLOCK name="+block.getName()+" initialized="+block.isInitialized()+
                    " start="+block.getStart()+" size="+block.getSize());
            if (block.isInitialized() && block.getSize() >= 1024 &&
                    block.getSize() <= 20480) {
                if (b != null) throw new IllegalStateException("Multiple candidate raw RAM blocks");
                b = block;
            }
        }
        if (b == null) {
            throw new IllegalStateException("Missing initialized raw RAM input block");
        }
        Address start = b.getStart();
        long size = b.getSize();
        if (size < 1024 || size > 20480) {
            throw new IllegalStateException("Only bounded 1..20KiB RAM artifacts");
        }
        String language = currentProgram.getLanguageID().toString();
        if (!language.startsWith("M16C/60:")) {
            throw new IllegalStateException("M16C/60 language is required: " + language);
        }
        int seeds = 0, attempted = 0;
        for (int offset = 0; offset < size - 8; offset += 97) {
            Address candidate = start.add(offset);
            if (!currentProgram.getListing().isInFunction(candidate)) {
                attempted++;
                if (disassemble(candidate)) seeds++;
            }
        }
        int count=0,bytes=0,jumps=0,calls=0,returns=0,inside=0,outside=0,rom_targets=0;
        int distinctInstructions=0;
        Map<String,Integer> names = new TreeMap<String,Integer>();
        for (InstructionIterator it=currentProgram.getListing().getInstructions(true);it.hasNext();) {
            Instruction ins=it.next();
            count++;
            bytes+=ins.getLength();
            String op=ins.getMnemonicString();
            names.put(op,names.getOrDefault(op,0)+1);
            if (ins.getFlowType().isJump()) jumps++;
            if (ins.getFlowType().isCall()) calls++;
            if (ins.getFlowType().isTerminal()) returns++;
            for (Address target : ins.getFlows()) {
                long to=target.getOffset();
                if (to >= start.getOffset() && to < start.getOffset()+size) inside++;
                else outside++;
                if (to >= 0xC0000L && to <= 0xFFFFFL) rom_targets++;
            }
        }
        StringBuilder top=new StringBuilder();
        names.entrySet().stream()
          .sorted((a,c) -> Integer.compare(c.getValue(),a.getValue()))
          .limit(15)
          .forEach(e -> {
              if (top.length()>0)top.append(",");
              top.append(e.getKey()).append(":").append(e.getValue());
          });
        println("WB2A_M16C_PROBE_RESULT filename="+currentProgram.getName()+
                " lang="+language+
                " base="+start.toString()+
                " len="+size+" seed_attempts="+attempted+" seed_success="+seeds+
                " instructions="+count+" covered_bytes="+bytes+
                " coverage="+String.format("%.4f", (double)bytes / (double)size)+
                " jumps="+jumps+" calls="+calls+" terminals="+returns+
                " inner_targets="+inside+" external_targets="+outside+
                " highrom_targets="+rom_targets+
                " mnemonic_top="+top.toString());
    }
}
