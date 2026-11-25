"""Build caller-authored C ABI libraries with the selected native Crystal SDK."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(command):
    return subprocess.check_output(list(map(str, command)), text=True)


project, output, original, environment = map(Path, sys.argv[1:5])
compiler, nm, system, specifications, cc, ldd, selected_stdlib, selected_compiler, selected_gc = sys.argv[5:]
project, output, original, environment = (
    path.resolve() for path in (project, output, original, environment)
)
specs = json.loads(Path(specifications).read_text())
native_path = run([compiler, "env", "CRYSTAL_PATH"]).strip().split(os.pathsep)
sdk_roots = [Path(selected_stdlib).resolve(strict=True)]
reported_sdk_roots = [Path(path).resolve() for path in native_path
                      if path and Path(path).is_absolute() and not Path(path).resolve().is_relative_to(environment)]
assert reported_sdk_roots == sdk_roots, "Native compiler reported a foreign standard library"
assert sdk_roots and all(str(path).startswith("/nix/store/") for path in sdk_roots), "Unowned Crystal standard library"
native_library_roots = [Path(path).resolve() for path in run([compiler, "env", "CRYSTAL_LIBRARY_PATH"]).strip().split(os.pathsep) if path]
dependency_roots = [environment]
for folder in (environment / "lib", environment / "sources"):
    if folder.is_dir():
        dependency_roots.extend(path.resolve() for path in folder.iterdir() if path.is_dir())
compiler_exec = Path(run([compiler, "env", "CRYSTAL_EXEC_PATH"]).strip()) / "crystal"
assert compiler_exec.is_file(), "Missing selected native Crystal compiler"
assert compiler_exec.resolve() == Path(selected_compiler).resolve(strict=True), "Foreign native Crystal compiler"
support = output / "nix-support/crystal-native"
support.mkdir(parents=True)
records = {}
for name, spec in specs.items():
    source, header = ((project / spec[key]).resolve(strict=True) for key in ("source", "header"))
    assert source.is_relative_to(project) and header.is_relative_to(project), "Foreign authored native input"
    assert source.is_file() and header.is_file(), "Missing authored native input"
    for key, staged in (("source", source), ("header", header)):
        authored_input = (original / spec[key]).resolve(strict=True)
        assert authored_input.is_relative_to(original) and authored_input.is_file(), "Foreign original native input"
        assert staged.read_bytes() == authored_input.read_bytes(), "Authored native input changed before compilation"
    definitions = [item for flag in spec.get("defines", []) for item in ("-D", flag)]
    dependency_text = run([compiler, "tool", "dependencies", "--format", "flat", "--include", "/",
                           *definitions, source])
    (support / (name + "-dependencies.txt")).write_text(dependency_text)
    paths = {source}
    for line in dependency_text.splitlines():
        assert line and not line.endswith((" filtered", " duplicate skipped")), "Incomplete native require graph"
        path = Path(line)
        paths.add((path if path.is_absolute() else project / path).resolve(strict=True))
    graph = {}
    for path in sorted(paths):
        assert path.is_file(), "Missing native required source"
        if path.is_relative_to(project):
            origin, relative = "project", str(path.relative_to(project))
        elif any(path.is_relative_to(root) for root in sdk_roots):
            origin, relative = "sdk", str(path)
        elif any(path.is_relative_to(root) for root in dependency_roots):
            origin, relative = "dependency", str(path)
        else:
            raise AssertionError("Foreign native require graph owner: " + str(path))
        graph[str(path)] = {"origin": origin, "relative": relative, "sha256": sha(path)}
    assert any(record["origin"] == "sdk" for record in graph.values()), "Missing original Crystal prelude"
    for relative in ("prelude.cr", "crystal/main.cr", "gc.cr"):
        assert any(str(root / relative) in graph for root in sdk_roots), "Shadowed original Crystal runtime require"
    header_check = subprocess.run([cc, "-x", "c", "-fsyntax-only", "-include", str(header), "-"],
                                  input="void *exports[] = {" + ",".join("(void*)&" + symbol for symbol in spec["exports"]) + "};\n",
                                  text=True, capture_output=True)
    assert header_check.returncode == 0, "Authored header/export mismatch: " + header_check.stderr
    library = output / "lib" / ("lib" + name + ".so")
    library.parent.mkdir(exist_ok=True)
    command = [compiler, "build", str(source), "--single-module", "--link-flags=-shared",
               *definitions, "-o", str(library), "--verbose"]
    native_build = run(command)
    (support / (name + "-build.txt")).write_text(native_build)
    elf = library.read_bytes()
    assert elf[:4] == b"\x7fELF" and struct.unpack_from("<H" if elf[5] == 1 else ">H", elf, 18)[0] == {
        "x86_64-linux": 62, "aarch64-linux": 183
    }[system], "Foreign native library architecture"
    symbols = run([nm, "-D", "--defined-only", library])
    exported = {parts[-1] for line in symbols.splitlines()
                if len(parts := line.split()) >= 3 and parts[-2] in ("T", "W")}
    assert set(spec["exports"]).issubset(exported), "Missing callable authored native export"
    linked_libraries = run([ldd, library])
    assert "not found" not in linked_libraries, "Unresolved native runtime dependency"
    linked = {}
    for line in linked_libraries.splitlines():
        fields = line.split()
        candidates = [field for field in fields if field.startswith("/")]
        if candidates:
            path = Path(candidates[0]).resolve(strict=True)
            assert str(path).startswith("/nix/store/"), "Foreign native runtime dependency"
            linked[str(path)] = sha(path)
            if path.name.startswith("libgc.so"):
                assert path.is_relative_to(Path(selected_gc).resolve(strict=True)), "Foreign Crystal GC dependency"
    installed_header = output / "include" / name / header.name
    installed_header.parent.mkdir(parents=True)
    shutil.copy2(header, installed_header)
    assert installed_header.read_bytes() == header.read_bytes(), "Installed authored header changed"
    for path, record in graph.items():
        assert sha(Path(path)) == record["sha256"], "Native required source changed during compilation"
    assert header.read_bytes() == (original / spec["header"]).read_bytes(), "Authored native header changed during compilation"
    records[name] = {"specification": spec, "command": command,
                     "compiler": {"path": str(compiler_exec), "sha256": sha(compiler_exec)},
                     "requireGraph": graph, "library": str(library), "librarySha256": sha(library),
                     "header": str(installed_header), "headerSha256": sha(installed_header),
                     "dynamicSymbols": symbols,
                     "linkedLibraries": linked,
                     "nativeLinkerOutput": linked_libraries,
                     "dynamicSection": run([Path(nm).parent / "readelf", "-d", library])}
authored = {str(path.relative_to(original)): sha(path)
            for path in sorted(original.rglob("*")) if path.is_file()}
post_build = {relative: sha(project / relative) if (project / relative).is_file() else None
              for relative in authored}
(support / "verified-libraries.json").write_text(json.dumps({
    "libraries": records, "authoredInputs": authored, "postBuildInputs": post_build,
    "nativeCompilerPath": compiler, "sdkRoots": list(map(str, sdk_roots))
    , "selectedGcRoot": selected_gc
}, indent=2, sort_keys=True) + "\n")
