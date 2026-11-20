- `gene prove-set <mod> <anchor> --out <folder> --vanilla-core <core>` builds one carrier for a gene and every gene its needs
  name, in turn (94.G2 slice 11), and writes its static isolation proof, `set-isolation-proof.json`:
  - **Members:** each is written once; one path with two different contents is refused.
  - **Isolation:** unresolved references may name only what the set provides or the core supplies.
  - **What the proof lists:** refused needs, registrations the carrier does not make, suspects by file, and ids that
    nothing carries.

  One progress line per gene; an interrupted walk resumes from a checkpoint.
