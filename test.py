#!/usr/bin/env python3
import subprocess
import time
import os
import sys
from datetime import datetime
import threading

LOG_FILE = "test_results.log"

# -------------------------
# Helper functions for netem
# -------------------------
def clear_netem():
    """Remove any netem settings on the loopback interface."""
    cmd = ["sudo", "tc", "qdisc", "del", "dev", "lo", "root"]
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        log("Warning: " + str(e))

def apply_netem(params):
    """
    Apply network emulation on the loopback interface using tc.
    """
    # Clear any existing qdisc first.
    clear_netem()
    
    # Build the command string.
    cmd = ["sudo", "tc", "qdisc", "add", "dev", "lo", "root", "netem"]
    
    if "delay" in params:
        cmd.extend(["delay", params["delay"]])
    if "loss" in params:
        cmd.extend(["loss", params["loss"]])
    if "duplicate" in params:
        cmd.extend(["duplicate", params["duplicate"]])
    if "reorder" in params:
        cmd.extend(["reorder", params["reorder"], "50%"])
    
    log("Applying netem: " + " ".join(cmd))
    subprocess.run(cmd, check=True)

# -------------------------
# Logging helper
# -------------------------
def log(message):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    full_message = f"[{timestamp}] {message}"
    print(full_message, flush=True)
    with open(LOG_FILE, "a") as f:
        f.write(full_message + "\n")
        f.flush()

# -------------------------
# Functions to stream process output in real time
# -------------------------
def stream_output(stream, prefix):
    """Read from a process stream line by line and log it with a prefix."""
    for line in iter(stream.readline, ''):
        if line:
            log(f"{prefix}: {line.strip()}")
    stream.close()

def launch_and_stream(cmd, proc_name):
    """Launch a subprocess and stream its stdout and stderr in real time."""
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1  # Line buffered.
    )
    t_out = threading.Thread(target=stream_output, args=(proc.stdout, proc_name + " STDOUT"))
    t_err = threading.Thread(target=stream_output, args=(proc.stderr, proc_name + " STDERR"))
    t_out.start()
    t_err.start()
    return proc, t_out, t_err

# -------------------------
# Test Harness functions
# -------------------------
def generate_test_file(filename, size_bytes):
    with open(filename, "wb") as f:
        f.write(os.urandom(size_bytes))

def run_test_case(case):
    log("\n========== Running {} ==========".format(case["name"]))
    test_file = "testfile.bin"
    file_size = 1024 * 1024  # 1 MiB
    generate_test_file(test_file, file_size)
    log("Test file created: " + test_file + f" ({file_size} bytes)")
    
    # Ensure the 'src' folder exists and remove any old copy.
    src_dir = "src"
    if not os.path.exists(src_dir):
        os.mkdir(src_dir)
    received_file = os.path.join(src_dir, os.path.basename(test_file))
    if os.path.exists(received_file):
        os.remove(received_file)
    
    # Apply network emulation if needed.
    if case.get("netem"):
        try:
            apply_netem(case["netem"])
        except subprocess.CalledProcessError as e:
            log("Failed to apply netem settings: " + str(e))
            sys.exit(1)
    else:
        log("No netem settings to apply for this test case.")
    
    server_ip = "127.0.0.1"
    server_port = "5005"
    
    # Start the server and stream its output.
    log("Starting server...")
    server_cmd = [sys.executable, "urft_server.py", server_ip, server_port]
    server_proc, server_tout, server_terr = launch_and_stream(server_cmd, "SERVER")
    
    # Allow the server time to start.
    time.sleep(1)
    
    # Start the client and stream its output.
    log("Starting client...")
    client_cmd = [sys.executable, "urft_client.py", test_file, server_ip, server_port]
    client_proc, client_tout, client_terr = launch_and_stream(client_cmd, "CLIENT")
    
    # Wait for the client to finish.
    start_time = time.time()
    client_proc.wait()
    client_tout.join()
    client_terr.join()
    client_duration = time.time() - start_time
    log(f"Client completed in {client_duration:.2f} seconds.")
    
    # Wait for the server to finish.
    try:
        server_proc.wait(timeout=case["time_limit"])
    except subprocess.TimeoutExpired:
        server_proc.kill()
        log("Server timed out.")
    server_tout.join()
    server_terr.join()
    
    # Now, verify the file content.
    if os.path.exists(received_file):
        with open(test_file, "rb") as orig, open(received_file, "rb") as recv:
            if orig.read() == recv.read():
                log("Test PASSED: The received file matches the original.")
                result = True
            else:
                log("Test FAILED: File content mismatch.")
                result = False
    else:
        log("Test FAILED: Received file not found in the 'src' folder.")
        result = False
    
    # Cleanup: Remove test files.
    os.remove(test_file)
    if os.path.exists(received_file):
        os.remove(received_file)
    
    # Clear netem settings after the test.
    clear_netem()
    # Pause briefly between tests.
    time.sleep(1)
    
    return case["name"], result

def main():
    # Clear the log file.
    with open(LOG_FILE, "w") as f:
        f.write("Test Results Log\n\n")
    
    # Ensure the script is run as root.
    if os.geteuid() != 0:
        print("This test harness requires root privileges to apply netem settings. Please run as root or with sudo.", flush=True)
        sys.exit(1)
    
    # Define all 7 test cases.
    test_cases = [
        {
            "name": "Test Case 1: 1 MiB, UDP, RTT=10ms, no errors",
            "netem": {"delay": "10ms"},
            "time_limit": 30
        },
        {
            "name": "Test Case 2: 1 MiB, UDP, RTT=10ms, Client-to-Server Packet Duplication 2%",
            "netem": {"delay": "10ms", "duplicate": "2%"},
            "time_limit": 30
        },
        {
            "name": "Test Case 3: 1 MiB, UDP, RTT=10ms, Client-to-Server Packet Loss 2%",
            "netem": {"delay": "10ms", "loss": "2%"},
            "time_limit": 30
        },
        {
            "name": "Test Case 4: 1 MiB, UDP, RTT=10ms, Server-to-Client Packet Duplication 5%",
            "netem": {"delay": "10ms", "duplicate": "5%"},
            "time_limit": 30
        },
        {
            "name": "Test Case 5: 1 MiB, UDP, RTT=10ms, Server-to-Client Packet Loss 5%",
            "netem": {"delay": "10ms", "loss": "5%"},
            "time_limit": 30
        },
        {
            "name": "Test Case 6: 1 MiB, UDP, RTT=250ms, no errors",
            "netem": {"delay": "250ms"},
            "time_limit": 60
        },
        {
            "name": "Test Case 7: 1 MiB, UDP, RTT=250ms, Client-to-Server Packet Re-ordering 2%",
            "netem": {"delay": "250ms", "reorder": "2%"},
            "time_limit": 90
        }
    ]
    
    results = []
    for case in test_cases:
        name, result = run_test_case(case)
        results.append((name, result))
    
    log("\n========== Test Summary ==========")
    for name, result in results:
        status = "PASSED" if result else "FAILED"
        log("{:<80} : {}".format(name, status))
    
    log("\nAll tests completed.")

if __name__ == "__main__":
    main()
