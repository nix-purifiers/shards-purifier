import ctypes
import json
from pathlib import Path
import subprocess
import sys

projection, expected = Path(sys.argv[1]), int(sys.argv[2])
sys.path.insert(0, str(projection))
import purifier_native

library = json.loads((projection / "catalog.json").read_text())["libraries"]["answer"]
handle = purifier_native.load("answer")
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
f=FFI(); f.cdef("int answer_init(int,char **); uint32_t native_answer(uint32_t); void answer_collect(void);")
lib=f.dlopen(LIBRARY)
name=f.new("char[]",b"crystal-cffi"); argv=f.new("char *[]",[name,f.NULL])
assert lib.answer_init(1,argv)==0
for value in [*range(100),0xffffffff]:
 assert lib.native_answer(value)==(value+EXPECTED) % (1<<32)
 lib.answer_collect()
print("Actual Crystal CFFI100/GC/overflow PASS")
'''
subprocess.run([sys.executable, "-c", "LIBRARY=" + repr(library) + "\nEXPECTED=" + str(expected) + "\n" + program], check=True)
print("Actual Crystal Python projection ctypes100/GC/overflow PASS")
