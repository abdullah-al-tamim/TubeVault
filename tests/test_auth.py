from unittest.mock import Mock, patch
from tubevault.auth import Auth


def test_expired_token_is_refreshed_and_saved(db):
    secrets = Mock()
    secrets.get.return_value = '{}'
    credentials = Mock(valid=False, token='refreshed')
    credentials.to_json.return_value = '{"saved":true}'
    with patch('tubevault.auth.Credentials.from_authorized_user_info', return_value=credentials):
        auth = Auth(db, secrets, Mock())
        assert auth.token() == 'refreshed'
    credentials.refresh.assert_called_once()
    secrets.set.assert_called_once_with('google', '{"saved":true}')
