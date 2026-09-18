import subprocess

result = subprocess.run(
    [r"myvenv\Scripts\python.exe", "-m", "unittest", "discover", "-p", "test_*.py"],
    capture_output=True, text=True
)

if result.returncode != 0:
    out = result.stderr
    # Split into individual errors
    blocks = out.split("======================================================================")
    for b in blocks:
        if "FAIL:" in b or "ERROR:" in b:
            print("======================================================================")
            print(b[:1500])
    print(f"\nFinal lines:\n{out[-500:]}")
else:
    print("ALL TESTS PASSED!")
