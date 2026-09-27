import json
import os
import re
import tempfile
import unittest

from tools import evolve, soak


class TestEvolveReport(unittest.TestCase):
    def test_report_lineage_and_resume(self):
        with tempfile.TemporaryDirectory() as d:
            out, lin, ckpt = (os.path.join(d, n) for n in ("r.html", "l.jsonl", "w.ckpt"))
            evolve.main(["--seed", "3", "--ticks", "200", "--sample-every", "20",
                         "--out", out, "--lineage", lin, "--checkpoint", ckpt])
            html = open(out).read()
            self.assertNotIn("__DATA__", html)
            data = json.loads(re.search(r"const DATA = (\{.*?\});\n", html, re.S).group(1))
            self.assertEqual(data["t"][0], 0)
            self.assertEqual(data["t"][-1], 200)
            self.assertEqual(len(data["counts"]["total"]), len(data["t"]))
            self.assertEqual(len(data["spectrum"]["counts"]), len(data["t"]))
            self.assertIn("Other", data["families"]["order"])
            records = [json.loads(line) for line in open(lin)]
            self.assertTrue(any(r[0] == "birth" and r[3] is None for r in records))

            out2 = os.path.join(d, "r2.html")
            evolve.main(["--resume", ckpt, "--ticks", "100", "--sample-every", "20", "--out", out2])
            data2 = json.loads(re.search(r"const DATA = (\{.*?\});\n", open(out2).read(), re.S).group(1))
            self.assertEqual(data2["t"][0], 200)
            self.assertEqual(data2["t"][-1], 300)


class TestSoakHelpers(unittest.TestCase):
    def test_parse_rules_and_mix(self):
        r = soak.parse_rules(["eat_fraction=0.5", "predators_are_prey=false", "hunt_cooldown=8"])
        self.assertEqual((r.eat_fraction, r.predators_are_prey, r.hunt_cooldown), (0.5, False, 8))
        self.assertEqual(soak.parse_mix("8:1:1"), {"absorber": 8.0, "parasite": 1.0, "predator": 1.0})
        with self.assertRaises(SystemExit):
            soak.parse_rules(["nonsense=1"])
        dyn = soak.parse_rules(["num_rocks=3"], soak.base_rules("dynamic"))
        self.assertEqual(dyn.num_rocks, 3)
        self.assertGreater(dyn.pulse_depth, 0)
        self.assertEqual(soak.parse_rules([], soak.base_rules("static")).num_rocks, 0)


if __name__ == "__main__":
    unittest.main()
