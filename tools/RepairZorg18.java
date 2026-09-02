import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.zip.ZipEntry;
import java.util.zip.ZipInputStream;
import java.util.zip.ZipOutputStream;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.ClassVisitor;
import org.objectweb.asm.ClassWriter;
import org.objectweb.asm.MethodVisitor;
import org.objectweb.asm.Opcodes;

/** Creates a repaired copy of the supplied Zorg18 release; it never edits its input. */
public final class RepairZorg18 {
    private static final String SYSTEM_SOURCE = "src/data/shipsystems/scripts/ZorgDisplacerStats.java";
    private static final String MOD_JAR = "jar/Zorg18.jar";
    private static final String SYSTEM_CLASS = "data/shipsystems/scripts/ZorgDisplacerStats.class";

    private RepairZorg18() { }

    public static void main(String[] args) throws Exception {
        if (args.length != 2) throw new IllegalArgumentException("usage: INPUT.zip OUTPUT.zip");
        Path input = Path.of(args[0]).toAbsolutePath().normalize();
        Path output = Path.of(args[1]).toAbsolutePath().normalize();
        if (input.equals(output)) throw new IllegalArgumentException("Output must differ from input.");
        if (!Files.isRegularFile(input)) throw new IllegalArgumentException("Input ZIP does not exist: " + input);
        if (Files.exists(output)) throw new IllegalArgumentException("Refusing to overwrite existing output: " + output);
        Files.createDirectories(output.getParent());
        boolean sourcePatched = false, classPatched = false;
        try (ZipInputStream in = new ZipInputStream(Files.newInputStream(input));
             ZipOutputStream out = new ZipOutputStream(Files.newOutputStream(output))) {
            ZipEntry entry;
            while ((entry = in.getNextEntry()) != null) {
                ZipEntry copy = new ZipEntry(entry.getName());
                out.putNextEntry(copy);
                byte[] content = in.readAllBytes();
                if (SYSTEM_SOURCE.equals(entry.getName())) {
                    content = patchSource(content);
                    sourcePatched = true;
                } else if (MOD_JAR.equals(entry.getName())) {
                    PatchResult result = patchJar(content);
                    content = result.content;
                    classPatched = result.classPatched;
                }
                out.write(content);
                out.closeEntry();
                in.closeEntry();
            }
        }
        if (!sourcePatched || !classPatched) {
            Files.deleteIfExists(output);
            throw new IllegalStateException("Expected source/JAR targets were not both found (source=" + sourcePatched + ", class=" + classPatched + ").");
        }
        System.out.println("Wrote repaired archive: " + output);
    }

    private static byte[] patchSource(byte[] input) {
        String text = new String(input, StandardCharsets.UTF_8);
        text = text.replaceAll("(?s)@Override\\s+public float getActiveOverride\\(ShipAPI ship\\) \\{.*?\\n\\s*\\}", "@Override\n\tpublic float getActiveOverride(ShipAPI ship) { return -1f; }");
        text = text.replaceAll("(?s)@Override\\s+public float getInOverride\\(ShipAPI ship\\) \\{.*?\\n\\s*\\}", "@Override\n\tpublic float getInOverride(ShipAPI ship) { return -1f; }");
        text = text.replaceAll("(?s)@Override\\s+public float getOutOverride\\(ShipAPI ship\\) \\{.*?\\n\\s*\\}", "@Override\n\tpublic float getOutOverride(ShipAPI ship) { return -1f; }");
        text = text.replaceAll("(?s)@Override\\s+public int getUsesOverride\\(ShipAPI ship\\) \\{.*?\\n\\s*\\}", "@Override\n\tpublic int getUsesOverride(ShipAPI ship) { return -1; }");
        text = text.replaceAll("(?s)@Override\\s+public float getRegenOverride\\(ShipAPI ship\\) \\{.*?\\n\\s*\\}", "@Override\n\tpublic float getRegenOverride(ShipAPI ship) { return -1f; }");
        if (text.contains("UnsupportedOperationException")) throw new IllegalStateException("Source patch did not remove every placeholder.");
        return text.getBytes(StandardCharsets.UTF_8);
    }

    private static PatchResult patchJar(byte[] input) throws Exception {
        ByteArrayOutputStream result = new ByteArrayOutputStream();
        boolean patched = false;
        try (ZipInputStream in = new ZipInputStream(new ByteArrayInputStream(input));
             ZipOutputStream out = new ZipOutputStream(result)) {
            ZipEntry entry;
            while ((entry = in.getNextEntry()) != null) {
                out.putNextEntry(new ZipEntry(entry.getName()));
                byte[] content = in.readAllBytes();
                if (SYSTEM_CLASS.equals(entry.getName())) {
                    content = patchClass(content);
                    patched = true;
                }
                out.write(content);
                out.closeEntry();
                in.closeEntry();
            }
        }
        return new PatchResult(result.toByteArray(), patched);
    }

    private static byte[] patchClass(byte[] input) {
        ClassReader reader = new ClassReader(input);
        ClassWriter writer = new ClassWriter(ClassWriter.COMPUTE_MAXS);
        reader.accept(new ClassVisitor(Opcodes.ASM9, writer) {
            @Override public MethodVisitor visitMethod(int access, String name, String descriptor, String signature, String[] exceptions) {
                MethodVisitor delegate = super.visitMethod(access, name, descriptor, signature, exceptions);
                if (!isTimingOverride(name, descriptor)) return delegate;
                return new MethodVisitor(Opcodes.ASM9) {
                    @Override public void visitEnd() {
                        delegate.visitCode();
                        if ("getUsesOverride".equals(name)) delegate.visitInsn(Opcodes.ICONST_M1);
                        else delegate.visitLdcInsn(-1f);
                        delegate.visitInsn("getUsesOverride".equals(name) ? Opcodes.IRETURN : Opcodes.FRETURN);
                        delegate.visitMaxs(0, 0);
                        delegate.visitEnd();
                    }
                };
            }
        }, 0);
        return writer.toByteArray();
    }

    private static boolean isTimingOverride(String name, String descriptor) {
        return "(Lcom/fs/starfarer/api/combat/ShipAPI;)F".equals(descriptor)
                && ("getActiveOverride".equals(name) || "getInOverride".equals(name) || "getOutOverride".equals(name) || "getRegenOverride".equals(name))
                || "(Lcom/fs/starfarer/api/combat/ShipAPI;)I".equals(descriptor) && "getUsesOverride".equals(name);
    }

    private record PatchResult(byte[] content, boolean classPatched) { }
}
