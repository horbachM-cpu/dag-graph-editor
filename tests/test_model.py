import json
import unittest
from pathlib import Path

from dag_graph_editor.model import GraphModel


REPO_ROOT = Path(__file__).resolve().parents[1]


class GraphModelTests(unittest.TestCase):
    def load_example(self, name: str) -> dict:
        with (REPO_ROOT / "examples" / name).open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def test_sample_graph_roundtrip_preserves_node_count(self):
        model = GraphModel()
        sample = self.load_example("sample_graph.json")

        model.from_json(sample)
        exported = model.to_json()

        self.assertEqual(len(sample["nodes"]), len(exported["nodes"]))
        self.assertEqual(exported["meta"]["title"], sample["meta"]["title"])

    def test_project_management_demo_computes_expected_values(self):
        model = GraphModel()
        demo = self.load_example("project_management_demo.json")

        model.from_json(demo)
        ok, error = model.compute_cpm()

        self.assertTrue(ok, error)
        self.assertIsNone(error)
        self.assertEqual(model.doc.nodes["pm004"].pm.FAZ, 4)
        self.assertEqual(model.doc.nodes["pm003"].pm.GP, 1)
        self.assertTrue(model.doc.nodes["pm005"].pm.isCritical)

    def test_reparent_validation_rejects_cycles(self):
        model = GraphModel()

        root = model.add_node("Root")
        child = model.add_node("Child", root.id)
        grandchild = model.add_node("Grandchild", child.id)

        self.assertFalse(model.is_acyclic_if_reparent(root.id, grandchild.id))
        self.assertTrue(model.is_acyclic_if_reparent(grandchild.id, root.id))


if __name__ == "__main__":
    unittest.main()
