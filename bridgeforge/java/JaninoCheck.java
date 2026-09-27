import java.io.File;
import java.net.URL;
import java.net.URLClassLoader;

import org.codehaus.janino.JavaSourceClassLoader;

/**
 * Compiles loose scripts the way Starsector does: Janino's JavaSourceClassLoader over source roots,
 * with the game's jars (and the mod's own jars) as the parent class loader.
 *
 * Used by probe_mod_build (live bug PRB-MISSION-02: javac accepts generics that the game's Janino
 * rejects, so a javac-only check let a Fatal-at-startup mission ship) and by compile_check for every
 * mod loose script (ROADMAP P15 item 22.1).
 *
 * args: <source roots> <class names, comma-separated> <classpath>
 *       roots and classpath are File.pathSeparator-separated.
 * Prints one line per class: JANINO_OK <class>, or JANINO_FAIL <class> :: <message>.
 * Exits 3 when any class failed.
 */
public class JaninoCheck {
    // Janino's own compile/parse/scan exceptions anywhere in the cause chain; anything else (an
    // initializer's NullPointerException, a VerifyError) is not a compile error.
    private static Throwable compileError(Throwable e) {
        for (Throwable t = e; t != null; t = t.getCause()) {
            String name = t.getClass().getName();
            if (name.startsWith("org.codehaus.commons.compiler.") || name.startsWith("org.codehaus.janino.")) {
                return t;
            }
            if (t.getCause() == t) {
                break;
            }
        }
        return null;
    }

    public static void main(String[] args) throws Exception {
        String[] parts = args[2].split(File.pathSeparator);
        URL[] urls = new URL[parts.length];
        for (int i = 0; i < parts.length; i++) {
            urls[i] = new File(parts[i]).toURI().toURL();
        }
        String[] rootNames = args[0].split(File.pathSeparator);
        File[] roots = new File[rootNames.length];
        for (int i = 0; i < rootNames.length; i++) {
            roots[i] = new File(rootNames[i]);
        }
        ClassLoader parent = new URLClassLoader(urls, JaninoCheck.class.getClassLoader());
        boolean failed = false;
        for (String className : args[1].split(",")) {
            // A fresh loader per class, so one broken script cannot mask or poison the next.
            JavaSourceClassLoader loader = new JavaSourceClassLoader(parent, roots, "UTF-8");
            try {
                loader.loadClass(className);
                System.out.println("JANINO_OK " + className);
            } catch (Throwable e) {
                Throwable cause = compileError(e);
                if (cause == null) {
                    // Compiled, then failed outside Janino (a static initializer calling game code that
                    // does not exist offline, e.g. Global.getSettings() == null): not a compile error.
                    System.out.println("JANINO_OK " + className + " (initializer not run offline: " + e.getClass().getName() + ")");
                    continue;
                }
                String message = String.valueOf(cause.getMessage()).replace('\r', ' ').replace('\n', ' ');
                System.out.println("JANINO_FAIL " + className + " :: " + message);
                failed = true;
            }
        }
        if (failed) {
            System.exit(3);
        }
    }
}
