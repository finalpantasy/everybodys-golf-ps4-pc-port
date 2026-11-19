"""Build the encrypted inner record for the local daily score-list probe."""
import argparse
from ctypes.util import find_library
from pathlib import Path

from make_discovery_fixture import encrypt_blocks, read_prepared_eboot


def build_score_block(eboot: Path, libcrypto: str) -> bytes:
    elf = read_prepared_eboot(eboot)
    # Title cipher context at 0xf6cc6–0xf6ce5. The prepared ELF has a 0x4000 file bias.
    seed = elf[0x1361EC9 + 0x4000:0x1361ED1 + 0x4000]
    iv = elf[0xF6CC8 + 0x4000:0xF6CD0 + 0x4000]
    return encrypt_blocks(b"0_local\0", seed, iv, libcrypto)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("eboot", type=Path, help="Prepared CUSA04687 1.17 eboot.elf")
    parser.add_argument("output", type=Path, help="New encrypted block file")
    parser.add_argument("--libcrypto", help="OpenSSL libcrypto library with Blowfish support")
    args = parser.parse_args()
    library = args.libcrypto or find_library("crypto")
    if not library:
        parser.error("Specify the OpenSSL library with --libcrypto")
    try:
        block = build_score_block(args.eboot, library)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("xb") as stream:
            stream.write(block)
    except (OSError, AttributeError, ValueError) as error:
        parser.error(str(error))
    print(f"Wrote {len(block)} bytes to {args.output}")


if __name__ == "__main__":
    main()
