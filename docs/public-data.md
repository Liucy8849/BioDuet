# Public data acquisition
The bundled BW-01 engineering world is synthetic and needs no download.
For external data, supply a reviewed JSON manifest with a files array containing
name, HTTPS url, exact bytes and SHA256 for each file, then run:
python -m bioduet.fetch manifest.json NEW_OUTPUT_DIRECTORY
No real-data manifest is invented or implicitly authorized by this prerelease.
The operator owns source access and license verification. Downloads retain failed
.partial files and acquisition receipts. The byte limit is a data-transfer bound,
not a model-call limit. An outer wall/network policy is required.
