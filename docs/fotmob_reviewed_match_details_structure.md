# Reviewed FotMob match-details structural assessment

## Purpose

PR #53 is the first boundary permitted to parse the preserved `/api/matchDetails` response body. It does so only to inventory JSON structure.

The chain is:

```text
PR #51 persisted response.json + manifest.json
→ PR #52 exact historical byte verification
→ PR #53 strict structural JSON assessment
→ later explicit human semantic review
```

PR #53 does not assign football meaning to any FotMob key.

## Exact ancestry gate

The assessor requires all four inputs:

- the exact PR #52 verified evidence object;
- its exact canonical PR #52 receipt bytes;
- the exact persisted canonical manifest bytes;
- the exact persisted raw response bytes.

It reruns PR #52 from the manifest/raw bytes, compares the rebuilt canonical receipt with the supplied PR #52 object, and then requires the supplied receipt bytes to be exactly identical. A mutated or detached receipt cannot silently cross the boundary.

## Strict response JSON

The raw body must be:

- strict UTF-8;
- valid JSON;
- a JSON object at the root;
- duplicate-key free at every object level;
- free of NaN/Infinity constants;
- free of numeric values that parse to non-finite floats.

The parser does not coerce strings to numbers, infer missing values, apply defaults, or normalize football data.

## Structural inventory

Every parsed node is inventoried with a deterministic JSON-pointer-shaped path and one or more observed JSON value kinds:

- `OBJECT`
- `ARRAY`
- `STRING`
- `INTEGER`
- `NUMBER`
- `BOOLEAN`
- `NULL`

Array members use the structural wildcard `/*`, so repeated array elements contribute to one structural path. Object-key pointer tokens use RFC 6901 escaping (`~` → `~0`, `/` → `~1`).

The assessment records:

- exact PR #52 receipt SHA-256;
- manifest/raw SHA-256 identity;
- fixture/source match identity;
- sorted top-level keys;
- total structural node count;
- maximum structural depth;
- sorted unique structural paths;
- observed kinds and occurrence counts for every path.

To keep assessment bounded and fail-closed, maximum depth is 64, maximum parsed nodes is 100,000, maximum distinct paths is 50,000, and maximum pointer length is 2,048 characters.

## What structure does not mean

A path such as `/general/homeTeam/id` being present does **not** establish that it is a trustworthy team identifier. A key called `injured`, `lineup`, `weather`, `form`, or anything else is not given football meaning merely because of its name.

PR #53 therefore authorizes no semantic use of any observed path.

## Safety

All downstream authorization remains false, including:

- semantic review automation;
- source qualification;
- football semantics;
- field extraction;
- Fixture Intelligence facts/snapshots;
- model features;
- probabilities;
- pricing;
- selections;
- bets.

The next safe boundary is PR #54: an explicit human-reviewed field-semantics decision contract anchored to the exact PR #53 assessment.
