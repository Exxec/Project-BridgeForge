- Tooling: the pre-push hook lints the branch's changed Python files and checks the generated docs first, then runs the tests
  that import a changed module as well as those named after it, leaving the measured slow tests and a central module's
  many importers to CI (ROADMAP-3 96.5 C5).
