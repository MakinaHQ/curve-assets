"""
Regression tests for the token list generation pipeline.

These lock in the data-integrity fixes:
  * `generate_tokenlist` must accumulate tokens across ALL networks instead of
    discarding every network after the first.
  * A network's tokens must appear exactly once (the old `list.extend(list)`
    self-extension duplicated them).
  * `networks_to_include` and `networks_to_ignore` must both be applied.

Run with:  python -m pytest tests/ -v      (or: python tests/test_generate.py)
"""

import os
import sys
import unittest
from typing import Dict, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# The real pipeline reaches out to an RPC node for every token. These tests stub
# the network boundary so they stay deterministic and run offline.
from scripts import generate as generate_mod
from scripts import process as process_mod


def _fake_process_network(network_name, existing_tokenlist, all_failed_tokens):
    """Return a deterministic, network-specific token for each network."""
    token = {
        "chainId": 1,
        "address": f"0x{'0' * 38}{abs(hash(network_name)) % 100:02d}",
        "name": f"Token of {network_name}",
        "symbol": network_name[:4].upper(),
        "decimals": 18,
        "logoURI": f"https://example.test/{network_name}.png",
    }
    return [token], []


class GenerateTokenlistAccumulationTest(unittest.TestCase):
    """The generator must not lose or duplicate tokens across networks."""

    def setUp(self) -> None:
        self._orig_process = generate_mod.process_network
        self._orig_scan = generate_mod.scan_images_folder
        self._orig_display = generate_mod.display_summary
        self._orig_native = generate_mod.ensure_native_token_in_list

        generate_mod.process_network = _fake_process_network
        # Pretend the images folder yields three networks.
        generate_mod.scan_images_folder = lambda _existing: (
            ["ethereum", "arbitrum", "base"],
            [],
            [],
        )
        generate_mod.display_summary = lambda *args, **kwargs: None
        # The native-token injection depends on the real on-disk images folder and
        # the shared NETWORKS table. It is exercised by its own unit test; stub it
        # here so this test isolates the accumulation/duplication behaviour.
        generate_mod.ensure_native_token_in_list = lambda *args, **kwargs: None

    def tearDown(self) -> None:
        generate_mod.process_network = self._orig_process
        generate_mod.scan_images_folder = self._orig_scan
        generate_mod.display_summary = self._orig_display
        generate_mod.ensure_native_token_in_list = self._orig_native

    @staticmethod
    def _names(result: Dict) -> List[str]:
        return sorted(t["name"] for t in result["tokens"])

    def test_all_networks_are_retained(self) -> None:
        """Every processed network must contribute its tokens to the result."""
        result = generate_mod.generate_tokenlist({}, networks_to_include=None, networks_to_ignore=None)
        names = self._names(result)
        self.assertEqual(
            names,
            ["Token of arbitrum", "Token of base", "Token of ethereum"],
            "tokens from earlier networks were dropped from the output",
        )

    def test_tokens_are_not_duplicated(self) -> None:
        """Each network's token must appear exactly once, not twice."""
        result = generate_mod.generate_tokenlist({}, networks_to_include=None, networks_to_ignore=None)
        names = self._names(result)
        self.assertEqual(
            len(names),
            len(set(names)),
            f"duplicate tokens produced: {names}",
        )

    def test_include_and_ignore_are_both_applied(self) -> None:
        """
        An ignore list must still take effect when an include list is supplied.
        A previous `if/elif` made the ignore list a silent no-op in that case.
        """
        result = generate_mod.generate_tokenlist(
            {},
            networks_to_include=["ethereum", "arbitrum", "base"],
            networks_to_ignore=["arbitrum"],
        )
        self.assertEqual(self._names(result), ["Token of base", "Token of ethereum"])


if __name__ == "__main__":
    unittest.main(verbosity=2)