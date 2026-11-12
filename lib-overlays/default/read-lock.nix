# SPDX-License-Identifier: MIT
{ lib }:
{
  src,
  lockFile ? src + "/shards-purifier.lock.json",
  shardLock ? src + "/shard.lock",
}:
let
  fix = message: "shards-purifier: ${message}; run shards-purifier lock";
  exists = builtins.pathExists lockFile && builtins.pathExists shardLock;
  raw =
    if exists then
      builtins.addErrorContext (fix "invalid companion JSON") (
        builtins.fromJSON (builtins.readFile lockFile)
      )
    else
      { };
  data = if builtins.isAttrs raw then raw else { };
  native = if exists then builtins.readFile shardLock else "";
  nameOK = value: builtins.isString value && builtins.match "[A-Za-z0-9][A-Za-z0-9_-]*" value != null;
  pathOK =
    value:
    builtins.isString value
    && value != ""
    && !lib.hasPrefix "/" value
    && !lib.hasInfix "\\" value
    && builtins.all (
      p:
      !(builtins.elem p [
        ""
        "."
        ".."
      ])
    ) (lib.splitString "/" value);
  hex =
    length: value:
    builtins.isString value && builtins.match "[0-9a-f]{${toString length}}" value != null;
  urlOK =
    value: builtins.isString value && builtins.match "(https?|git|file)://[^[:space:]@]+" value != null;
  b64 =
    value:
    builtins.isString value
    && builtins.match "([A-Za-z0-9+/]{4})*([A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?" value != null;
  linkOK = link: builtins.isAttrs link && pathOK (link.path or null) && hex 40 (link.rev or null);
  aliasOK =
    value:
    builtins.isString value
    && builtins.match "refs/(heads|tags)/[A-Za-z0-9_.+/-]+" value != null
    && !lib.hasInfix ".." value;
  dependencyOK =
    dep:
    builtins.isAttrs dep
    && nameOK (dep.name or null)
    && pathOK (dep.cachePath or null)
    && builtins.isString (dep.hash or null)
    && builtins.match "sha256-[A-Za-z0-9+/]{43}=" dep.hash != null
    && builtins.isList (dep.aliases or null)
    && builtins.all aliasOK dep.aliases
    && builtins.isAttrs (dep.git or null)
    && urlOK (dep.git.url or null)
    && hex 40 (dep.git.rev or null)
    && (dep.git.leaveDotGit or null) == true
    && (dep.git.submodules or null) == false
    && builtins.isAttrs (dep.git.commitObject or null)
    && b64 (dep.git.commitObject.object or null)
    && builtins.isList (dep.git.commitObject.gitlinks or null)
    && builtins.all linkOK dep.git.commitObject.gitlinks
    && builtins.isString (dep.version or null)
    && lib.hasSuffix "+git.commit.${dep.git.rev}" dep.version;
  dependencies = data.dependencies or null;
  inputNames = [
    "shard.yml"
    "shard.override.yml"
  ];
  inputs = map (path: {
    inherit path;
    hash =
      if builtins.pathExists (src + "/${path}") then
        builtins.hashFile "sha256" (src + "/${path}")
      else
        null;
  }) inputNames;
  expectedNative =
    "version: \"2.0\"\nshards:"
    + (
      if dependencies == [ ] then
        " {}\n"
      else
        "\n"
        + lib.concatMapStrings (
          dep:
          "  ${builtins.toJSON dep.name}:\n    git: ${builtins.toJSON dep.git.url}\n    version: ${builtins.toJSON dep.version}\n"
        ) dependencies
    );
  problems =
    if !exists then
      [ (fix "missing native or companion lock") ]
    else if !builtins.pathExists (src + "/shard.yml") then
      [ (fix "missing native manifest") ]
    else if !builtins.isAttrs raw || (data.version or null) != 1 then
      [ (fix "unsupported companion format") ]
    else if
      (data.contentHash or null)
      != builtins.hashString "sha256" (builtins.toJSON (removeAttrs data [ "contentHash" ]))
    then
      [ (fix "companion contentHash mismatch") ]
    else if (data.inputs or null) != inputs then
      [ (fix "project manifests changed") ]
    else if
      !builtins.isString (data.manifest or null)
      || data.manifest != builtins.readFile (src + "/shard.yml")
    then
      [ (fix "invalid native manifest snapshot") ]
    else if !builtins.isList dependencies || !builtins.all dependencyOK dependencies then
      [ (fix "invalid native Git source export") ]
    else if
      map (d: d.name) dependencies
      != builtins.sort builtins.lessThan (lib.unique (map (d: d.name) dependencies))
    then
      [ (fix "duplicate or unordered native dependencies") ]
    else if
      (data.nativeLock or null) != native
      || (data.nativeHash or null) != builtins.hashString "sha256" native
      || native != expectedNative
    then
      [ (fix "native pins do not match source export") ]
    else if !builtins.isList (data.targets or null) || !builtins.all nameOK data.targets then
      [ (fix "invalid native application targets") ]
    else
      [ ];
in
{
  purifier = "shards-purifier";
  inherit problems data;
  entries =
    if problems != [ ] then
      [ ]
    else
      map (dep: {
        path = "sources/${dep.name}";
        inherit (dep) git hash;
      }) dependencies;
  outputs =
    if problems != [ ] then
      { }
    else
      {
        project = { };
        environment = { };
      };
}
