package bridgeforge.bytecode;

import java.nio.file.Files;
import java.nio.file.Path;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.ClassVisitor;
import org.objectweb.asm.ClassWriter;
import org.objectweb.asm.MethodVisitor;
import org.objectweb.asm.Opcodes;

/** One exact symbolic substitution. It does not add instructions or compute frames. */
public final class BridgeforgeBytecodeRewrite {
    public static void main(String[] a) throws Exception {
        if (a.length != 11) throw new IllegalArgumentException("expected input output action owner name desc opcode newOwner newName newDesc expected");
        Path input=Path.of(a[0]), output=Path.of(a[1]); String action=a[2], owner=a[3], name=a[4], desc=a[5], newOwner=a[7], newName=a[8], newDesc=a[9]; int opcode=Integer.parseInt(a[6]), expected=Integer.parseInt(a[10]);
        if (!newDesc.equals(desc) || expected < 1) throw new IllegalArgumentException("descriptor changes and non-positive expectations are forbidden");
        ClassReader reader=new ClassReader(Files.readAllBytes(input)); ClassWriter writer=new ClassWriter(reader, 0); int[] count={0};
        reader.accept(new ClassVisitor(Opcodes.ASM9, writer) {
            @Override public MethodVisitor visitMethod(int access,String method,String descriptor,String signature,String[] exceptions) {
                MethodVisitor base=super.visitMethod(access,method,descriptor,signature,exceptions);
                return new MethodVisitor(Opcodes.ASM9,base) {
                    @Override public void visitMethodInsn(int op,String o,String n,String d,boolean itf) { if ("remap-method-reference".equals(action)&&op==opcode&&o.equals(owner)&&n.equals(name)&&d.equals(desc)) { count[0]++; super.visitMethodInsn(op,newOwner,newName,d,itf); } else super.visitMethodInsn(op,o,n,d,itf); }
                    @Override public void visitFieldInsn(int op,String o,String n,String d) { if ("remap-field-reference".equals(action)&&op==opcode&&o.equals(owner)&&n.equals(name)&&d.equals(desc)) { count[0]++; super.visitFieldInsn(op,newOwner,newName,d); } else super.visitFieldInsn(op,o,n,d); }
                    @Override public void visitTypeInsn(int op,String type) { if ("remap-class-reference".equals(action)&&op==opcode&&type.equals(owner)) { count[0]++; super.visitTypeInsn(op,newOwner); } else super.visitTypeInsn(op,type); }
                };
            }
        }, 0);
        if (count[0] != expected) throw new IllegalStateException("expected " + expected + " match(es), found " + count[0]);
        Files.write(output, writer.toByteArray()); System.out.println(count[0]);
    }
}
