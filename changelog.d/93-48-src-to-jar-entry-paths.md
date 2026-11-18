- Security: `src-to-jar` no longer writes a jar entry outside its scratch folder (ROADMAP-3 93.48). An entry stored as
  `pkg/Name$\..\..\x.class` compiled fine for javac but was a path out of the folder to Python's zipfile on Windows, so
  the proof overwrote an existing file with the mod's bytes. Only plain class names are read now, and a write must stay in
  the folder.
