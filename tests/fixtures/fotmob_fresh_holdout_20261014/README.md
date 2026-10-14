# Retained AFC CL2 wrapper projection

`afc-cl2-9469-20261014-wrappers.json` is a canonical JSON projection, not the original response bytes. It preserves the four original `id=9469` wrapper objects and their matches from capture `6cb5f96614054a5c91a63515`, with a request-date envelope. No network acquisition was performed to produce this fixture.

- Release: `athena-fresh-holdout-evidence-2026-W42`
- Release asset ID: `636458042`
- Asset: `failure-20261013T083700Z-run-38370644665.tar.gz`
- Asset SHA256: `1c1cd0769ce58300e9f9d71dcedf34edfbe164fed41aea0c14d8707e4c977963`
- Original response SHA256: `27bce777fa289a6a135abd8a4a5b624af736f3ce61c0626fbff7926066ccd23c`
- Original manifest SHA256: `3789cb54af4cab147e8ca3d7fc8f3f959ccb97424972a5e499f89f81876db5ee`
- Projection SHA256: `5b619bf689b1b66ca075ec8995735665b3623131eb8f8f3d905228ab6a266367`

The projection test builds a new manifest and checks lineage against the projection bytes; it does not claim the original capture identity. The adapter receipt separately records both retained capture identities.

Local retained-byte qualification yielded 137 and 144 fixtures respectively for the two original captures, with eight AFC CL2 fixtures in each and original raw lineage preserved. No collection tick, backfill, settlement execution, or authority grant is implied.

The two `*-manifest.json` files are exact original manifest bytes selected from the authenticated retained archive, not raw provider response captures. The second manifest SHA256 is `3482cbb4a16f713536b88b8d8c948aa5cd36508dc55502799909f6b94d52e716`; its actual `observed_at` is `2026-10-13T08:55:14.551847Z`. The wrapper-only projection above remains unchanged and is not source evidence.
