"""Run AI Board Meeting with managed local LLM server lifecycle."""

import subprocess
import sys
import time
import socket
import signal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODEL_PATH = Path("/Users/niallsemple/Documents/kimi/workspace/models/moonshotai_Kimi-Linear-48B-A3B-Instruct-Q2_K_L.gguf")
REPORT_PATH = ROOT / "reports" / f"board-ai-{__import__('datetime').datetime.now(__import__('datetime').timezone.utc).strftime('%Y-%m-%d')}-demo.md"

def wait_for_port(host, port, timeout=120):
    start = time.time()
    while time.time() - start < timeout:
        try:
            with socket.create_connection((host, port), timeout=2):
                return True
        except OSError:
            time.sleep(0.5)
    return False


def main():
    if not MODEL_PATH.exists():
        print(f"Model not found: {MODEL_PATH}")
        print("Expected at workspace/models/ (from the local setup)")
        sys.exit(1)

    print("=" * 60)
    print("  DARWIN AI Board Meeting — Live Demo")
    print("=" * 60)
    print(f"\nModel: {MODEL_PATH.name}")
    print(f"Report: {REPORT_PATH.name}")
    print("\nStarting llama-server (CPU mode, ~30-60s load time)...")
    print("Press Ctrl+C at any time to abort.\n")

    proc = subprocess.Popen(
        [
            "llama-server",
            "-m", str(MODEL_PATH),
            "--host", "127.0.0.1",
            "--port", "8080",
            "-ngl", "0",
            "-c", "4096",
            "--no-webui",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    try:
        if not wait_for_port("127.0.0.1", 8080, timeout=120):
            print("ERROR: Server did not start in time.")
            proc.send_signal(signal.SIGTERM)
            proc.wait(timeout=5)
            sys.exit(1)

        # Wait a bit more for model to fully load
        print("Server port open. Waiting for model to finish loading...")
        time.sleep(5)
        print("Model loaded. Running AI Board Meeting...\n")

        sys.path.insert(0, str(ROOT))
        from darwin_meta.ai_board_meeting import generate_ai_boardMeeting
        from darwin_meta.utils.llm_bridge import LLMBridge

        llm = LLMBridge()
        if not llm.health():
            print("WARNING: LLM health check failed, trying anyway...")

        text = generate_ai_boardMeeting(
            ROOT / "library" / "edges.json",
            ROOT / "library" / "graveyard.json",
            REPORT_PATH,
            llm=llm,
        )

        print("\n" + "=" * 60)
        print("  BOARD MEETING COMPLETE")
        print("=" * 60)
        print(f"\nReport saved to: {REPORT_PATH}\n")
        print("--- REPORT PREVIEW ---\n")
        print(text[:3000])
        if len(text) > 3000:
            print(f"\n... ({len(text) - 3000} more chars) ...")
        print("\n--- END PREVIEW ---")

    except KeyboardInterrupt:
        print("\n\nInterrupted by user.")
    except Exception as e:
        print(f"\nERROR during board meeting: {e}")
        import traceback
        traceback.print_exc()
    finally:
        print("\nShutting down server...")
        proc.send_signal(signal.SIGTERM)
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        print("Done.")


if __name__ == "__main__":
    main()
