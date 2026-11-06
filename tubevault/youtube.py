import re
from urllib.parse import urlparse
import httpx


class APIError(Exception):
    def __init__(self, reason, retryable=False, quota=False):
        super().__init__(reason)
        self.reason, self.retryable, self.quota = reason, retryable, quota


class YouTube:
    def __init__(self, auth):
        self.auth = auth
        self.client = httpx.Client(timeout=httpx.Timeout(120, connect=20), follow_redirects=False)

    def request(self, method, endpoint, **kwargs):
        url = endpoint if endpoint.startswith("https:") else "https://www.googleapis.com/youtube/v3/" + endpoint
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname != "www.googleapis.com":
            raise APIError("Invalid upload session host")
        headers = kwargs.pop("headers", {}) | {"Authorization": "Bearer " + self.auth.token()}
        try:
            response = self.client.request(method, url, headers=headers, **kwargs)
        except httpx.HTTPError:
            raise APIError("Network interruption", retryable=True) from None
        if response.status_code in (200, 201, 204, 308):
            return response
        reason = "http_" + str(response.status_code)
        try:
            reason = response.json()["error"]["errors"][0]["reason"]
        except (ValueError, KeyError, IndexError, TypeError):
            pass
        # Only a constrained error code is persisted; never response bodies or URLs.
        reason = re.sub(r"[^a-zA-Z0-9_]", "", reason)[:80]
        quota = reason in {"quotaExceeded", "dailyLimitExceeded", "uploadLimitExceeded"}
        raise APIError(reason, response.status_code >= 500 or response.status_code in (408, 429) or reason in {"rateLimitExceeded", "userRateLimitExceeded"}, quota)

    def list_all(self, endpoint, params):
        result, token = [], None
        while True:
            body = self.request("GET", endpoint, params=params | ({"pageToken": token} if token else {})).json()
            result.extend(body.get("items", []))
            token = body.get("nextPageToken")
            if not token:
                return result

    def playlists(self):
        return self.list_all("playlists", {"part": "snippet,status", "mine": "true", "maxResults": 50})

    def uploaded_videos(self):
        channels = self.request("GET", "channels", params={"part": "contentDetails", "mine": "true"}).json().get("items", [])
        if len(channels) != 1:
            raise APIError("Cannot_verify_connected_channel")
        uploads = channels[0]["contentDetails"]["relatedPlaylists"]["uploads"]
        items = self.list_all("playlistItems", {"part": "snippet,contentDetails", "playlistId": uploads, "maxResults": 50})
        return {"channel_id": channels[0]["id"], "videos": [
            {"id": item["contentDetails"]["videoId"], "title": item["snippet"]["title"]} for item in items]}

    def ensure_playlist(self, mapping, before_create=None):
        if mapping.playlist_id:
            return mapping.playlist_id
        marker = "TubeVault collection " + mapping.id
        playlists = self.playlists()
        marked = [p for p in playlists if marker in p["snippet"].get("description", "")]
        if marked:
            return marked[0]["id"]
        matching = [p for p in playlists if p["snippet"]["title"] == mapping.title]
        if len(matching) == 1:
            return matching[0]["id"]
        if len(matching) > 1:
            raise APIError("Ambiguous_playlist_select_existing_ID")
        if before_create:
            before_create()
        return self.request("POST", "playlists", params={"part": "snippet,status"}, json={
            "snippet": {"title": mapping.title[:150], "description": marker},
            "status": {"privacyStatus": mapping.privacy}}).json()["id"]

    def start(self, job, size):
        response = self.request("POST", "https://www.googleapis.com/upload/youtube/v3/videos",
            params={"uploadType": "resumable", "part": "snippet,status", "notifySubscribers": "false"},
            headers={"X-Upload-Content-Length": str(size), "X-Upload-Content-Type": "application/octet-stream"},
            json={"snippet": {"title": job.title, "description": job.description + "\nTubeVault job " + job.id,
                              "tags": job.tags, "categoryId": "22"},
                  "status": {"privacyStatus": job.privacy, "selfDeclaredMadeForKids": job.made_for_kids}})
        return response.headers["Location"]

    def probe(self, uri, size):
        return self.request("PUT", uri, headers={"Content-Range": f"bytes */{size}", "Content-Length": "0"}, content=b"")

    def chunk(self, uri, size, offset, data):
        return self.request("PUT", uri, headers={"Content-Range": f"bytes {offset}-{offset + len(data) - 1}/{size}",
                            "Content-Type": "application/octet-stream"}, content=data)

    def video(self, video_id):
        items = self.request("GET", "videos", params={"id": video_id, "part": "status,processingDetails,snippet"}).json().get("items", [])
        if not items:
            raise APIError("Video_not_visible_yet", retryable=True)
        return items[0]

    def insert(self, playlist_id, video_id):
        existing = self.list_all("playlistItems", {"part": "contentDetails", "playlistId": playlist_id, "maxResults": 50})
        if any(p["contentDetails"]["videoId"] == video_id for p in existing):
            return
        self.request("POST", "playlistItems", params={"part": "snippet"}, json={"snippet": {
            "playlistId": playlist_id, "resourceId": {"kind": "youtube#video", "videoId": video_id}}})
