import unittest
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.cal_service import CalService

class TestCalServiceRedirect(unittest.TestCase):
    def test_google_meet_extracted(self):
        payload = {
            "uid": "12345",
            "references": [
                {
                    "type": "google_calendar",
                    "meetingUrl": "https://meet.google.com/abc-defg-hij"
                }
            ]
        }
        url = CalService.extract_meet_link(payload)
        self.assertEqual(url, "https://meet.google.com/abc-defg-hij")

    def test_zoom_extracted(self):
        payload = {
            "uid": "12345",
            "references": [
                {
                    "type": "zoom_video",
                    "meetingUrl": "https://zoom.us/j/1234567890"
                }
            ]
        }
        url = CalService.extract_meet_link(payload)
        self.assertEqual(url, "https://zoom.us/j/1234567890")

    def test_daily_video_branded_via_metadata(self):
        payload = {
            "uid": "5nZHsktLZoU8C4sQuwAW7d",
            "metadata": {
                "videoCallUrl": "https://app.cal.com/video/5nZHsktLZoU8C4sQuwAW7d"
            },
            "references": [
                {
                    "type": "daily_video",
                    "meetingUrl": "https://meetco.daily.co/as6bXkRHhyhfMtOOU0lI"
                }
            ]
        }
        url = CalService.extract_meet_link(payload)
        self.assertEqual(url, "https://app.cal.com/video/5nZHsktLZoU8C4sQuwAW7d")

    def test_daily_video_branded_constructed_via_uid(self):
        payload = {
            "uid": "5nZHsktLZoU8C4sQuwAW7d",
            "references": [
                {
                    "type": "daily_video",
                    "meetingUrl": "https://meetco.daily.co/as6bXkRHhyhfMtOOU0lI"
                }
            ]
        }
        url = CalService.extract_meet_link(payload)
        self.assertEqual(url, "https://app.cal.com/video/5nZHsktLZoU8C4sQuwAW7d")

    def test_fallback_to_references_if_no_uid(self):
        payload = {
            "references": [
                {
                    "type": "daily_video",
                    "meetingUrl": "https://meetco.daily.co/as6bXkRHhyhfMtOOU0lI"
                }
            ]
        }
        url = CalService.extract_meet_link(payload)
        self.assertEqual(url, "https://meetco.daily.co/as6bXkRHhyhfMtOOU0lI")

if __name__ == "__main__":
    unittest.main()
