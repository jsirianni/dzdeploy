# Development and CI

Use the Go toolchain selected by go.mod, Python 3.10 or newer, and Git. The optional Makefile is a convenience; the Python and Go commands work directly in PowerShell and Linux shells.

```text
python scripts/ci.py install
python -m unittest discover -s scripts -p "test_*.py"
python scripts/smoke_ci.py
python scripts/ci.py all
go vet ./...
go test -race -count=1 ./...
make fuzz
```

Run make for the complete task list. Pinned analyzers are recorded in scripts/ci-tools.json and installed under ignored .tools/ci-bin/. Tool version upgrades require a reviewed change to that file; Dependabot manages application modules and Actions, not tool versions embedded in this JSON file.

## Supported platforms and required checks

The dzdeploy workflow runs on main pushes, pull requests, a weekly schedule, and manual dispatch. All workflow Go versions come from go.mod; the existing toolchain directive remains effective.

- Windows and Linux: uncached all-package tests, vet, build, module verification/tidy checks, native portable packages, formatting/imports, Staticcheck, focused Revive, strict errcheck, gosec, native atomic statement coverage, and gate regression tests.
- Linux: race detection, reachable-vulnerability checks against vuln.go.dev, and bounded exploration of the portable-path and JSON log-record parsers. Fuzz seed cases run in ordinary tests on both platforms.
- Windows: reachable-vulnerability checks also include Windows-only dependencies. Mock SSH bootstrap, real SSH bootstrap on Windows 2022/2025, and isolated operator service/restart/backup/restore integration remain enabled.
- The CI aggregate requires every platform, quality, integration, race/vulnerability, and fuzz job to succeed. It rejects failed, cancelled, or skipped prerequisites. Native package and diagnostic artifacts remain available from Actions.

The host companion remains Windows amd64. Linux is a client platform, not a newly supported host. ARM64 clients can be cross-packaged with the existing packager; native CI runs on amd64. The separate release workflow validates the complete release package matrix when present.

## Explicit inherited analysis debt

A passing gate means no new or changed findings beyond the committed inventory. It does not mean the existing application has no security or correctness issues.

The repository was extracted with legacy unchecked errors and modernization work. This CI change inventories them instead of making hundreds of behavior changes. scripts/ci-baselines/ contains separate native Windows and Linux inventories for Staticcheck, Revive, errcheck, gosec, and go fix. Each record binds a finding to its rule, file, enclosing declaration, exact source, and diagnostic; repeated identical findings are counted. Moving an unchanged line is tolerated. New contexts, additional occurrences, changed findings, and stale entries fail. Every existing finding and its count remains visible in CI logs and quality report artifacts. Package-load errors, crashes, malformed output, and partial go-fix output accompanied by errors fail rather than becoming accepted debt.

The initial Windows inventory is 14 Staticcheck findings, 8 focused Revive findings, 365 strict errcheck findings, 113 gosec findings, and 49 Go modernization edits. Linux has its own measured inventory because platform-specific source and reachable declarations differ. No linter is globally disabled. errcheck excludes only the documented infallible bytes.Buffer/strings.Builder writes copied from the reference policy; file, stream, cleanup, state, and arbitrary writer errors remain scanned.

Meaningful inherited follow-up work remains visible:

- Error handling includes ignored durable state/result writes in backup and deployment paths. These warrant focused failure/recovery changes and tests; they are not all harmless cleanup noise.
- Windows gosec reports 30 HIGH findings: 12 integer conversions, 15 tainted paths, 1 command construction, and 2 WalkDir path-race findings. The G122 findings in syncModContext deserve a review of root-scoped operations and link substitution races. Integer conversions in disk-space accounting, process IDs, and service timing need their existing bounds checked. Taint reports in service command construction and file access need dataflow and trust-boundary review.
- Some reports reflect expected platform operations: test-host fixtures read explicitly supplied files, Windows service APIs require unsafe pointers, and the service SID uses SHA-1 as required by Windows. Such examples do not justify suppressing unrelated path, command, conversion, or unchecked-write findings.
- Staticcheck also reports unused platform-dependent helpers, capitalized diagnostics, a dead assignment in a test, and deprecated Windows token APIs. These are distinct from its future correctness checks.

The inventory is not a set of findings proven exploitable or proven false positive. Removing debt should be a focused reviewed change. Do not regenerate an entire baseline to make a new finding pass. After fixing findings, remove their stale entries. If an intentional toolchain/tool upgrade changes diagnostics, review the full difference on both native platforms before updating the corresponding inventory. The explicit maintenance command is python scripts/ci.py CHECK --write; CI never invokes --write.

