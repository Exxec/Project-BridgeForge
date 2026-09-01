# Legacy JSON compatibility policy

Bridgeforge first parses JSON strictly. It has one verified target-compatible
path: trailing commas immediately before `}` or `]`, outside JSON strings. It
also has a structural-only inspection path for `#` comments outside strings.
Both paths are read-only and produce `REVIEW` findings; Bridgeforge does not
rewrite a file merely because it can parse it.

## Evidence

On 2026-08-31, the locally installed target distribution's
`starsector-core/json.jar` was exercised directly with `org.json.JSONObject`
and `org.json.JSONArray`. It accepted both `{"value": 1,}` and `[1,]`.
Historical Ironclads and the supplied Edmund's Church 2.5 rewrite contained
this syntax.

The same installed `org.json` parser rejected `#` comments on 2026-08-31.
Bridgeforge may therefore expose metadata recovered through its structural-only
comment parser, but it labels that metadata unverified and does not use its
declared game version for confident environment inference.

## Non-goals

Unquoted keys, alternate encodings, and every other non-standard syntax remain
invalid until separately verified against the selected target parser. A
`REVIEW` finding is evidence for a human decision, not a claim that all
Starsector versions accept the file.
