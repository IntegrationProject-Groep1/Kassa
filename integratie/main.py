import time
import sys

def main():
    print("Kassa Integration Service Gestart.", flush=True)
    print("Wachtend op verdere code van het team. Container blijft actief...", flush=True)
    
    # Simpele keep-alive loop
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        print("Service wordt afgesloten...")
        sys.exit(0)

if __name__ == "__main__":
    main()
