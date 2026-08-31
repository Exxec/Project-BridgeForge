package bridgeforge.bytecode;

import java.io.BufferedReader;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.jar.JarFile;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.ClassVisitor;
import org.objectweb.asm.FieldVisitor;
import org.objectweb.asm.MethodVisitor;
import org.objectweb.asm.Opcodes;

/** Inspection-only bridge: never defines, loads, or executes inspected classes. */
public final class BridgeforgeBytecode {
    private BridgeforgeBytecode() {}

    public static void main(String[] args) throws Exception {
        if (args.length != 2 || !"--inputs-file".equals(args[0])) {
            throw new IllegalArgumentException("usage: --inputs-file PATH");
        }
        List<Object> classes = new ArrayList<>();
        try (BufferedReader reader = Files.newBufferedReader(Path.of(args[1]))) {
            String raw;
            while ((raw = reader.readLine()) != null) inspect(Path.of(raw), classes);
        }
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("schema_version", 1); result.put("mode", "INSPECTION_ONLY"); result.put("classes", classes);
        System.out.println(json(result));
    }

    private static void inspect(Path input, List<Object> classes) throws Exception {
        if (input.getFileName().toString().endsWith(".jar")) {
            try (JarFile jar = new JarFile(input.toFile())) {
                var entries = jar.entries();
                while (entries.hasMoreElements()) {
                    var entry = entries.nextElement();
                    if (entry.getName().endsWith(".class")) try (InputStream stream = jar.getInputStream(entry)) { classes.add(read(input + "!" + entry.getName(), stream)); }
                }
            }
        } else try (InputStream stream = Files.newInputStream(input)) { classes.add(read(input.toString(), stream)); }
    }

    private static Map<String, Object> read(String input, InputStream stream) throws Exception {
        Map<String, Object> result = new LinkedHashMap<>(); result.put("input", input);
        List<Object> methods = new ArrayList<>(), fields = new ArrayList<>(), refs = new ArrayList<>(), annotations = new ArrayList<>(), inner = new ArrayList<>(), strings = new ArrayList<>();
        new ClassReader(stream).accept(new ClassVisitor(Opcodes.ASM9) {
            @Override public void visit(int version, int access, String name, String signature, String superName, String[] interfaces) {
                result.put("class_name", name); result.put("class_file_version", version); result.put("super_name", superName); result.put("interfaces", List.of(interfaces)); result.put("access", access);
            }
            @Override public void visitSource(String source, String debug) { result.put("source_file", source); }
            @Override public void visitInnerClass(String name, String outer, String innerName, int access) { inner.add(Map.of("name", name, "outer", outer == null ? "" : outer, "inner", innerName == null ? "" : innerName)); }
            @Override public org.objectweb.asm.AnnotationVisitor visitAnnotation(String descriptor, boolean visible) { annotations.add(descriptor); return null; }
            @Override public FieldVisitor visitField(int access, String name, String descriptor, String signature, Object value) { fields.add(Map.of("name", name, "descriptor", descriptor, "access", access)); return null; }
            @Override public MethodVisitor visitMethod(int access, String name, String descriptor, String signature, String[] exceptions) {
                Map<String, Object> method = new LinkedHashMap<>(); method.put("name", name); method.put("descriptor", descriptor); method.put("access", access); method.put("native", (access & Opcodes.ACC_NATIVE) != 0);
                List<Object> opcodes = new ArrayList<>(); method.put("instruction_count", 0); method.put("opcode_sequence", opcodes); method.put("branch_count", 0); method.put("exception_table_count", 0); methods.add(method);
                return new MethodVisitor(Opcodes.ASM9) {
                    private void opcode(int value) { opcodes.add(value); method.put("instruction_count", ((Integer) method.get("instruction_count")) + 1); }
                    private void branch(int value) { opcode(value); method.put("branch_count", ((Integer) method.get("branch_count")) + 1); }
                    @Override public void visitInsn(int opcode) { opcode(opcode); }
                    @Override public void visitIntInsn(int opcode, int operand) { opcode(opcode); }
                    @Override public void visitVarInsn(int opcode, int variable) { opcode(opcode); }
                    @Override public void visitTypeInsn(int opcode, String type) { opcode(opcode); refs.add(Map.of("kind", "type", "opcode", opcode, "owner", type)); }
                    @Override public void visitFieldInsn(int opcode, String owner, String target, String desc) { opcode(opcode); refs.add(Map.of("kind", "field", "opcode", opcode, "owner", owner, "name", target, "descriptor", desc)); }
                    @Override public void visitMethodInsn(int opcode, String owner, String target, String desc, boolean itf) { opcode(opcode); refs.add(Map.of("kind", "method", "opcode", opcode, "owner", owner, "name", target, "descriptor", desc)); }
                    @Override public void visitInvokeDynamicInsn(String name, String desc, org.objectweb.asm.Handle handle, Object... args) { opcode(Opcodes.INVOKEDYNAMIC); refs.add(Map.of("kind", "invokedynamic", "name", name, "descriptor", desc, "bootstrap_owner", handle.getOwner())); }
                    @Override public void visitJumpInsn(int opcode, org.objectweb.asm.Label label) { branch(opcode); }
                    @Override public void visitLdcInsn(Object value) { opcode(Opcodes.LDC); if (value instanceof String) strings.add(value); }
                    @Override public void visitIincInsn(int variable, int increment) { opcode(Opcodes.IINC); }
                    @Override public void visitTableSwitchInsn(int min, int max, org.objectweb.asm.Label defaultLabel, org.objectweb.asm.Label... labels) { branch(Opcodes.TABLESWITCH); }
                    @Override public void visitLookupSwitchInsn(org.objectweb.asm.Label defaultLabel, int[] keys, org.objectweb.asm.Label[] labels) { branch(Opcodes.LOOKUPSWITCH); }
                    @Override public void visitMultiANewArrayInsn(String descriptor, int dimensions) { opcode(Opcodes.MULTIANEWARRAY); }
                    @Override public void visitTryCatchBlock(org.objectweb.asm.Label start, org.objectweb.asm.Label end, org.objectweb.asm.Label handler, String type) { method.put("exception_table_count", ((Integer) method.get("exception_table_count")) + 1); }
                };
            }
        }, ClassReader.SKIP_FRAMES);
        result.put("fields", fields); result.put("methods", methods); result.put("references", refs); result.put("annotations", annotations); result.put("inner_classes", inner); result.put("string_constants", strings);
        return result;
    }

    @SuppressWarnings("unchecked") private static String json(Object value) {
        if (value == null) return "null"; if (value instanceof String s) return '"' + s.replace("\\", "\\\\").replace("\"", "\\\"").replace("\n", "\\n").replace("\r", "\\r") + '"';
        if (value instanceof Number || value instanceof Boolean) return value.toString(); if (value instanceof List<?> list) { List<String> items = new ArrayList<>(); for (Object item : list) items.add(json(item)); return "[" + String.join(",", items) + "]"; }
        Map<String, Object> map = (Map<String, Object>) value; List<String> items = new ArrayList<>(); for (var entry : map.entrySet()) items.add(json(entry.getKey()) + ":" + json(entry.getValue())); return "{" + String.join(",", items) + "}";
    }
}
