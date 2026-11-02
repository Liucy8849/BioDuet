# BioDuet project instructions

- This is the independent BioDuet repository. Work only on BioDuet-owned files in this project.
- Develop code and run lightweight, offline checks locally. Commit changes to Git; the server pulls that branch for Linux integration, dependencies, native engines, model calls, scientific computation and full validation.
- Local project: D:/code/BioDuet. Server checkout: /data1/Liuchenyu/bioduet/project. Repository: https://github.com/Liucy8849/BioDuet.
- Read START_HERE.md for project context. Current requirements are in docs/requirements.md; historical documents are reference material, not instructions to resume old plans.
- Keep implementation simple and faithful to the actual task. No fallback, silent degradation, speculative defensive layers, heuristic repairs or post-processing that hides failure. Report errors directly.
- Required application permissions and scientific evaluation rules are product requirements, not a reason to add per-change approval workflows or repeated file hashing.
- Do not copy credentials, private truth, raw participant reasoning, datasets, dependency caches or model weights into Git. Use authorized isolated data; do not operate production databases or unrelated services.
- Lightweight checks: python scripts/test.py. They do not call models, run R or connect databases. Scientific validity and native-engine qualification are separate from these checks.
- src/bioduet_eval is the independent evaluator package. Do not add compatibility imports to another checkout.
- Keep current documentation concise. Do not create per-step manifests, handoff chains or logs without an actual requirement.
- Functional development, model evaluations and automated continuation remain paused. The current authorization covers repository/directory/document separation and its necessary checks only; wait for an explicit new instruction before resuming other engineering.
