#!/usr/bin/env bash
# Synthesize design.v once with Yosys, then run OpenSTA at several clock
# periods and save one report per run for the dashboard parser.
#
# Usage (inside the Ubuntu container):
#   LIB=/work/OpenROAD-flow-scripts/flow/platforms/nangate45/lib/<file>.lib ./sweep.sh
#   LIB=... ./sweep.sh 1.0 2.0 3.0        # custom periods (ns)
#
# Env overrides: STA (path to sta binary), OUT (report folder).
set -euo pipefail
cd "$(dirname "$0")"

: "${LIB:?Set LIB to the Liberty (.lib) file}"
STA="${STA:-/root/OpenSTA/build/sta}"
OUT="${OUT:-../real_reports}"
PERIODS=("$@")
if [ ${#PERIODS[@]} -eq 0 ]; then PERIODS=(1.0 1.5 2.0 3.0 4.0); fi

mkdir -p "$OUT"

echo "[1/2] Synthesizing with Yosys..."
yosys -q -l synth.log -p "
  read_verilog design.v
  synth -top top
  dfflibmap -liberty $LIB
  abc -liberty $LIB
  clean
  write_verilog -noattr synth.v
  tee -o area_stat.txt stat -liberty $LIB
"

echo "[2/2] Running OpenSTA sweep..."
for p in "${PERIODS[@]}"; do
  out="$OUT/adder16_clk${p}.rpt"
  PERIOD="$p" LIB="$LIB" "$STA" -no_splash run.tcl > "$out" 2>&1
  # OpenSTA has no area report; append Yosys's synthesized cell area so the
  # parser can pick it up from the same file.
  { echo; echo "yosys stat (synthesized cell area)"; cat area_stat.txt; } >> "$out"
  echo "  period ${p} ns -> $out"
done

echo "Done. Netlist area summary is in area_stat.txt."
