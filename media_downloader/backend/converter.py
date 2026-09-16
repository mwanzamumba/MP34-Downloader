import json
from pathlib import Path


INPUT_FILE = Path("cookies.json")
OUTPUT_FILE = Path("cookies.txt")


def convert_cookies():
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    cookies = data.get("cookies", [])

    if not cookies:
        raise ValueError("No cookies found in cookies.json")

    with open(OUTPUT_FILE, "w", encoding="utf-8", newline="\n") as f:

        f.write("# Netscape HTTP Cookie File\n")
        f.write("# Generated from browser JSON cookies\n\n")

        for cookie in cookies:

            domain = cookie.get("domain", "")
            path = cookie.get("path", "/")
            secure = "TRUE" if cookie.get("secure", False) else "FALSE"
            name = cookie.get("name", "")
            value = cookie.get("value", "")

            # Netscape format uses TRUE when the cookie
            # applies to subdomains.
            include_subdomains = (
                "FALSE" if cookie.get("hostOnly", False) else "TRUE"
            )

            expiration = cookie.get("expirationDate", 0)

            try:
                expiration = int(float(expiration))
            except (TypeError, ValueError):
                expiration = 0

            f.write(
                f"{domain}\t"
                f"{include_subdomains}\t"
                f"{path}\t"
                f"{secure}\t"
                f"{expiration}\t"
                f"{name}\t"
                f"{value}\n"
            )

    print(f"Converted {len(cookies)} cookies.")
    print(f"Created: {OUTPUT_FILE.absolute()}")


if __name__ == "__main__":
    convert_cookies()