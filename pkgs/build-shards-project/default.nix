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
  binutils,
  stdenv,
}:
{
  src,
  lockFile ? src + "/shards-purifier.lock.json",
  shardLock ? src + "/shard.lock",
  fetchers ? { },
  buildTargets ? null,
  test ? true,
  nativeLibraries ? { },
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
    import ../../lib-overlays/default/read-lock.nix { inherit lib; } { inherit src lockFile shardLock; }
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
  relative =
    value:
    builtins.isString value
    && value != ""
    && !lib.hasPrefix "/" value
    && builtins.all (
      part:
      !(builtins.elem part [
        ""
        "."
        ".."
      ])
    ) (lib.splitString "/" value);
  symbol = value: builtins.isString value && builtins.match "[A-Za-z_][A-Za-z0-9_]*" value != null;
  validNative =
    name: spec:
    symbol name
    && builtins.isAttrs spec
    &&
      builtins.attrNames (
        removeAttrs spec [
          "source"
          "header"
          "exports"
          "initialize"
          "defines"
        ]
      ) == [ ]
    && relative (spec.source or null)
    && lib.hasSuffix ".cr" spec.source
    && relative (spec.header or null)
    && symbol (spec.initialize or null)
    && builtins.isList (spec.exports or null)
    && spec.exports != [ ]
    && lib.all symbol spec.exports
    && builtins.elem spec.initialize spec.exports
    && builtins.isList (spec.defines or [ ])
    && lib.all symbol (spec.defines or [ ]);
  nativeSpecifications = writeText "crystal-native-libraries.json" (builtins.toJSON nativeLibraries);
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
        ${lib.optionalString (nativeLibraries != { }) ''
          python3 ${./native-products.py} "$PWD" "$out" ${source} ${environment} \
            ${crystal}/bin/crystal ${binutils}/bin/nm ${stdenv.hostPlatform.system} ${nativeSpecifications} \
            ${stdenv.cc}/bin/cc ${lib.getBin stdenv.cc.libc}/bin/ldd
        ''}
        mkdir -p "$out/share/shards"
        cp -r . "$out/share/shards/"
        ln -s ${environment}/lib "$out/share/shards/lib"
      '';
  projections = lib.optionalAttrs (nativeLibraries != { }) (
    purifier.nativeProjections {
      producer = project;
      libraries = lib.mapAttrs (name: _: "lib/lib${name}.so") nativeLibraries;
      includeDirectories = lib.mapAttrsToList (name: _: "include/${name}") nativeLibraries;
      targetMetadata = lib.mapAttrs (_: spec: {
        abi = "c";
        inherit (spec) source exports initialize;
        toolVersions = lock.data.toolVersions;
        runtimeContract = "Caller-authored initialization; same native thread; process-lifetime load";
      }) nativeLibraries;
      system = stdenv.hostPlatform.system;
      inherit runCommand python3;
    }
  );
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
assert lib.assertMsg
  (lib.all (name: validNative name nativeLibraries.${name}) (builtins.attrNames nativeLibraries))
  "Crystal native libraries require source, authored header, exports including initialize, and optional defines";
assert lib.assertMsg (
  nativeLibraries == { }
  || (
    lock.data.toolVersions.crystal == crystal.version
    && lock.data.toolVersions.shards == nativeShards.version
  )
) "Crystal native SDK changed; run shards-purifier lock --update";
{
  packages = {
    inherit project environment;
    default = project;
  };
  tests = project;
  inherit release projections;
  fetches = lock.entries;
}
