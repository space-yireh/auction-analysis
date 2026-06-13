import os
import urllib.request
from pathlib import Path

# Paths setup
BASE_DIR = Path(__file__).parent.parent
LIBS_DIR = BASE_DIR / "chrome-extension" / "libs"

# Library files to download
LIBRARIES = {
    "jszip.min.js": "https://cdnjs.cloudflare.com/ajax/libs/jszip/3.10.1/jszip.min.js",
    "pdf.min.js": "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.min.js",
    "pdf.worker.min.js": "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js"
}

def main():
    print(f"Creating libs directory: {LIBS_DIR}")
    LIBS_DIR.mkdir(parents=True, exist_ok=True)
    
    for filename, url in LIBRARIES.items():
        dest_path = LIBS_DIR / filename
        print(f"Downloading {filename} from {url}...")
        try:
            # Add user agent to avoid blockage
            req = urllib.request.Request(
                url, 
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            )
            with urllib.request.urlopen(req) as response:
                dest_path.write_bytes(response.read())
            print(f" Saved: {dest_path}")
        except Exception as e:
            print(f" Error downloading {filename}: {e}")
            raise e

    print("\nAll library files downloaded successfully!")

if __name__ == "__main__":
    main()
