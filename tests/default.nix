# SPDX-License-Identifier: MIT
{ pkgs, self }:
let
  project = pkgs.shards-purifier.buildShardsProject { src = ../examples/minimal; };
in
{
  cli = self.packages.${pkgs.stdenv.hostPlatform.system}.default;
  environment = project.packages.environment;
  project = project.tests;
  release = project.release;
  editor = import ./editor.nix {
    inherit pkgs;
    environment = project.packages.environment;
  };
}
