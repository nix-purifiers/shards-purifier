require "spec"
require "db"
describe "locked dependency" do
  it "uses the database library" do
    DB::Error.new("locked").message.should eq("locked")
  end
end
