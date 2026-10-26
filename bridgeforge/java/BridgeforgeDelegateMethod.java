package bridgeforge.bytecode;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.HashMap;
import java.util.Map;
import org.objectweb.asm.AnnotationVisitor;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.ClassVisitor;
import org.objectweb.asm.ClassWriter;
import org.objectweb.asm.Handle;
import org.objectweb.asm.Label;
import org.objectweb.asm.MethodVisitor;
import org.objectweb.asm.Opcodes;
import org.objectweb.asm.Type;
import org.objectweb.asm.TypePath;

/**
 * Replace whole method bodies with one static call into a helper class (Exotica 2.1.1-RC4, 2026-10-26).
 *
 * <p>For a Kotlin jar, whose decompiled source does not recompile, the fixed logic goes into a separately compiled
 * Java helper and each chosen method becomes: load this (unless static), load every argument, invokestatic
 * helperOwner.helperName, return. The helper's descriptor is the method's own, with the owner type first for an
 * instance method. Every other method, field and attribute of the class is left as it was. Args: input output, then
 * groups of four: name descriptor helperOwner helperName. Prints the number of methods replaced.
 */
public final class BridgeforgeDelegateMethod {
    public static void main(String[] a) throws Exception {
        if (a.length < 6 || (a.length - 2) % 4 != 0) throw new IllegalArgumentException("expected input output (name desc helperOwner helperName)+");
        Map<String, String[]> wanted = new HashMap<>();
        for (int i = 2; i < a.length; i += 4) wanted.put(a[i] + a[i + 1], new String[] {a[i + 2], a[i + 3]});
        ClassReader reader = new ClassReader(Files.readAllBytes(Path.of(a[0])));
        // Flags 0: untouched methods are copied byte for byte; the replaced body states its own max stack/locals.
        ClassWriter writer = new ClassWriter(reader, 0);
        String owner = reader.getClassName();
        int[] count = {0};
        reader.accept(new ClassVisitor(Opcodes.ASM9, writer) {
            @Override public MethodVisitor visitMethod(int access, String name, String descriptor, String signature, String[] exceptions) {
                MethodVisitor base = super.visitMethod(access, name, descriptor, signature, exceptions);
                String[] target = wanted.remove(name + descriptor);
                if (target == null) return base;
                if ((access & (Opcodes.ACC_ABSTRACT | Opcodes.ACC_NATIVE)) != 0) throw new IllegalStateException(name + descriptor + " has no body to replace");
                count[0]++;
                return new BodyReplacer(base, owner, access, descriptor, target[0], target[1]);
            }
        }, 0);
        if (!wanted.isEmpty()) throw new IllegalStateException("not found in " + owner + ": " + wanted.keySet());
        Files.write(Path.of(a[1]), writer.toByteArray());
        System.out.println(count[0]);
    }

    /** Keeps the method's annotations and parameters, drops its code and writes the delegating call instead. */
    private static final class BodyReplacer extends MethodVisitor {
        private final String owner, descriptor, helperOwner, helperName;
        private final boolean isStatic;
        private int maxStack, maxLocals;

        BodyReplacer(MethodVisitor base, String owner, int access, String descriptor, String helperOwner, String helperName) {
            super(Opcodes.ASM9, base);
            this.owner = owner; this.descriptor = descriptor; this.helperOwner = helperOwner; this.helperName = helperName;
            this.isStatic = (access & Opcodes.ACC_STATIC) != 0;
        }

        @Override public void visitCode() {
            super.visitCode();
            int slot = 0;
            String helperDescriptor = descriptor;
            if (!isStatic) {
                super.visitVarInsn(Opcodes.ALOAD, 0);
                slot = 1;
                helperDescriptor = "(L" + owner + ";" + descriptor.substring(1);
            }
            for (Type argument : Type.getArgumentTypes(descriptor)) {
                super.visitVarInsn(argument.getOpcode(Opcodes.ILOAD), slot);
                slot += argument.getSize();
            }
            super.visitMethodInsn(Opcodes.INVOKESTATIC, helperOwner, helperName, helperDescriptor, false);
            Type returned = Type.getReturnType(descriptor);
            super.visitInsn(returned.getOpcode(Opcodes.IRETURN));
            maxLocals = slot;
            maxStack = Math.max(slot, returned.getSize());
        }

        // The original body is dropped: every instruction, frame, local, line and try/catch entry.
        @Override public void visitFrame(int type, int numLocal, Object[] local, int numStack, Object[] stack) { }
        @Override public void visitInsn(int opcode) { }
        @Override public void visitIntInsn(int opcode, int operand) { }
        @Override public void visitVarInsn(int opcode, int var) { }
        @Override public void visitTypeInsn(int opcode, String type) { }
        @Override public void visitFieldInsn(int opcode, String owner, String name, String descriptor) { }
        @Override public void visitMethodInsn(int opcode, String owner, String name, String descriptor, boolean isInterface) { }
        @Override public void visitInvokeDynamicInsn(String name, String descriptor, Handle bootstrap, Object... arguments) { }
        @Override public void visitJumpInsn(int opcode, Label label) { }
        @Override public void visitLabel(Label label) { }
        @Override public void visitLdcInsn(Object value) { }
        @Override public void visitIincInsn(int var, int increment) { }
        @Override public void visitTableSwitchInsn(int min, int max, Label dflt, Label... labels) { }
        @Override public void visitLookupSwitchInsn(Label dflt, int[] keys, Label[] labels) { }
        @Override public void visitMultiANewArrayInsn(String descriptor, int numDimensions) { }
        @Override public AnnotationVisitor visitInsnAnnotation(int typeRef, TypePath typePath, String descriptor, boolean visible) { return null; }
        @Override public void visitTryCatchBlock(Label start, Label end, Label handler, String type) { }
        @Override public AnnotationVisitor visitTryCatchAnnotation(int typeRef, TypePath typePath, String descriptor, boolean visible) { return null; }
        @Override public void visitLocalVariable(String name, String descriptor, String signature, Label start, Label end, int index) { }
        @Override public AnnotationVisitor visitLocalVariableAnnotation(int typeRef, TypePath typePath, Label[] start, Label[] end, int[] index, String descriptor, boolean visible) { return null; }
        @Override public void visitLineNumber(int line, Label start) { }
        @Override public void visitMaxs(int ignoredStack, int ignoredLocals) { super.visitMaxs(maxStack, maxLocals); }
    }
}
