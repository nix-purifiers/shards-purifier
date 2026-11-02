# SPDX-License-Identifier: MIT
{
  lib,
  runCommand,
  fetchgit,
  python3,
  writeText,
  nativeShards,
  crystal,
  toolchain,
  purifier,
  gnutar,
  gzip,
}:
{
  src,
  lockFile ? src + "/shards-purifier.lock.json",
  shardLock ? src + "/shard.lock",
  fetchers ? { },
  buildTargets ? null,
  test ? true,
  nativeBuildInputs ? [ ],
  srcFilter ?
    path: type:
    !(builtins.elem (baseNameOf path) [
      ".git"
      ".shards-purifier"
      "lib"
      "bin"
      "result"
      "__pycache__"
    ]),
}:
let
  lock = purifier.checkLock (
    import ./read-lock.nix { inherit lib; } { inherit src lockFile shardLock; }
  );
  environment = import ./environment.nix {
    inherit
      lib
      runCommand
      fetchgit
      python3
      writeText
      nativeShards
      crystal
      toolchain
      purifier
      ;
  } { inherit lock fetchers; };
  source = lib.cleanSourceWith {
    inherit src;
    filter = srcFilter;
  };
  targets = if buildTargets == null then lock.data.targets else buildTargets;
  project =
    runCommand "purified-shards-project"
      {
        nativeBuildInputs = [
          toolchain
          python3
        ]
        ++ nativeBuildInputs;
      }
      ''
        export HOME="$TMPDIR/home" XDG_CACHE_HOME="$TMPDIR/xdg"
        export CRYSTAL=${crystal}/bin/crystal CRYSTAL_CACHE_DIR="$TMPDIR/crystal-cache"
        export SOURCE_DATE_EPOCH=1 GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_NOSYSTEM=1
        export SHARDS_INSTALL_PATH=${environment}/lib
        export SHARDS_CACHE_PATH="$TMPDIR/git-cache"
        export SHARDS_BIN_PATH="$out/bin"
        export SHARDS_PURIFIER_OFFLINE=1
        export CRYSTAL_PATH="${environment}/lib"
        unset SHARDS_OPTS SHARDS_OVERRIDE CRYSTAL_VERSION
        mkdir -p "$HOME" "$out/bin" project
        cp -r ${source}/. project/
        chmod -R u+w project
        cd project
        cp ${shardLock} shard.lock
        export SHARDS_PURIFIER_NATIVE_LOCKFILE="$PWD/shard.lock"
        ${lib.optionalString (targets != [ ]) (
          "${nativeShards}/bin/shards --frozen --local build " + lib.escapeShellArgs targets
        )}
        ${lib.optionalString test "if [ -d spec ]; then ${crystal}/bin/crystal spec; fi"}
        mkdir -p "$out/share/shards"
        cp -r . "$out/share/shards/"
        ln -s ${environment}/lib "$out/share/shards/lib"
      '';
  release =
    assert lock.problems == [ ];
    runCommand "shards-project-release"
      {
        nativeBuildInputs = [
          gnutar
          gzip
        ];
      }
      ''
        mkdir source "$out"
        cp -r ${source}/. source/
        chmod -R u+w source
        cp ${lockFile} source/shards-purifier.lock.json
        cp ${shardLock} source/shard.lock
        tar --sort=name --mtime=@1 --owner=0 --group=0 --numeric-owner -C source -cf - . | gzip -n > "$out/project.tar.gz"
      '';
in
{
  packages = {
    inherit project environment;
    default = project;
  };
  tests = project;
  inherit release;
  fetches = lock.entries;
}
