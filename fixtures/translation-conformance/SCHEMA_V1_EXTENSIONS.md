# Translation schema-v1 extension profile 1

Aligned 2026-10-19 by the Project Go / BridgeForge follow-up. This is an additive profile of `schema_version: 1`, not
schema 2. The original corpus and its `VERSION` stay unchanged. Both repositories carry byte-identical copies of this
document, `schema-v1-extensions.json` and `schema-v1-roles.json`, and test against their decoded source/output bytes.
Base64 stores synthetic binary classes and preserves BOM, GB18030 and mixed line endings without Git conversion.

## Additional units

| Kind | Stable id | Context | Content |
|---|---|---|---|
| `text-line` | `text:<relative file>@<1-based line>` | `{"line":N}` | CJK line content, excluding Java `Character.isWhitespace` at its edges |
| `class` | `class:<relative file>#<constant-pool index>` | `{"cp_index":N}` | CJK referenced CONSTANT_String values from a loose class |

Text eligibility: `.txt` anywhere below a `data/strings/` directory, or directly in `data/missions/<mission>/`.
Line numbering splits on LF; CR and other edge whitespace remain outside the replacement span. UTF-8, optional BOM,
and strict GB18030 fallback are preserved. Nonbreaking spaces follow Java's whitespace rule and remain part of the unit.
A target containing CR or LF is refused for a text-line. Loose classes and text have a 64 MiB read cap. Classes are never
loaded or executed; unreferenced UTF-8 constants are not units. `.ssmt-backup/` is excluded from discovery.

## Optional metadata

- `roles_version`: text describing the producer's classification rules; never an approval token.
- Entry `role`: TEXT (also the default when absent), IDENTIFIER, LINKED or UNKNOWN.
- Entry `role_rule`: optional text naming the deciding rule.
- Entry `group`: nonblank text, present only on LINKED entries. A declared group has at least two members with identical
  source text. All members receive one target or none. Different groups may not collapse to one target.
- IDENTIFIER entries are retained in interchange but are not translated, including glossary fallback. UNKNOWN does not
  mean automatically approved. Role fields never create human or policy approval.

Both readers refuse unsupported schemas/kinds and invalid role/group shapes before applying. Protected identity fields
(`id`, `file`, `kind`, `context`, `source`) and source hashes are checked against the selected source. Unknown extension
fields stay round-trippable in Project Go. Plain exports without role annotations remain valid.

Project Go recomputes classification from source at apply time. BridgeForge consumes declared roles, does not claim to
implement Project Go's classifier, and conservatively refuses a translated group if any rediscovered unit sharing its
source text is outside that group. This refusal avoids guessing which undeclared reference may move. Review the complete
document; removing annotations is not evidence that a unit is safe to translate.

BridgeForge stages LINKED applications into a new `--out` copy and refuses publication on any format rejection. Its
LINKED in-place path is explicitly unsupported and refused; Project Go's tested in-place path remains available. Ordinary
unannotated BridgeForge documents retain the existing copy/in-place behaviour. This profile does not certify a mod's
runtime behaviour, save compatibility, full translation coverage or release readiness.

## Fixtures

- `schema-v1-extensions.json`: five text/class units, exact file hashes, UTF-8 BOM and GB18030 bytes, line numbers,
  whitespace, placeholders, constant references and expected rewritten files.
- `schema-v1-roles.json`: a protected identifier and a linked CSV/map-key group; one supplied group target propagates to
  both references, while the identifier stays unchanged and is reported as protected.
