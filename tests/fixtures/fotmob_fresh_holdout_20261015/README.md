# Retained AFC CL2 wrapper projection

`afc-cl2-9469-20261015-wrappers.json` is a canonical JSON projection, not the original response bytes. It preserves the three original `id=9469` wrapper objects (groups F, H, G) and their matches from capture `7d46b089a3363f67e42f5fdc`, with a request-date envelope. No network acquisition was performed to produce this fixture.

- Release: `athena-fresh-holdout-evidence-2026-W42`
- Release asset ID: `642716850`
- Asset: `failure-20261015T043700Z-run-38682531200.tar.gz`
- Asset SHA256: `c33aef9563c3cb7239f554343762d09c8e3035c60202abb3310ac42ffabdaf55`
- Original response SHA256: `4a51a979fe4c76903e8a652685b5d06dd0fe7cb7417d19ce59f44e870dce3868`
- Original manifest SHA256: `e6a794624b0c13ce1572003fe70789238d9b99e05c6594bb81215deeff0467fd`
- Projection SHA256: `e0e824e8c8688209bcb6452e3694b20b2f1d780a795a9524f8b17493e228651d`

The projection test builds a new manifest and checks lineage against the projection bytes; it does not claim the original capture identity. The adapter receipt separately records the retained capture identity.

Local retained-byte qualification yielded 93 fixtures for the original capture, with six AFC CL2 fixtures across groups F, G, and H and original raw lineage preserved. No collection tick, backfill, settlement execution, or authority grant is implied.

The `7d46b089a3363f67e42f5fdc-manifest.json` file is exact original manifest bytes selected from the authenticated retained archive, not raw provider response captures. Its actual `observed_at` is `2026-10-15T04:54:59.097819Z`. The wrapper-only projection above remains unchanged and is not source evidence.
