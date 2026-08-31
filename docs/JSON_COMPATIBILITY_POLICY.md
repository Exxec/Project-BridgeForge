# Legacy JSON compatibility policy

Bridgeforge first parses JSON strictly. It has one intentionally narrow
compatibility path: trailing commas immediately before `}` or `]`, outside JSON
strings. This path is read-only and produces a `REVIEW` finding; Bridgeforge
does not rewrite the file merely because it can parse it.

## Evidence

On 2026-08-31, the locally installed target distribution's
`starsector-core/json.jar` was exercised directly with `org.json.JSONObject`
and `org.json.JSONArray`. It accepted both `{"value": 1,}` and `[1,]`.
Historical Ironclads and the supplied Edmund's Church 2.5 rewrite contained
this syntax.

## Non-goals

Comments, unquoted keys, alternate encodings, and every other non-standard
syntax remain invalid until separately verified against the selected target
parser. A `REVIEW` finding is evidence for a human decision, not a claim that
all Starsector versions accept the file.
