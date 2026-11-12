# SPDX-License-Identifier: MIT
{
  project,
  lockFile,
  shardLock,
  target,
}:
let
  pkgs = import (/. + "@nixpkgs@") { };
  purifier = import (/. + "@purifier@/nix/lib") { inherit (pkgs) lib; };
  nativeCrystalline = pkgs.callPackage ./crystalline.nix { };
  nativeShards = pkgs.callPackage ./shards.nix { };
  toolchain = pkgs.buildEnv {
    name = "shards-purifier-toolchain";
    paths = [
      pkgs.crystal
      nativeCrystalline
      nativeShards
      pkgs.git
      pkgs.stdenv.cc
      pkgs.pkg-config
      pkgs.gnumake
      pkgs.cmake
      pkgs.ninja
      pkgs.coreutils
      pkgs.findutils
      pkgs.gnused
      pkgs.gnugrep
      pkgs.bash
      pkgs.patch
    ];
  };
  args = {
    src = /. + project;
    lockFile = /. + lockFile;
    shardLock = /. + shardLock;
  };
  lock = import ../lib-overlays/default/read-lock.nix { inherit (pkgs) lib; } args;
in
if target == "environment" then
  pkgs.callPackage ../pkgs/build-shards-project/environment.nix { inherit purifier nativeShards toolchain; } { inherit lock; }
else if target == "runtime" then
  pkgs.runCommand "shards-purifier-runtime" { } ''ln -s @runtime@ "$out"''
else if target == "release" then
  (pkgs.callPackage ../pkgs/build-shards-project/default.nix { inherit purifier nativeShards toolchain; } args).release
else
  throw "shards-purifier: unknown realization target ${target}"
