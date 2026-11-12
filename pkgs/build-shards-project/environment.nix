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
}:
{
  lock,
  fetchers ? { },
}:
let
  checked = purifier.checkLock lock;
  sources = purifier.tree (
    {
      name = "locked-shards-sources";
      entries = checked.entries;
      inherit
        runCommand
        fetchgit
        python3
        writeText
        ;
    }
    // fetchers
  );
  metadata = writeText "shards-source-metadata.json" (builtins.toJSON checked.data);
  manifest = writeText "shard.yml" checked.data.manifest;
  nativeLock = writeText "shard.lock" checked.data.nativeLock;
in
runCommand "purified-shards-environment"
  {
    nativeBuildInputs = [
      toolchain
      python3
    ];
  }
  ''
    export HOME="$TMPDIR/home" XDG_CACHE_HOME="$TMPDIR/xdg"
    export CRYSTAL_CACHE_DIR="$TMPDIR/crystal-cache"
    export CRYSTAL=${crystal}/bin/crystal
    export SOURCE_DATE_EPOCH=1
    export GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_NOSYSTEM=1
    export SHARDS_CACHE_PATH="$TMPDIR/git-cache"
    export SHARDS_INSTALL_PATH="$out/lib"
    export SHARDS_BIN_PATH="$out/bin"
    export SHARDS_PURIFIER_OFFLINE=1
    unset SHARDS_OPTS SHARDS_OVERRIDE CRYSTAL_VERSION
    mkdir -p "$HOME" "$out/lib" "$out/bin" project
    ln -s ${sources}/sources "$out/sources"
    ln -s ${metadata} "$out/metadata.json"
    python3 ${../../shards_purifier/prepare.py} ${metadata} ${sources}/sources "$SHARDS_CACHE_PATH"
    cd project
    cp ${manifest} shard.yml
    cp ${nativeLock} shard.lock
    export SHARDS_PURIFIER_NATIVE_LOCKFILE="$PWD/shard.lock"
    ${nativeShards}/bin/shards --local --frozen install
    ${nativeShards}/bin/shards --local --frozen check
  ''
