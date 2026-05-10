"""
Master script: run all SAGA paper benchmarks and produce all figures.

Usage:
    cd /path/to/oldsaga/benchmarks
    python run_all.py [--mongo-uri URI] [--duration SEC] [--threads N]

Figures produced (all PDFs):
    fig2_otk_generation.pdf
    fig3_token_derivation.pdf
    fig4_protocol_overhead_provider.pdf
    fig5_protocol_overhead_agent.pdf
    fig6a_otk_request.pdf
    fig6b_otk_refresh.pdf
    fig6c_capacity.pdf
    fig7_agent_reg_{10,100,1000}otks.pdf
    fig8_otk_refresh_{10,100,1000}otks.pdf
"""
import subprocess, sys, os

SCRIPTS = [
    "fig2_otk_generation.py",
    "fig3_token_derivation.py",
    "fig4_fig5_protocol_overhead.py",
    "fig6_7_8_throughput.py",
]

here = os.path.dirname(os.path.abspath(__file__))

# Forward any extra args to sub-scripts (e.g. --mongo-uri, --duration)
extra = sys.argv[1:]

for script in SCRIPTS:
    path = os.path.join(here, script)
    cmd  = [sys.executable, path] + extra
    print(f"\n{'='*60}")
    print(f"Running: {script}")
    print('='*60)
    result = subprocess.run(cmd, cwd=here)
    if result.returncode != 0:
        print(f"  WARNING: {script} exited with code {result.returncode}")

print("\n\nAll benchmarks complete.  PDFs are in:", here)
