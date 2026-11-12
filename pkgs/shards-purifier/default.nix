# SPDX-License-Identifier: MIT
{
  lib,
  stdenvNoCC,
  makeWrapper,
  python3,
  nix,
  gh,
  crystal,
  nativeShards,
  nativeCrystalline,
  toolchain,
  cacert,
  nixpkgsSrc,
  purifierSrc,
}:
let
  python = python3.withPackages (p: [ p.pyyaml ]);
in
stdenvNoCC.mkDerivation {
  pname = "shards-purifier";
  version = "0.1.0";
  src = ../..;
  nativeBuildInputs = [ makeWrapper ];
  dontBuild = true;
  installPhase = ''
    mkdir -p "$out/bin" "$out/lib/shards-purifier"
    cp -r shards_purifier nix lib-overlays pkgs "$out/lib/shards-purifier/"
    install -m755 bin/shards-purifier "$out/bin/shards-purifier"
    substituteInPlace "$out/lib/shards-purifier/nix/realize.nix" \
      --replace-fail '@nixpkgs@' '${nixpkgsSrc}' \
      --replace-fail '@purifier@' '${purifierSrc}' \
      --replace-fail '@runtime@' "$out"
    wrapProgram "$out/bin/shards-purifier" \
      --prefix PATH : ${
        lib.makeBinPath [
          python
          nix
          gh
          toolchain
        ]
      } \
      --set-default SSL_CERT_FILE ${cacert}/etc/ssl/certs/ca-bundle.crt \
      --set SHARDS_PURIFIER_SHARDS ${nativeShards}/bin/shards \
      --set SHARDS_PURIFIER_CRYSTAL ${crystal}/bin/crystal \
      --set SHARDS_PURIFIER_CRYSTALLINE ${nativeCrystalline}/bin/crystalline \
      --set SHARDS_PURIFIER_TOOLCHAIN ${toolchain} \
      --set SHARDS_PURIFIER_SHARDS_VERSION ${nativeShards.version} \
      --set SHARDS_PURIFIER_CRYSTAL_VERSION ${crystal.version}
    for tool in shards crystal crystalline; do
      makeWrapper "$out/bin/shards-purifier" "$out/bin/$tool" --add-flags "native $tool --"
    done
    for program in ${toolchain}/bin/*; do
      name=$(basename "$program")
      if [ ! -e "$out/bin/$name" ]; then ln -s "$program" "$out/bin/$name"; fi
    done
  '';
  meta = {
    description = "Native Crystal Shards workflow with locked Nix-resolved dependencies";
    homepage = "https://nix-purifiers.github.io/";
    license = lib.licenses.mit;
    platforms = [
      "x86_64-linux"
      "aarch64-linux"
    ];
    mainProgram = "shards-purifier";
  };
}
