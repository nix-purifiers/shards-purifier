# SPDX-License-Identifier: MIT
{ shards }:
shards.overrideAttrs (old: {
  # Upstream fixes shard.lock to the working directory. Keep native commands
  # and cwd semantics while selecting an external lock without rewriting it.
  # A scoped offline flag also covers compiler/server subprocesses without
  # appending SHARDS_OPTS after a user's `shards run ... -- ARGS` separator.
  postPatch = (old.postPatch or "") + ''
    substituteInPlace src/commands/command.cr \
      --replace-fail '@lockfile_path = File.join(@path, LOCK_FILENAME)' \
        '@lockfile_path = ENV["SHARDS_PURIFIER_NATIVE_LOCKFILE"]? || File.join(@path, LOCK_FILENAME)' \
      --replace-fail 'Shards::Lock.write(packages, override_path, LOCK_FILENAME)' \
        'Shards::Lock.write(packages, override_path, lockfile_path)'
    substituteInPlace src/config.cr \
      --replace-fail 'class_property? frozen = false' \
        'class_property? frozen : Bool = (ENV["SHARDS_PURIFIER_OFFLINE"]? == "1")' \
      --replace-fail 'class_property? local = false' \
        'class_property? local : Bool = (ENV["SHARDS_PURIFIER_OFFLINE"]? == "1")'
  '';
})
