# SPDX-License-Identifier: MIT
{
  description = "Locked, Nix-resolved dependencies for Crystal Shards";
  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  inputs.purifier = {
    url = "github:nix-purifiers/purifier";
    flake = false;
  };
  outputs =
    {
      self,
      nixpkgs,
      purifier,
    }:
    let
      systems = [
        "x86_64-linux"
        "aarch64-linux"
      ];
      forAll = nixpkgs.lib.genAttrs systems;
      shared = lib: import (purifier + "/nix/lib") { inherit lib; };
      overlay = final: prev: {
        shards-purifier = final.lib.makeScope final.newScope (scope: {
          nativeCrystalline = scope.callPackage ./nix/crystalline.nix { };
          nativeShards = scope.callPackage ./nix/shards.nix { };
          toolchain = final.buildEnv {
            name = "shards-purifier-toolchain";
            paths = [
              final.crystal
              scope.nativeCrystalline
              scope.nativeShards
              final.git
              final.stdenv.cc
              final.pkg-config
              final.gnumake
              final.cmake
              final.ninja
              final.coreutils
              final.findutils
              final.gnused
              final.gnugrep
              final.bash
              final.patch
            ];
          };
          cli = scope.callPackage ./nix/cli.nix {
            nixpkgsSrc = nixpkgs;
            purifierSrc = purifier;
          };
          buildShardsProject = scope.callPackage ./nix/build-project.nix { purifier = shared final.lib; };
        });
      };
      pkgsFor =
        system:
        import nixpkgs {
          inherit system;
          overlays = [ overlay ];
        };
    in
    {
      overlays.default = overlay;
      lib.shards-purifier.readLock = import ./nix/read-lock.nix { lib = nixpkgs.lib; };
      packages = forAll (system: {
        default = (pkgsFor system).shards-purifier.cli;
        cli = self.packages.${system}.default;
      });
      apps = forAll (system: {
        default = {
          type = "app";
          program = "${self.packages.${system}.default}/bin/shards-purifier";
          meta.description = "Lock and prefetch Crystal Shards dependencies";
        };
      });
      formatter = forAll (system: (pkgsFor system).nixfmt-tree);
      checks = forAll (
        system:
        import ./tests {
          pkgs = pkgsFor system;
          inherit self;
        }
      );
    };
}
