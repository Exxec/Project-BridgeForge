package bridgeforge.bytecode;

import java.nio.file.Files;
import java.nio.file.Path;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.ClassVisitor;
import org.objectweb.asm.ClassWriter;
import org.objectweb.asm.MethodVisitor;
import org.objectweb.asm.Opcodes;

/**
 * One exact symbolic substitution. It does not add instructions or compute frames, except `append-constant-argument`:
 * a call whose target gained one trailing parameter gets `null` (a reference) or `false` (a boolean) pushed right before
 * it and the new descriptor (0.98.5a-RC3's ShipAIConfig(ShipAPI) and ShipAPI.isBeingIgnored(boolean), 2026-11-15). The
 * push sits between the last argument and the call, never at a branch target, so stack map frames stay valid; max stack
 * is recomputed (COMPUTE_MAXS needs no class hierarchy).
 */
public final class BridgeforgeBytecodeRewrite {
    public static void main(String[] a) throws Exception {
        if (a.length != 11) throw new IllegalArgumentException("expected input output action owner name desc opcode newOwner newName newDesc expected");
        Path input=Path.of(a[0]), output=Path.of(a[1]); String action=a[2], owner=a[3], name=a[4], desc=a[5], newOwner=a[7], newName=a[8], newDesc=a[9]; int opcode=Integer.parseInt(a[6]), expected=Integer.parseInt(a[10]);
        boolean append="append-constant-argument".equals(action);
        if (expected < 1) throw new IllegalArgumentException("non-positive expectations are forbidden");
        if (append) {
            int close=desc.indexOf(')'); String added=close < 0 ? "" : newDesc.substring(close, Math.max(close, newDesc.indexOf(')')));
            boolean shape=close > 0 && newOwner.equals(owner) && newDesc.startsWith(desc.substring(0, close)) && newDesc.endsWith(desc.substring(close));
            boolean kind=("null".equals(newName) && added.startsWith("L") && added.endsWith(";") && added.indexOf(';') == added.length() - 1) || ("false".equals(newName) && "Z".equals(added));
            if (!shape || !kind) throw new IllegalArgumentException("append-constant-argument adds exactly one trailing reference (null) or boolean (false) parameter");
        } else if (!newDesc.equals(desc)) throw new IllegalArgumentException("descriptor changes are forbidden");
        ClassReader reader=new ClassReader(Files.readAllBytes(input)); ClassWriter writer=append ? new ClassWriter(ClassWriter.COMPUTE_MAXS) : new ClassWriter(reader, 0); int[] count={0};
        // append builds a fresh constant pool: a copied one keeps the old Methodref, which linkage checks read
        reader.accept(new ClassVisitor(Opcodes.ASM9, writer) {
            @Override public MethodVisitor visitMethod(int access,String method,String descriptor,String signature,String[] exceptions) {
                MethodVisitor base=super.visitMethod(access,method,descriptor,signature,exceptions);
                return new MethodVisitor(Opcodes.ASM9,base) {
                    @Override public void visitMethodInsn(int op,String o,String n,String d,boolean itf) {
                        if (append&&op==opcode&&o.equals(owner)&&n.equals(name)&&d.equals(desc)) { count[0]++; super.visitInsn("null".equals(newName) ? Opcodes.ACONST_NULL : Opcodes.ICONST_0); super.visitMethodInsn(op,o,n,newDesc,itf); return; }
                        if ("remap-method-reference".equals(action)&&op==opcode&&o.equals(owner)&&n.equals(name)&&d.equals(desc)) { count[0]++; super.visitMethodInsn(op,newOwner,newName,d,itf); } else super.visitMethodInsn(op,o,n,d,itf); }
                    @Override public void visitFieldInsn(int op,String o,String n,String d) { if ("remap-field-reference".equals(action)&&op==opcode&&o.equals(owner)&&n.equals(name)&&d.equals(desc)) { count[0]++; super.visitFieldInsn(op,newOwner,newName,d); } else super.visitFieldInsn(op,o,n,d); }
                    @Override public void visitTypeInsn(int op,String type) { if ("remap-class-reference".equals(action)&&op==opcode&&type.equals(owner)) { count[0]++; super.visitTypeInsn(op,newOwner); } else super.visitTypeInsn(op,type); }
                };
            }
        }, 0);
        if (count[0] != expected) throw new IllegalStateException("expected " + expected + " match(es), found " + count[0]);
        Files.write(output, writer.toByteArray()); System.out.println(count[0]);
    }
}
