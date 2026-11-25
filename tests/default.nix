# SPDX-License-Identifier: MIT
{ pkgs, self }:
let
  project = pkgs.shards-purifier.buildShardsProject { src = ../examples/minimal; };
in
{
  native = import ./native-products.nix { inherit pkgs; };
  native-revision = import ./native-products.nix {
    inherit pkgs;
    src = ./fixtures/native-revision;
    expected = 42;
  };
  cli = self.packages.${pkgs.stdenv.hostPlatform.system}.default;
  environment = project.packages.environment;
  project = project.tests;
  release = project.release;
  editor = import ./editor.nix {
    inherit pkgs;
    environment = project.packages.environment;
  };
}
