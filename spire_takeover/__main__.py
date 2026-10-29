"""Let the bundled policy play a running Steam game through the SpireTakeover mod."""

import argparse
import json
import os
import sys
from pathlib import Path

import torch

from spire_takeover.env.protocol import ProtocolError
from spire_takeover.steam import parse_duration, play

ROOT = Path(__file__).resolve().parent.parent
CHECKPOINT = ROOT / "checkpoint"
BRIDGE = Path("SlayTheSpire2") / "spire_takeover" / "bridge"


def bridge_candidates():
    """Where the mod writes its bridge: `%APPDATA%/SlayTheSpire2/spire_takeover/bridge`
    on Windows, the same folder under `/mnt/c/Users/*/AppData/Roaming` from WSL, and
    Godot's user data folder on Linux (native or Proton)."""
    if os.name == "nt" and os.environ.get("APPDATA"):
        yield Path(os.environ["APPDATA"]) / BRIDGE
    yield from sorted(Path("/mnt/c/Users").glob(f"*/AppData/Roaming/{BRIDGE.as_posix()}"))
    yield Path.home() / ".local/share" / BRIDGE
    yield from sorted(Path.home().glob(
        f".steam/steam/steamapps/compatdata/*/pfx/drive_c/users/steamuser/AppData/Roaming/{BRIDGE.as_posix()}"))


def find_bridge():
    """The bridge folder of the mod's settings (`spire_takeover/settings.json`), which
    the mod writes once the game has started with it installed."""
    found = [path for path in bridge_candidates() if (path.parent / "settings.json").is_file() or path.is_dir()]
    if len(found) != 1:
        listed = "\n  ".join(map(str, found)) or "(none)"
        raise ProtocolError(
            "Cannot tell which bridge folder to use; start the game with the mod once, "
            f"or give --bridge-dir. Found:\n  {listed}"
        )
    return found[0]


def parser():
    p = argparse.ArgumentParser(prog="python -m spire_takeover", description=__doc__)
    p.add_argument("--bridge-dir", type=Path,
                   help="The mod's bridge folder; found automatically when there is one")
    p.add_argument("--checkpoint", type=Path, default=CHECKPOINT,
                   help=f"Policy checkpoint directory (default {CHECKPOINT})")
    p.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu",
                   help="cuda, cuda:1 or cpu (default: cuda when available)")
    p.add_argument("--compile", action="store_true",
                   help="torch.compile the model blocks (needs a C++ toolchain; slower start)")
    p.add_argument("--threads", type=int, default=4, help="CPU threads for inference")
    p.add_argument("--run-for", type=parse_duration,
                   help="How long to stay beside the game, such as 8h, 45m or 90s; default until interrupted")
    p.add_argument("--max-decisions", type=int, help="Stop after this many decisions; default no limit")
    p.add_argument("--request-timeout", type=float, default=120,
                   help="Seconds to wait for the game to answer one bridge request")
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    torch.set_num_threads(args.threads)
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    try:
        bridge = args.bridge_dir or find_bridge()
        print(json.dumps({"bridge": str(bridge), "checkpoint": str(args.checkpoint), "device": args.device},
                         ensure_ascii=False), file=sys.stderr)
        result = play(args.checkpoint, bridge, args.device, request_timeout=args.request_timeout,
                      run_for=args.run_for, max_decisions=args.max_decisions,
                      compile_blocks=args.compile)
    except KeyboardInterrupt:
        return 130
    except (ProtocolError, ValueError, OSError, RuntimeError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
