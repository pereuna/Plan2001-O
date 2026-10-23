# Chan/Qid/Dirtab/Walk dependency audit — reference index

**External source artifact:** `Plan2001-O_Chan-riippuvuudet(1).txt` supplied by the project owner on 23 October 2026. This file is **NOT** the complete inventory; it is a short index intentionally kept suitable for agent context.

- **Pinned source commit:** `19de707bc6f88d259d4cc1a75179b69aec7393cf`, **NOT** current HEAD.
- **Target:** amd64/`pc64`.
- **Raw artifact:** 2,928,946 bytes / 41,191 lines; SHA-256 `7b9680cd2523c8e16562feedd27478e733860db44da362d0d6abfbd593f5db93`.
- **Stats reported by that audit:** 207 C/header files, 229 source files, 3,447 functions, 151 active C files, 29 `Dev` registrations, 27 devices with local trees, 2,895 dependency occurrences in 620 functions, 16,248 resolved direct call sites, 431 indirect and 1,117 macro call sites.
- **Sections:** build membership; Dev callback relations; struct-field relations; Dirtab definitions; Dirtab/generator argument relations; Qid-dispatch cases; function index; functions with source and call relations; nonfunction references with context; source hashes.

**Important limitations:** lexical/structural analysis only, not a typed or preprocessed C AST; unresolved indirect and macro callbacks, all preprocessor branches retained, build inclusion is not linker proof, and token/call counts overlap. The **GEFS-local** `Chan`, `Mount`, `Path` macro aliases are not the kernel types; `Kchan` denotes the latter in GEFS code. Source locations must be revalidated on HEAD.

**Already tracked related tools:** `python3 tools/kernel_opmap.py --write` generates `docs/KERNEL-OPMAP.md` and `.json`; `--check` verifies their fingerprint. These outputs are related operation maps, **not an exact reproduction** of the owner's separate 41k-line Chan-dependency inventory.

**Storage recommendation:** if the detailed snapshot is needed for automatic code transformation, archive its exact bytes *outside auto-read docs* at e.g. `audit/chan-deps-19de707.txt.gz` (gzip -n) with the original SHA-256. Do not paste the full raw output into `AGENTS.md`, `STATUS.md`, or a standing coding prompt. The original scanner/source and a fresh HEAD-specific scan are preferable to treating an older lexical snapshot as current ground truth.

**Architectural target:** expose the real underlying hardware/resource functions without compulsory hierarchical `walk`/name navigation, distinguish files vs streams vs live handles, and separately classify pathless-but-`Chan`-backed bridges versus genuinely `Chan`-independent native paths. A successful compiler run or zero boot-time path counters is not sufficient proof of whole-kernel independence.