Formatting checks normalize CRLF only in scratch copies. Applying python scripts/ci.py format --write preserves each original file's newline style and changes only actual formatting/import differences. go fix -diff is non-mutating and its known rewrites are tracked without applying a broad modernization.

## Coverage regression policy

The coverage gate always runs all default-tag packages with -count=1 -covermode=atomic. It weights Go's statement counts, never averages rounded package percentages, and checks every package separately against its native-platform baseline. A decrease of up to 0.5 percentage points is allowed. New/missing packages, malformed profiles, duplicate blocks, missing statements, and larger decreases fail. Profile files are temporary and cleaned up on success or failure; measured package totals appear in ignored reports and Actions artifacts.

The extracted command entry point has no direct tests and starts at zero coverage. The packager's entry point likewise has low direct coverage; its supported-platform unit tests and separate executable integration/package validations remain in place. These low floors are explicit, not an assertion of exhaustive behavior coverage.

To review a deliberate baseline change, run python scripts/ci.py coverage --write on each native platform after reviewing the test changes and inspect scripts/ci-baselines/coverage-PLATFORM.json. Partial test selections cannot establish the baseline. Unit tests exercise weighted arithmetic, the inclusive threshold, failure paths, package classification, CRLF normalization, and stale/new analysis detection. Real pinned-tool fixtures prove that enabled analysis rules actually reject violations, including errors in tests and narrow security suppressions beside unrelated unsafe calls.

## Dependency and Go updates

Dependabot checks all direct/indirect Go module dependencies and GitHub Actions weekly on Monday at 09:00 America/New_York. Minor/patch version updates are grouped by ecosystem, security updates have separate groups, and major updates remain outside version-update groups. Source-repository OpenTelemetry groups and generator compatibility ceilings do not apply to dzdeploy.

The daily/manual Update Go workflow queries the official stable Go feed, opens or updates automation/update-go, and advances both the Go directive and an existing toolchain directive together. It accepts numeric stable releases, rejects malformed/prerelease toolchain directives, and never lowers the effective selected toolchain. It explicitly dispatches dzdeploy.yml on the PR branch to ensure unattended validation; token-created PR events can require workflow approval. See [GitHub's workflow-trigger guidance](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow#triggering-a-workflow-from-a-workflow). It also dispatches release.yml when that workflow exists. Go updates always require review; changed modernization or analysis baselines remain reviewable failures.

Repository prerequisites are deliberately not changed by these workflows:

- Actions must be allowed to create pull requests for the Go updater to open its PR. The job requests only the needed contents, pull-requests, and actions write permissions. If the repository disallows Actions-created PRs, an administrator must enable that capability before the updater can complete.
- Dependabot security-update availability depends on the repository's Dependabot settings. The file groups those updates when available; it does not enable repository administration settings.
- Dependabot auto-merge is disabled unless an administrator sets the repository variable DEPENDABOT_AUTO_MERGE to true and enables repository auto-merge. The workflow also verifies a classic main branch protection rule that requires status checks, an up-to-date branch, and both CI and the release workflow's validate context. Missing/unreadable protection, ruleset-only protection, or disabled auto-merge leaves the PR for manual review. Configure and verify these protections before opting in.
- The privileged bot workflow never checks out or executes PR code. Verified Dependabot-authored same-repository minor/patch updates alone are eligible; gh pr merge uses auto-merge and the exact head SHA. Major updates and ordinary contributors receive no automatic merge action.

## Reference adaptation

This setup was compared with [tradeview-go at 0c111167](https://github.com/jsirianni/tradeview-go/tree/0c111167e729579513a5a44864c5998b40133636). Its pinned format/import, Staticcheck, Revive, strict error, security, vulnerability, modernization, coverage-regression, negative-fixture, bounded-fuzz, scheduled CI, grouped dependency, protected bot-merge, and reviewed Go-update mechanisms are carried over with portable wrappers and dzdeploy's platform/integration requirements.

OpenAPI regeneration consistency, generated-binding coverage categories, generator publication checks, market-stream benchmarks/fuzzers, generator-specific dependency ceilings, and OpenTelemetry update groups have no counterpart here. dzdeploy's actual parser targets and per-package native coverage replace those source-specific checks. The configuration repository's omitted server-tree baseline remains omitted; this tooling PR adds no game configuration and authorizes no deployment or restart.
