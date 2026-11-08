# OpenSTA script. Reads PERIOD (ns) and LIB (Liberty file) from the environment.
read_liberty $::env(LIB)
read_verilog synth.v
link_design top

set period $::env(PERIOD)
create_clock -name clk -period $period [get_ports clk]
set_input_delay  0.1 -clock clk [get_ports {a[*] b[*]}]
set_output_delay 0.1 -clock clk [get_ports {sum[*]}]

puts "=========================================================================="
puts "report_checks -path_delay max"
puts "--------------------------------------------------------------------------"
report_checks -path_delay max

puts "=========================================================================="
puts "report_tns"
puts "--------------------------------------------------------------------------"
report_tns

puts "=========================================================================="
puts "report_wns"
puts "--------------------------------------------------------------------------"
report_wns

puts "=========================================================================="
puts "report_worst_slack"
puts "--------------------------------------------------------------------------"
report_worst_slack -max

puts "=========================================================================="
puts "report_power"
puts "--------------------------------------------------------------------------"
report_power

exit
