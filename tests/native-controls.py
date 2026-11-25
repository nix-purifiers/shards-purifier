"""Exercise native compiler and physical ownership rejection paths."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

repo = Path(__file__).resolve().parents[1]
override = []
if source := os.environ.get("SHARDS_TEST_CORE_SOURCE"):
    override = ["--override-input", "purifier", "path:" + source, "--no-write-lock-file"]
system = subprocess.check_output(["nix", "eval", "--impure", "--raw", "--expr", "builtins.currentSystem"], text=True).strip()
attribute = ".#checks." + system + ".native"
subprocess.run(["nix", "build", attribute, "--no-link", *override], cwd=repo, check=True)
producer = Path(subprocess.check_output(["nix", "eval", attribute + ".producer.outPath", "--raw", *override], cwd=repo, text=True).strip())
proof = json.loads((producer / "nix-support/crystal-native/verified-libraries.json").read_text())
tools = proof["nativeTools"]
expected = {
    "missing-export": "Missing callable authored native export",
    "header-export": "Authored header/export mismatch",
    "foreign-header": "Foreign authored native input",
    "foreign-require": "Foreign native require graph owner",
    "shadowed-prelude": "Shadowed original Crystal runtime require",
    "wrong-compiler": "Foreign native Crystal compiler",
}
for case, message in expected.items():
    with tempfile.TemporaryDirectory(prefix="crystal-native-control-") as temporary:
        root = Path(temporary)
        original, staged = root / "original", root / "project"
        shutil.copytree(repo / "tests/fixtures/native", original)
        shutil.copytree(original, staged)
        spec = json.loads(json.dumps(proof["libraries"]["answer"]["specification"]))
        environment = Path(proof["dependencyEnvironment"])
        selected_compiler = tools["compilerExecutable"]
        if case == "missing-export":
            spec["exports"].append("missing_native_export")
            for folder in (original, staged):
                with (folder / spec["header"]).open("a") as stream:
                    stream.write("void missing_native_export(void);\n")
        elif case == "header-export":
            for folder in (original, staged):
                header = folder / spec["header"]
                header.write_text(header.read_text().replace("uint32_t native_answer(uint32_t value);\n", ""))
        elif case == "foreign-header":
            foreign = root / "foreign.h"
            foreign.write_bytes((staged / spec["header"]).read_bytes())
            (staged / spec["header"]).unlink()
            (staged / spec["header"]).symlink_to(foreign)
        elif case == "foreign-require":
            foreign = root / "foreign.cr"
            foreign.write_text("module ForeignOwned; end\n")
            for folder in (original, staged):
                source = folder / spec["source"]
                source.write_text("require " + json.dumps(str(foreign)) + "\n" + source.read_text())
        elif case == "shadowed-prelude":
            copied = root / "environment"
            shutil.copytree(environment, copied, symlinks=True)
            (copied / "lib").chmod(0o755)
            shutil.copyfile(Path(proof["sdkRoots"][0]) / "prelude.cr", copied / "lib/prelude.cr")
            environment = copied
        else:
            selected_compiler = tools["cc"]
        specifications = root / "specifications.json"
        specifications.write_text(json.dumps({"answer": spec}))
        env = dict(os.environ, CRYSTAL_PATH=str(environment / "lib"),
                   CRYSTAL_CACHE_DIR=str(root / "cache"),
                   PATH=str(Path(tools["cc"]).parent) + os.pathsep + os.environ["PATH"])
        command = [sys.executable, str(repo / "pkgs/build-shards-project/native-products.py"),
                   str(staged), str(root / "output"), str(original), str(environment),
                   proof["nativeCompilerPath"], tools["nm"], system, str(specifications),
                   tools["cc"], tools["ldd"], proof["sdkRoots"][0], selected_compiler, proof["selectedGcRoot"]]
        result = subprocess.run(command, cwd=staged, env=env, capture_output=True, text=True)
        assert result.returncode != 0 and message in result.stderr, (case, result.returncode, result.stdout, result.stderr)
        print(json.dumps({"case": case, "nativeExit": result.returncode, "diagnostic": message}), flush=True)
