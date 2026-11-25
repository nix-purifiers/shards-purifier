require "db"

fun answer_init(argc : Int32, argv : UInt8**) : Int32
  GC.init
  Crystal.init_runtime
  Crystal.main_user_code(argc, argv)
  0
end

fun native_answer(value : UInt32) : UInt32
  message = DB::Error.new("x" * 41).message.not_nil!
  value &+ message.bytesize.to_u32
end

fun answer_collect : Nil
  GC.collect
end
