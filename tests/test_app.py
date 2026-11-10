import io
import tempfile
import unittest
from pathlib import Path
from app import app, get_playlist


class SignageTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / 'uploads').mkdir()
        app.config.update(TESTING=True, SECRET_KEY='test-only', UPLOAD_FOLDER=self.root / 'uploads', PLAYLIST_FILE=self.root / 'playlist.txt')
        self.client = app.test_client()
        self.client.get('/')
        with self.client.session_transaction() as session:
            self.csrf = session['csrf']

    def tearDown(self):
        self.temp.cleanup()

    def upload(self, name, grade='all'):
        return self.client.post('/', data={'csrf': self.csrf, 'grade': grade, 'file': (io.BytesIO(b'test-media'), name)})

    def test_upload_duplicate_unicode_and_literal_percent(self):
        name = '학교 100%25 #소식.png'
        self.upload(name)
        self.upload(name)
        self.assertEqual(get_playlist(), ['all_' + name, 'all_학교 100%25 #소식 (2).png'])
        from urllib.parse import quote
        with self.client.get('/uploads/' + quote('all_' + name, safe='')) as response:
            self.assertEqual(response.data, b'test-media')

    def test_delete_requires_post_and_token(self):
        self.upload('안내.png')
        self.assertEqual(self.client.get('/delete/all_안내.png').status_code, 200)
        self.assertEqual(len(get_playlist()), 1)
        self.assertEqual(self.client.post('/delete/all_안내.png').status_code, 400)
        self.client.post('/delete/all_안내.png', data={'csrf': self.csrf})
        self.assertEqual(get_playlist(), [])
        self.assertFalse((self.root / 'uploads' / 'all_안내.png').exists())

    def test_order_and_grade_filter(self):
        for name, grade in [('common.png', 'all'), ('one.mp4', '1'), ('two.png', '2')]:
            self.upload(name, grade)
        self.assertEqual(self.client.get('/reorder').status_code, 405)
        response = self.client.post('/reorder', data={'csrf': self.csrf, 'original': get_playlist(), 'order': ['all_common.png', '2_two.png', '1_one.mp4']})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(get_playlist(), ['all_common.png', '2_two.png', '1_one.mp4'])
        html = self.client.get('/display/1').get_data(as_text=True)
        self.assertIn('all_common.png', html)
        self.assertIn('1_one.mp4', html)
        self.assertNotIn('2_two.png', html)
        self.assertEqual(self.client.get('/display/invalid').status_code, 404)

    def test_reorder_rejects_invalid_or_stale_list(self):
        self.upload('first.png')
        self.upload('second.png')
        original = get_playlist()
        self.assertEqual(self.client.post('/reorder', data={'original': original, 'order': original}).status_code, 400)
        for invalid in [original[:1], [original[0], original[0]], ['../outside.png', original[1]]]:
            response = self.client.post('/reorder', data={'csrf': self.csrf, 'original': original, 'order': invalid})
            self.assertEqual(response.status_code, 400)
            self.assertEqual(get_playlist(), original)
        self.upload('new.png')
        response = self.client.post('/reorder', data={'csrf': self.csrf, 'original': original, 'order': original[::-1]})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(len(get_playlist()), 3)

    def test_path_and_html_safety(self):
        self.upload('../outside.png')
        self.upload('bad.html')
        self.assertEqual(get_playlist(), [])
        self.assertEqual(self.client.post('/delete/../outside.png', data={'csrf': self.csrf}).status_code, 404)
        self.upload("학교 '안내' & 소식.png")
        html = self.client.get('/').get_data(as_text=True)
        self.assertNotIn('<img onerror=alert(1)>', html)
        self.assertIn('&#39;안내&#39; &amp; 소식.png', html)

    def test_empty_and_preview(self):
        self.assertEqual(self.client.get('/display/all').status_code, 200)
        self.upload('preview.webp')
        self.assertEqual(self.client.get('/view/all_preview.webp').status_code, 200)
        self.assertEqual(self.client.get('/view/missing.png').status_code, 404)


if __name__ == '__main__':
    unittest.main()
