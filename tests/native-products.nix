{
  pkgs,
  src ? ./fixtures/native,
  expected ? 41,
}:
let
  built = pkgs.shards-purifier.buildShardsProject {
    inherit src;
    nativeLibraries.answer = {
      source = "src/native.cr";
      header = "native-answer.h";
      initialize = "answer_init";
      exports = [
        "answer_init"
        "native_answer"
        "answer_collect"
      ];
    };
  };
  producer = built.packages.project;
  projection = built.projections.native;
  python = pkgs.python3.withPackages (p: [ p.cffi ]);
in
pkgs.runCommand "crystal-native-abi-consumers"
  {
    nativeBuildInputs = [
      python
      pkgs.gcc
      pkgs.jdk21
    ];
    passthru = { inherit built producer projection; };
  }
  ''
    mkdir "$out"
    test "$(${producer}/bin/hello)" = 'Locked Crystal dependencies'
    cc ${./native-consumer.c} -DEXPECTED=${toString expected} \
      -I${producer}/include/answer ${producer}/lib/libanswer.so -o consume
    ./consume
    python ${./native-consumers.py} ${projection} ${toString expected}
    cp ${./NativeAnswer.java} NativeAnswer.java
    javac --enable-preview --release 21 NativeAnswer.java
    java @${built.projections.java-ffi}/java.args --enable-preview --enable-native-access=ALL-UNNAMED NativeAnswer ${toString expected}
    cp ${producer}/nix-support/crystal-native/verified-libraries.json "$out/"
  ''
