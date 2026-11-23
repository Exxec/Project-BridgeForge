- A literal put as a key into a map field is now a mention when every load of that field in the mod's loaded code only looks
  entries up (`get`, `containsKey`) or puts into it (94.G2 slice 14; owner ruling 2026-11-20). A map that is iterated,
  stored or passed on keeps its keys as needs. One Eridani hull mod's table no longer bundles 10 hull mods.
