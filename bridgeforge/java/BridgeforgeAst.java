package bridgeforge.ast;

import com.sun.source.tree.CompilationUnitTree;
import com.sun.source.tree.ImportTree;
import com.sun.source.tree.ClassTree;
import com.sun.source.tree.MethodTree;
import com.sun.source.tree.MethodInvocationTree;
import com.sun.source.tree.VariableTree;
import com.sun.source.util.JavacTask;
import com.sun.source.util.TreeScanner;
import com.sun.source.util.Trees;
import java.io.File;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.charset.StandardCharsets;
import java.util.Base64;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Collections;
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
      java.util.List<String> sourceArgs = new java.util.ArrayList<>();
      for (int i = 0; i < args.length; i++) {
        if ("--sources-file".equals(args[i]) && i + 1 < args.length) sourceArgs.addAll(Files.readAllLines(Path.of(args[++i]), StandardCharsets.UTF_8));
        else sourceArgs.add(args[i]);
      }
      Iterable<? extends javax.tools.JavaFileObject> inputs = files.getJavaFileObjects(sourceArgs.toArray(new String[0]));
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
          private final ArrayDeque<String> classes = new ArrayDeque<>();
          private final ArrayDeque<String> methods = new ArrayDeque<>();
          private String owner() {
            String packageName = unit.getPackageName() == null ? "" : unit.getPackageName().toString();
            java.util.List<String> names = new ArrayList<>(classes);
            Collections.reverse(names);
            String className = classes.isEmpty() ? "[top-level]" : String.join("$", names);
            return packageName.isEmpty() ? className : packageName + "." + className;
          }
          @Override public Void visitClass(ClassTree node, Void unused) {
            classes.push(node.getSimpleName().toString());
            try { return super.visitClass(node, unused); } finally { classes.pop(); }
          }
          @Override public Void visitMethod(MethodTree node, Void unused) {
            long position = trees.getSourcePositions().getStartPosition(unit, node);
            long line = position >= 0 ? unit.getLineMap().getLineNumber(position) : -1;
            String signature = owner() + "#" + node.getName();
            System.out.println("D\t" + encode(file) + "\t" + line + "\t" + position + "\t" + encode(signature));
            methods.push(signature);
            try { return super.visitMethod(node, unused); } finally { methods.pop(); }
          }
          @Override public Void visitMethodInvocation(MethodInvocationTree node, Void unused) {
            long position = trees.getSourcePositions().getStartPosition(unit, node);
            long line = position >= 0 ? unit.getLineMap().getLineNumber(position) : -1;
            long selectPosition = trees.getSourcePositions().getStartPosition(unit, node.getMethodSelect());
            System.out.println("M\t" + encode(file) + "\t" + line + "\t" + selectPosition + "\t" + encode(node.getMethodSelect().toString()));
            if (!methods.isEmpty()) System.out.println("C\t" + encode(file) + "\t" + line + "\t" + selectPosition + "\t" + encode(methods.peek() + "->" + node.getMethodSelect().toString()));
            return super.visitMethodInvocation(node, unused);
          }
          @Override public Void visitVariable(VariableTree node, Void unused) {
            long position = trees.getSourcePositions().getStartPosition(unit, node);
            long line = position >= 0 ? unit.getLineMap().getLineNumber(position) : -1;
            String type = node.getType() == null ? "" : node.getType().toString();
            System.out.println("V\t" + encode(file) + "\t" + line + "\t" + position + "\t" + encode(type + "\u001f" + node.getName()));
            return super.visitVariable(node, unused);
          }
        }.scan(unit, null);
      }
    }
  }
}
