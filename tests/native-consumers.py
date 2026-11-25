import ctypes
import json
import os
from pathlib import Path
import subprocess
import sys

projection, expected = Path(sys.argv[1]), int(sys.argv[2])
proof = json.loads(Path(sys.argv[3]).read_text())
sys.path.insert(0, str(projection))
import purifier_native

library = json.loads((projection / "catalog.json").read_text())["libraries"]["answer"]
handle = purifier_native.load("answer", mode=os.RTLD_NOW | os.RTLD_NODELETE)
class DlInfo(ctypes.Structure):
    _fields_ = [("filename", ctypes.c_char_p), ("base", ctypes.c_void_p),
                ("symbol", ctypes.c_char_p), ("address", ctypes.c_void_p)]

dladdr = ctypes.CDLL(None).dladdr
dladdr.argtypes = [ctypes.c_void_p, ctypes.POINTER(DlInfo)]
dladdr.restype = ctypes.c_int
origins = {}
for symbol in ["answer_init", "native_answer", "answer_collect", "GC_malloc"]:
    info = DlInfo()
    assert dladdr(ctypes.cast(getattr(handle, symbol), ctypes.c_void_p), ctypes.byref(info))
    origin = Path(info.filename.decode()).resolve(strict=True)
    if symbol == "GC_malloc":
        assert origin.is_relative_to(Path(proof["selectedGcRoot"]).resolve())
        import hashlib
        assert hashlib.sha256(origin.read_bytes()).hexdigest() == proof["libraries"]["answer"]["linkedLibraries"][str(origin)]
    else:
        assert origin == Path(library).resolve()
    origins[symbol] = str(origin)
print("Actual Crystal ABI/runtime/GC physical origins", json.dumps(origins, sort_keys=True))
handle.answer_init.argtypes = [ctypes.c_int, ctypes.POINTER(ctypes.c_char_p)]
handle.answer_init.restype = ctypes.c_int
argv = (ctypes.c_char_p * 2)(b"crystal-ctypes", None)
assert handle.answer_init(1, argv) == 0
handle.native_answer.argtypes = [ctypes.c_uint32]
handle.native_answer.restype = ctypes.c_uint32
handle.answer_collect.argtypes = []
handle.answer_collect.restype = None
for value in [*range(100), 0xffffffff]:
    assert handle.native_answer(value) == (value + expected) % (1 << 32)
    handle.answer_collect()
program = '''from cffi import FFI
import os
from pathlib import Path
f=FFI(); f.cdef("int answer_init(int,char **); uint32_t native_answer(uint32_t); void answer_collect(void);")
lib=f.dlopen(LIBRARY, flags=os.RTLD_NOW | os.RTLD_NODELETE)
name=f.new("char[]",b"crystal-cffi"); argv=f.new("char *[]",[name,f.NULL])
assert lib.answer_init(1,argv)==0
for value in [*range(100),0xffffffff]:
 assert lib.native_answer(value)==(value+EXPECTED) % (1<<32)
 lib.answer_collect()
f.dlclose(lib)
assert str(Path(LIBRARY).resolve()) in Path("/proc/self/maps").read_text()
print("Actual Crystal CFFI100/GC/overflow PASS")
'''
subprocess.run([sys.executable, "-c", "LIBRARY=" + repr(library) + "\nEXPECTED=" + str(expected) + "\n" + program], check=True)
print("Actual Crystal Python projection ctypes100/GC/overflow PASS")
