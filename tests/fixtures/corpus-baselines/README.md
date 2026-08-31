# Sanitized comparison baselines

These files capture aggregate scanner expectations for user-supplied real
mods. They contain only a version fingerprint, file count, and finding IDs;
they must never include mod assets, source, metadata contents, or local paths.
They support repeatable tuning against real-world failure patterns while CI
continues to run entirely from synthetic fixtures.
