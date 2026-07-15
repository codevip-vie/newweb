import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import google_drive


class SaveRefreshTokenTests(unittest.TestCase):
    def test_save_refresh_token_updates_account_object(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            account = SimpleNamespace(index=2, oauth_refresh_token="old-token")
            token_file = Path(tmpdir) / "google_drive_oauth_2.json"
            os.environ["GOOGLE_OAUTH_TOKEN_FILE_2"] = str(token_file)
            os.environ.pop("GOOGLE_OAUTH_REFRESH_TOKEN_2", None)

            google_drive.save_refresh_token("new-token", account)

            self.assertEqual(account.oauth_refresh_token, "new-token")
            self.assertEqual(os.environ.get("GOOGLE_OAUTH_REFRESH_TOKEN_2"), "new-token")


if __name__ == "__main__":
    unittest.main()
