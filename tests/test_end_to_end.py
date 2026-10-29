"""The bundled checkpoint plays one recorded Steam decision through the file bridge,
with a stand-in for the game answering each request the way the mod does."""

import json
import threading
from pathlib import Path

from spire_takeover.steam import DECISIONS, PROTOCOL, play

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).parent / "fixtures"


def fake_game(directory, message, stop, executed):
    request = directory / "request.json"
    while not stop.is_set():
        try:
            asked = json.loads(request.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            stop.wait(0.02)
            continue
        request.unlink()
        command = asked["command"]
        if command == "observe":
            answer = dict(message, status="terminal" if executed else "decision")
        elif command == "execute":
            executed.append(asked["action"])
            answer = dict(status="executed")
        else:
            answer = dict(status="ok")
        answer.update(id=asked["id"], protocol=PROTOCOL, reset_count=0)
        temporary = directory / "answer.tmp"
        temporary.write_text(json.dumps(answer))
        temporary.replace(directory / f"response-{asked['id']}.json")


def test_the_bundled_checkpoint_takes_a_recorded_decision(tmp_path):
    message = json.loads((FIXTURES / "steam-rewards.json").read_text(encoding="utf-8"))
    stop, executed = threading.Event(), []
    game = threading.Thread(target=fake_game, args=(tmp_path, message, stop, executed), daemon=True)
    game.start()
    try:
        result = play(ROOT / "checkpoint", tmp_path, "cpu", request_timeout=30, max_decisions=1)
    finally:
        stop.set()
        game.join()
    assert result["decisions"] == 1 and result["errors"] == 0
    offered = {a["command"] for a in message["state"]["legal"]["actions"]}
    assert len(executed) == 1 and executed[0]["command"] in offered
    record = json.loads((tmp_path / DECISIONS).read_text(encoding="utf-8").splitlines()[0])
    assert record["phase"] == "rewards" and record["ranking"]
