# SPDX-License-Identifier: MIT
{ crystalline }:
crystalline.overrideAttrs (old: {
  postPatch = (old.postPatch or "") + ''
    substituteInPlace src/crystalline/project.cr \
      --replace-fail 'Path[@root_uri.decoded_path, "lib"].to_s' \
        '(ENV["SHARDS_INSTALL_PATH"]? || Path[@root_uri.decoded_path, "lib"].to_s)' \
      --replace-fail 'lib_dir = Path[root, "lib"]' \
        'lib_dir = Path[ENV["SHARDS_INSTALL_PATH"]? || Path[root, "lib"].to_s]'
  '';
})
