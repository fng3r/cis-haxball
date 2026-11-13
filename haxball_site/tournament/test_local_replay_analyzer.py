import json
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from .local_replay_analyzer import analyze_local_replay


class LocalReplayResponseTests(SimpleTestCase):
    def test_django_omits_only_heatmaps_from_every_game_and_player(self):
        payload = {
            'schemaVersion': 1,
            'engine': 'haxball-replay-analyzer-poc',
            'games': [
                {
                    'players': [
                        {
                            'id': '1:red',
                            'goals': 2,
                            'primaryPosition': 'GK',
                            'maps': {'heatmap': [{'x': 10, 'y': 20, 'ticks': 100}], 'goals': [{'from': {}, 'to': {}}]},
                        },
                        {'id': '2:blue', 'maps': {'heatmap': []}},
                    ]
                },
                {'players': [{'id': '3:red', 'maps': {'heatmap': [{'ticks': 1}], 'passes': []}}, {'id': '4:blue'}]},
            ],
        }
        process = SimpleNamespace(returncode=0, stdout=json.dumps(payload).encode())
        with patch('tournament.local_replay_analyzer.subprocess.run', return_value=process):
            result = analyze_local_replay(b'HBR2fixture')
        for game in result['games']:
            for player in game['players']:
                self.assertNotIn('heatmap', player.get('maps', {}))
        self.assertEqual(result['games'][0]['players'][0]['goals'], 2)
        self.assertEqual(result['games'][0]['players'][0]['primaryPosition'], 'GK')
        self.assertEqual(result['games'][0]['players'][0]['maps']['goals'], [{'from': {}, 'to': {}}])
        self.assertIn('passes', result['games'][1]['players'][0]['maps'])
