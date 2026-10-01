# Immutable failed LG-A evidence

These three non-sensitive JSON documents are exact payload bytes from run
36846297806, attempt 1, head 426f36e60ebb421af003ed3154c4da48007d674a,
artifact 11153681944 (`athena-run-36846297806`). ZIP SHA-256:
efe42a986203619cfbffa1c01be10951c027ecb2636cdc4ddc2edb283a2adf56.

The observed old manifest intentionally retains `restore_eligible=true` and its
original self-SHA. It is structurally valid but producer-semantically ineligible.
No correction, provider replay or retry is implied. The exact PR119 bytes needed
to reconstruct the relevant archive layout come from the already retained C2
gzip fixture; no live download is needed. No credentials/source capture exist.
