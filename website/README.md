# BioDuet website

Independent read-only research website. Vue 3 + TypeScript + Vite, static versioned JSON, no backend or database. This directory has its own source and deployment configuration.

## Local development

Requires Node >=22.15. Use this package directory, not the repository's root scripts.

```sh
npm ci --ignore-scripts
npm run dev
```

Open `http://127.0.0.1:4173`. Language, filters, selected runs and event location are encoded in the hash URL. UI language is also stored locally when the browser permits it. No accounts, analytics, remote fonts, online translations or model calls.

```sh
npm run verify:release
npm run build
npm test
```

Build output: `website/dist/`. Browser QA: `website/test-results/`. Tests use Playwright Chromium by default. Set BIODUET_BROWSER_EXECUTABLE to an existing compatible Chromium executable when managing browsers separately. Install browser dependencies only in your authorized environment. No Jest, global DB setup or backend imports are used.

## Data identity

The bundled `demo-v1` contains **fictional UI fixtures, not experimental results**. Task titles reflect the design-only v0.3 catalogue; descriptions and English translations are engineering drafts. Eight fictional runs exercise completed/incomplete attempts, missing metrics, restricted events and artifact comparisons. They are not BW01 pilot results. Regenerate explicitly with `npm run data:demo` only when fixture changes are intended.

`src/schema.ts` is the strict public projection contract. `release.json` lists every index/detail file with bytes and SHA-256. The browser validates all index files and lazily verifies details before display. `scripts/verify-release.mjs` additionally rejects unlisted files and symbolic links, checks artifact row hashes, and scans basic private-material signatures. This scan supplements rather than replaces human disclosure review. Original trace bodies remain English; translated labels never alter source messages, enums, metrics or judgments.

## Real data integration

Prepare a **new, independently reviewed public projection** on the server using the schema. Do not copy private traces or QA directories into `public/`. The raw BW01 source-to-public field mapping is not implemented or validated without the server evidence. Retain all attempts and missingness; never infer scores, pair identities or event content. Reject unknown fields instead of silently publishing them.

Validate an explicit candidate directory with:

```sh
node scripts/verify-release.mjs --directory=/absolute/path/to/reviewed-release --production
```

This must refuse the bundled demonstration. Only an `audience=public`, `status=approved` release with a `review_ref` and reviewed translations passes the publication identity gate. Checksums prove consistency, not authorship or scientific validity. An operator must independently verify the review reference. Once accepted, transfer only the exact declared public files to a new versioned folder, set `VITE_BIODUET_RELEASE` to that folder name at build time (the default is `demo-v1`), and rerun the data contract and browser tests against that release. Preserve the previous release and withdrawal records. Do not overwrite demo files to disguise their identity.

## Static hosting

Serve the **built dist directory only**, never the repository, source tree or Vite dev server. Hash routing works under a subdirectory. The site has no API endpoints and never executes model-generated HTML. Artifact tables and reports render text through Vue's escaping. Approved PNG previews use bounded data URLs validated by the release schema; SVG and HTML execution are not supported. Artifact SHA-256 covers the canonical rows JSON, literal report text, or complete PNG data-URL string respectively, independently of any original scientific source checksum. CSV formula-like values are quoted and prefixed. Real hosting, domain, HTTPS and rollback destination remain deployment-specific and are not configured by running a local preview.

Recommended production headers are in `deploy/headers.conf.example`. Set `index.html` and `release.json` to `no-cache`; immutable content-addressed assets may be cached. Keep old versioned releases addressable or explicitly withdrawn. Publish to a new version directory and atomically switch the host's serving pointer; roll back to the last verified directory. Do not overwrite or restart unrelated services.

No formal leaderboard is enabled. Formal aggregate statistics and scientific results remain a separate R4 release requirement.
