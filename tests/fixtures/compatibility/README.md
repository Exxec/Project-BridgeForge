# Synthetic compatibility fixtures

These fixtures contain invented IDs, package names, and metadata only. They
must never contain copied Starsector or third-party mod data. Each fixture is
small enough to assert one migration or diagnostic contract deterministically.

Historical archives may inspire a fixture only through a documented failure
pattern (for example, malformed metadata or an invalid archive). The fixture
must reproduce that pattern with invented minimal content; it must not embed
the archive, its assets, source, or original metadata.
