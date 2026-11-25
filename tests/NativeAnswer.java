import java.lang.foreign.*;
import static java.lang.foreign.ValueLayout.*;
class NativeAnswer {
  public static void main(String[] args) throws Throwable {
    System.loadLibrary("answer");
    var lookup = SymbolLookup.loaderLookup();
    var linker = Linker.nativeLinker();
    var init = linker.downcallHandle(lookup.find("answer_init").orElseThrow(),
      FunctionDescriptor.of(JAVA_INT, JAVA_INT, ADDRESS));
    var function = linker.downcallHandle(lookup.find("native_answer").orElseThrow(),
      FunctionDescriptor.of(JAVA_INT, JAVA_INT));
    var collect = linker.downcallHandle(lookup.find("answer_collect").orElseThrow(),
      FunctionDescriptor.ofVoid());
    {
      var arena = Arena.global();
      var name = arena.allocateUtf8String("crystal-java");
      var argv = arena.allocate(ADDRESS, 2);
      argv.setAtIndex(ADDRESS, 0, name);
      argv.setAtIndex(ADDRESS, 1, MemorySegment.NULL);
      if ((int)init.invokeExact(1, argv) != 0) throw new AssertionError();
      int expected = Integer.parseInt(args[0]);
      for (int i=0; i<100; i++) {
        if ((int)function.invokeExact(i) != i+expected) throw new AssertionError();
        collect.invokeExact();
      }
      if ((int)function.invokeExact(-1) != expected-1) throw new AssertionError();
      System.out.println("Actual Crystal Java FFM100/GC/overflow PASS");
    }
  }
}
