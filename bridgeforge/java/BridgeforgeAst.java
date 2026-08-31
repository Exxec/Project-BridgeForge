package bridgeforge.ast;

import com.sun.source.tree.CompilationUnitTree;
import com.sun.source.tree.ImportTree;
import com.sun.source.tree.MethodInvocationTree;
import com.sun.source.util.JavacTask;
import com.sun.source.util.TreeScanner;
import com.sun.source.util.Trees;
import java.io.File;
import java.nio.charset.StandardCharsets;
import java.util.Base64;
import javax.tools.JavaCompiler;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;

/** Emits parse-only Java source facts as tab-separated, base64-encoded records. */
public final class BridgeforgeAst {
  private static String encode(String value) {
    return Base64.getEncoder().encodeToString(value.getBytes(StandardCharsets.UTF_8));
  }

  public static void main(String[] args) throws Exception {
    JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
    if (compiler == null) throw new IllegalStateException("A JDK compiler is required");
    try (StandardJavaFileManager files = compiler.getStandardFileManager(null, null, StandardCharsets.UTF_8)) {
      Iterable<? extends javax.tools.JavaFileObject> inputs = files.getJavaFileObjects(args);
      JavacTask task = (JavacTask) compiler.getTask(null, files, null, java.util.List.of("-proc:none"), null, inputs);
      Iterable<? extends CompilationUnitTree> units = task.parse();
      Trees trees = Trees.instance(task);
      for (CompilationUnitTree unit : units) {
        String file = new File(unit.getSourceFile().toUri()).getPath();
        for (ImportTree importTree : unit.getImports()) {
          long line = unit.getLineMap().getLineNumber(trees.getSourcePositions().getStartPosition(unit, importTree));
          System.out.println("I\t" + encode(file) + "\t" + line + "\t" + trees.getSourcePositions().getStartPosition(unit, importTree) + "\t" + encode(importTree.getQualifiedIdentifier().toString()));
        }
        new TreeScanner<Void, Void>() {
          @Override public Void visitMethodInvocation(MethodInvocationTree node, Void unused) {
            long position = trees.getSourcePositions().getStartPosition(unit, node);
            long line = position >= 0 ? unit.getLineMap().getLineNumber(position) : -1;
            long selectPosition = trees.getSourcePositions().getStartPosition(unit, node.getMethodSelect());
            System.out.println("M\t" + encode(file) + "\t" + line + "\t" + selectPosition + "\t" + encode(node.getMethodSelect().toString()));
            return super.visitMethodInvocation(node, unused);
          }
        }.scan(unit, null);
      }
    }
  }
}
