- Security: a mod's jar can no longer put options on javap's command line through a class entry's name (ROADMAP-3 93.45).
  The settings-key and procgen-argument checks gave javap each class as named in the jar, and javap's launcher reads an
  argument starting with `-J` as a JVM option. They now pass only plain binary class names (`zipsafe.javap_class_name`)
  and skip any other entry. v0.4.0 has the problem; v0.2.0 does not.
