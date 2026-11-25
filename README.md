# shards-purifier

Locked, Nix-resolved dependencies for Crystal's Shards.

## Native C ABI libraries

Opt in to compiling a caller-authored C ABI entry point with the selected Crystal
compiler and the project's existing locked Shards dependency environment:

```nix
let built = pkgs.shards-purifier.buildShardsProject {
  src = ./.;
  nativeLibraries.answer = {
    source = "src/native.cr";
    header = "native-answer.h";
    initialize = "answer_init";
    exports = [ "answer_init" "native_answer" ];
    # defines = [ "my_feature" ];
  };
}; in built.projections.python-ffi
```

The builder preserves normal Shards application targets and tests, then compiles
`lib/libanswer.so` with the original compiler's `--single-module` and shared-link
options. It installs the unchanged authored header in `include/answer` and exposes
`projections.native`, `projections.python-ffi`, and `projections.java-ffi`. The native
catalog retains the source, export, initializer, and captured tool-version metadata.

The compiler's own dependency tool runs with the same defines and reports its
require graph, including the standard library (which it normally filters out).
Required files must belong to the staged project, locked dependency environment,
or selected native standard library. The builder retains their hashes, compiler
identity, original and post-build input hashes, dynamic symbols, and resolved
runtime library paths and hashes in `nix-support/crystal-native`. It checks the
original runtime/prelude origins, native architecture, callable exports, header
export declarations, and installed header bytes. The header's ABI types and any
foreign-code behavior remain the application's responsibility.

The caller must initialize the runtime exactly once before calling allocating
exports, on the same native thread used for subsequent calls, and keep the library
loaded for the process lifetime. The authored initializer can use the original
`GC.init`, `Crystal.init_runtime`, and `Crystal.main_user_code(argc, argv)` routines.
Do not let Crystal exceptions cross the C boundary. This interface does not transfer
Crystal objects across the boundary: use caller-owned scalar/buffer interfaces and
explicit ownership rules for any application-defined allocations. No arbitrary
foreign-thread, unload/reload, or universal Crystal embedding guarantee is implied.

The native examples exercise actual `DB::Error` allocations from the locked shard,
forced GC, and C/Python ctypes-CFFI/JDK21 FFM consumers across two source revisions.

## Quickstart

From a project with `shard.yml`:

```sh
nix shell 'github:nix-purifiers/shards-purifier'
shards-purifier lock
shards-purifier prefetch
shards build
crystal spec
```

The shell supplies wrappers for `shards`, `crystal` and `crystalline`.
They use a private dependency directory under `.shards-purifier/`, leaving
an existing `lib/` alone. Start your editor from this shell to use the
prepared dependencies with Crystalline. No generated devshell is needed.
You can install these wrappers through your usual Nix configuration.

Without a companion lockfile, wrappers warn and run the ordinary, impure
tool. Invalid or stale locks fail with a repair instruction.

Commit `shard.lock` and `shards-purifier.lock.json`. Ignore
`.shards-purifier/` and generated `bin/` files.

## Lock and update

```sh
shards-purifier lock
shards-purifier update db
shards-purifier update
```

Shards resolves the graph. The companion records exact Git commits,
source hashes and the native cache layout. Semantic version selections
use Shards' native `+git.commit.` lock syntax, retaining the exact revision
when a tag moves. `lock` retains valid selections; `update NAME` asks
Shards to update that dependency, and `update` updates the graph.

`prefetch` realizes dependencies with Nix, executes native installation
and postinstall hooks in the sandbox, and roots the environment and SDK.
Builds, tests and editor commands run in your working tree. Native hooks
must work offline from their declared inputs.

Use the helper for dependency changes. Guarded `shards update`, `lock`,
`init`, `prune` and `outdated` commands are rejected rather than changing
the sealed graph.

## External locks

```sh
shards-purifier \
  --project ./app \
  --lockfile ./locks/companion.json \
  --tool-lockfile ./locks/shard.lock \
  lock

export SHARDS_PURIFIER_LOCKFILE="$PWD/locks/companion.json"
export SHARDS_PURIFIER_TOOL_LOCKFILE="$PWD/locks/shard.lock"
cd app
shards build
```

The selected native lock is read directly by the scoped Shards SDK.
The working tree's `shard.lock` is not rewritten by guarded commands.
`--native-lock` and `SHARDS_PURIFIER_NATIVE_LOCKFILE` are equivalent
native-lock selectors.

## Nix builds

The overlay exposes `pkgs.shards-purifier.buildShardsProject`:

```nix
pkgs.shards-purifier.buildShardsProject {
  src = ./.;
}
```

It returns `packages`, `tests`, `release` and `fetches`.
`packages.project` builds native targets and runs specs;
`packages.environment` supplies prepared dependencies. Output names and
fetch declarations are available during evaluation without building.
`lockFile` and `shardLock` select external locks; `buildTargets` selects
native targets, and `test = false` skips specs.

## Releases

```sh
shards-purifier publish \
  --repo OWNER/REPOSITORY \
  --tag v0.1.0
```

This publishes a deterministic Nix-built source archive containing both
locks. It creates a GitHub release or replaces the archive on an existing
release. Authentication uses the ordinary `gh` configuration.

## Scope

Supports native Git shards over public HTTP(S) and Git transports,
including GitHub shorthand, development dependencies and native targets.
Path dependencies, dependency overrides and Git submodules are not yet
supported. Private credentials are not captured. Postinstall downloads
or undeclared external tools fail during sandboxed prefetch.

The SDK currently targets x86_64-linux and aarch64-linux.

## Credits

The purifier idea was inspired by nixcloud's
[cargo (libnix)](https://github.com/nixcloud/cargo).
