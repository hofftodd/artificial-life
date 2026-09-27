import os
import types
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

import simulator


class TestGuiEndToEnd(unittest.TestCase):
    def setUp(self):
        pygame.init()
        self.app = simulator.SimulationApp(seed=7, setup=False)
        # Clock.tick is a read-only C attribute; swap the whole clock for a
        # no-op so frames aren't throttled to 60fps during tests.
        self.app.clock = types.SimpleNamespace(tick=lambda *a, **k: 0)

    def tearDown(self):
        pygame.quit()

    def test_fonts_available(self):
        self.assertIsNotNone(self.app.font)
        self.assertIsNotNone(self.app.big)
        self.assertIsNotNone(self.app.small)

    def test_frames_render_and_world_advances(self):
        before = [ (round(o.x, 3), round(o.y, 3)) for o in self.app.world.organisms ]
        for _ in range(20):
            self.assertTrue(self.app.frame())
        after = [(round(o.x, 3), round(o.y, 3)) for o in self.app.world.organisms]
        self.assertNotEqual(before, after)
        self.assertGreater(len(self.app.world.organisms), 0)

    def test_space_key_toggles_start_stop(self):
        self.assertFalse(self.app.paused)
        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_SPACE))
        self.assertTrue(self.app.handle_events())
        self.assertTrue(self.app.paused)
        world = self.app.world
        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_SPACE))
        self.app.handle_events()
        self.assertFalse(self.app.paused)
        self.assertIs(self.app.world, world)

    def test_space_pause_freezes_world(self):
        self.app.handle_events()
        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_SPACE))
        self.app.handle_events()
        self.assertTrue(self.app.paused)
        frozen = [(o.x, o.y, o.energy, o.age) for o in self.app.world.organisms]
        for _ in range(5):
            self.app.frame()
        current = [(o.x, o.y, o.energy, o.age) for o in self.app.world.organisms]
        self.assertEqual(frozen, current)

    def test_r_key_opens_setup_and_enter_starts_new_world(self):
        original = self.app.world
        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_r))
        self.assertTrue(self.app.handle_events())
        self.assertEqual(self.app.mode, "setup")
        self.assertIs(self.app.world, original)
        self.app.frame()  # world is frozen while the dialog is open
        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
        self.assertTrue(self.app.handle_events())
        self.assertEqual(self.app.mode, "run")
        self.assertIsNot(self.app.world, original)
        self.assertEqual(len(self.app.world.organisms),
                         simulator.simcore.START_POPULATION)
        self.assertEqual(self.app.world.generation, 0)
        self.assertFalse(self.app.paused)

    def test_escape_in_setup_returns_to_running_world(self):
        world = self.app.world
        self.app.open_setup()
        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
        self.assertTrue(self.app.handle_events())
        self.assertEqual(self.app.mode, "run")
        self.assertIs(self.app.world, world)

    def test_setup_dialog_configures_world(self):
        self.app.open_setup()
        dialog = self.app.dialog
        keys = [f[0] for f in dialog.fields]

        def press(key):
            pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=key))
            self.app.handle_events()

        def set_field(name, value):
            while dialog.index != keys.index(name):
                press(pygame.K_DOWN)
            while dialog.values[name] > value:
                press(pygame.K_LEFT)
            while dialog.values[name] < value:
                press(pygame.K_RIGHT)

        set_field("emitters", 1)
        set_field("organisms", 60)
        set_field("predator", 0)
        set_field("parasite", 50)
        set_field("absorber", 50)
        set_field("width", 700)
        set_field("height", 500)
        set_field("rocks", 3)
        set_field("dynamic", 1)
        self.app.draw()
        press(pygame.K_RETURN)

        w = self.app.world
        self.assertEqual(self.app.mode, "run")
        self.assertEqual((w.width, w.height), (700, 500))
        # the window is the world plus the side pane
        self.assertEqual(self.app.screen.get_size(), simulator.window_size(700, 500))
        self.assertEqual(len(w.emitters), 1)
        self.assertEqual(len(w.organisms), 60)
        strategies = {o.strategy for o in w.organisms}
        self.assertNotIn("predator", strategies)
        self.assertEqual(strategies, {"absorber", "parasite"})
        self.assertEqual(len(w.rocks), 3)
        self.assertGreater(w.rules.pulse_depth, 0)

    def test_static_environment_from_dialog(self):
        self.app.open_setup()
        dialog = self.app.dialog
        dialog.values.update(rocks=0, dynamic=0)
        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
        self.app.handle_events()
        w = self.app.world
        self.assertEqual(w.rocks, [])
        self.assertEqual((w.rules.pulse_depth, w.rules.spectrum_drift), (0.0, 0.0))
        self.app.draw()

    def test_setup_buttons_respond_to_clicks(self):
        self.app.open_setup()
        dialog = self.app.dialog
        _rect, rows, start = dialog.layout(self.app.screen.get_size())
        key, _row, _minus, plus = rows[0]
        before = dialog.values[key]
        pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=plus.center))
        self.app.handle_events()
        self.assertEqual(dialog.values[key], before + 1)
        pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1,
                                             pos=start.center))
        self.app.handle_events()
        self.assertEqual(self.app.mode, "run")
        self.assertEqual(len(self.app.world.emitters), before + 1)

    def test_app_starts_in_setup_by_default(self):
        app = simulator.SimulationApp(seed=1)
        self.assertEqual(app.mode, "setup")
        self.assertIsNone(app.world)
        app.clock = types.SimpleNamespace(tick=lambda *a, **k: 0)
        self.assertTrue(app.frame())
        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
        self.assertFalse(app.handle_events())

    def test_events_become_visual_effects(self):
        w = self.app.world
        o = w.organisms[0]
        o.energy = -1.0  # dies on the next tick
        self.app.frame()
        deaths = [e for e in self.app.effects.items if e[0] == "death"]
        self.assertTrue(deaths)
        for _ in range(simulator.EFFECT_FRAMES["death"] + 1):
            self.app.update()
        self.assertFalse([e for e in self.app.effects.items
                          if e[0] == "death" and e[1][:2] == (o.x, o.y)])

    def test_all_effect_kinds_render(self):
        self.app.effects.add_world_events([
            ("steal", 100, 100, 110, 100),
            ("eat", 200, 200, 205, 200),
            ("death", 300, 300, "eaten", "absorber"),
            ("death", 320, 300, "starved", "absorber"),
            ("death", 340, 300, "old age", "predator"),
        ])
        self.app.draw()
        self.assertEqual(len(self.app.effects.items), 5)

    def test_click_selects_organism_for_inspection(self):
        o = self.app.world.organisms[0]
        pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1,
                                             pos=(int(o.x), int(o.y))))
        self.app.handle_events()
        self.assertIsNotNone(self.app.selected)
        self.app.draw()
        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_h))
        self.app.handle_events()
        self.assertFalse(self.app.show_legend)
        self.app.draw()

    def test_esc_key_quits(self):
        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
        self.assertFalse(self.app.handle_events())

    def test_run_max_frames(self):
        self.app.reset()
        before = [(o.x, o.y) for o in self.app.world.organisms]
        frames = self.app.run(max_frames=15)
        self.assertEqual(frames, 15)
        after = [(o.x, o.y) for o in self.app.world.organisms]
        self.assertNotEqual(before, after)

    def test_module_level_run_with_autoquit_env(self):
        os.environ["AIL_AUTOQUIT_FRAMES"] = "10"
        try:
            frames = simulator.run(seed=3)
        finally:
            del os.environ["AIL_AUTOQUIT_FRAMES"]
        self.assertEqual(frames, 10)


if __name__ == "__main__":
    unittest.main()
