import java.io.File;
import java.net.URL;
import java.net.URLClassLoader;

import org.codehaus.janino.JavaSourceClassLoader;

/**
 * Compiles one loose script the way Starsector does: Janino's JavaSourceClassLoader over a source
 * root, with the game's jars (and the mod's own jar) as the parent class loader.
 *
 * Used by probe_mod_build (live bug PRB-MISSION-02): javac accepts generics that the game's Janino
 * rejects, so a javac-only check let a Fatal-at-startup mission ship.
 *
 * args: <source root> <class name> <classpath, File.pathSeparator-separated>
 * Prints JANINO_OK <class>, or JANINO_FAIL <class> :: <message> and exits 3.
 */
public class JaninoCheck {
    public static void main(String[] args) throws Exception {
        String[] parts = args[2].split(File.pathSeparator);
        URL[] urls = new URL[parts.length];
        for (int i = 0; i < parts.length; i++) {
            urls[i] = new File(parts[i]).toURI().toURL();
        }
        ClassLoader parent = new URLClassLoader(urls, JaninoCheck.class.getClassLoader());
        JavaSourceClassLoader loader = new JavaSourceClassLoader(parent, new File[] { new File(args[0]) }, "UTF-8");
        try {
            loader.loadClass(args[1]);
            System.out.println("JANINO_OK " + args[1]);
        } catch (ClassNotFoundException e) {
            Throwable cause = e.getCause() != null ? e.getCause() : e;
            System.out.println("JANINO_FAIL " + args[1] + " :: " + cause.getMessage());
            System.exit(3);
        }
    }
}
