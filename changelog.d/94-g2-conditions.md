- A gene manifest's `conditions` now records the ids its code only checks for (`hasHullMod`, a `contains`, `hasTag`) as
  `checks-for`, since the gene may act only where that content is present (94.G2 slice 15). Single-gene `gene prove` now
  also FAILs isolation when its carrier does not define what the gene provides.
