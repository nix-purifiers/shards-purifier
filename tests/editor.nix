# SPDX-License-Identifier: MIT
{ pkgs, environment }:
pkgs.runCommand "shards-editor-check"
  {
    nativeBuildInputs = [
      pkgs.shards-purifier.toolchain
      pkgs.python3
    ];
  }
  ''
    export HOME="$TMPDIR/home" XDG_CACHE_HOME="$TMPDIR/xdg"
    export CRYSTAL_CACHE_DIR="$TMPDIR/compiler-cache"
    export CRYSTAL=${pkgs.crystal}/bin/crystal
    export SHARDS_PURIFIER_OFFLINE=1
    export SHARDS_CACHE_PATH="$TMPDIR/git-cache"
    export SHARDS_INSTALL_PATH="$TMPDIR/lib"
    export CRYSTAL_PATH="$SHARDS_INSTALL_PATH"
    export GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_NOSYSTEM=1
    mkdir -p "$HOME" project
    cp -r ${../examples/minimal}/. project/
    chmod -R u+w project
    cp -r ${environment}/lib "$SHARDS_INSTALL_PATH"
    chmod -R u+w "$SHARDS_INSTALL_PATH"
    python3 ${../shards_purifier/prepare.py} ${environment}/metadata.json ${environment}/sources "$SHARDS_CACHE_PATH"
    export SHARDS_PURIFIER_NATIVE_LOCKFILE="$PWD/project/shard.lock"
    python3 ${./editor.py} "$PWD/project" ${pkgs.shards-purifier.nativeCrystalline}/bin/crystalline
    touch "$out"
  ''
