"""Load a policy checkpoint directory (manifest.json and weight shards) for inference."""

import dataclasses
import json
from pathlib import Path

import torch

from spire_takeover.encoding import rules
from spire_takeover.network.config import ModelConfig
from spire_takeover.network.model import PolicyNetwork
from spire_takeover.encoding.representation import ENCODING_VERSION
from spire_takeover.encoding.vocabulary import Vocabulary
from spire_takeover.env.public_history import require_history_version


def load_model(path, device="cpu", *, allow_legacy_encoding=False, compile_blocks=False):
    """The model, its vocabulary and manifest. Blocks are compiled only when asked:
    compiling needs a C++ toolchain (MSVC on Windows) and slows the first decisions."""
    path = Path(path)
    manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("format") != 1:
        raise ValueError("Unsupported checkpoint format")
    require_history_version(manifest.get("public_history_version"))
    if manifest.get("encoding_version") != ENCODING_VERSION and not allow_legacy_encoding:
        raise ValueError("Checkpoint input encoding changed; use bootstrap --weights-only to start a new run")
    if manifest.get("rules") != rules.digest():
        raise ValueError("Checkpoint was trained with different rule text")
    if "ascension" not in manifest.get("training", {}):
        raise ValueError("Checkpoint has no declared ascension; do not infer a new default")
    config = ModelConfig.from_dict(manifest["model"])
    config = dataclasses.replace(config, compile_blocks=compile_blocks)
    # Allocate once on the destination without a second full CPU model.
    with torch.device("meta"):
        model = PolicyNetwork(config)
    model.to_empty(device=device)
    expected = set(model.state_dict())
    loaded = set()
    for name in manifest["weights"]:
        shard = torch.load(path / name, map_location=device, weights_only=True)
        if loaded & shard.keys() or not shard.keys() <= expected:
            raise ValueError("Duplicate or unexpected checkpoint tensors")
        model.load_state_dict(shard, strict=False)
        loaded.update(shard)
        del shard
    if loaded != expected:
        raise ValueError("Checkpoint is missing model tensors")
    # Public schema symbols added since the checkpoint was saved take spare rows; every old
    # ID stays. Every reader of the checkpoint (a resumed run, its KL reference, evaluation)
    # expands it the same way, so they share one table and its digest.
    vocabulary = Vocabulary.from_state(manifest["vocabulary"], config).expanded()
    return model, vocabulary, manifest
