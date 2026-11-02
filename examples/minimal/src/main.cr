require "db"
puts DB::Error.new("Locked Crystal dependencies").message
