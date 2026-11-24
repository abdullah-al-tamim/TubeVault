import Foundation
import AuthenticationServices
import CryptoKit
import UIKit
import Security

struct Problem: LocalizedError {
    let message: String
    init(_ message: String) { self.message = message }
    var errorDescription: String? { message }
}
enum Vault {
    static func query(_ key: String) -> [String: Any] {
        [kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: "TubeVault.iOS", kSecAttrAccount as String: key]
    }
    static func read(_ key: String) throws -> Data? {
        var q = query(key)
        q[kSecReturnData as String] = true
        var result: CFTypeRef?
        let status = SecItemCopyMatching(q as CFDictionary, &result)
        if status == errSecItemNotFound { return nil }
        guard status == errSecSuccess, let data = result as? Data else { throw Problem("Unlock your phone to access the Keychain.") }
        return data
    }
    static func put(_ key: String, _ data: Data) throws {
        var q = query(key)
        let attrs: [String: Any] = [kSecValueData as String: data, kSecAttrAccessible as String: kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly]
        var status = SecItemUpdate(q as CFDictionary, attrs as CFDictionary)
        if status == errSecItemNotFound {
            q.merge(attrs) { _, new in new }
            status = SecItemAdd(q as CFDictionary, nil)
        }
        guard status == errSecSuccess else { throw Problem("Could not save recovery information to Keychain.") }
    }
    static func remove(_ key: String) throws {
        let status = SecItemDelete(query(key) as CFDictionary)
        guard status == errSecSuccess || status == errSecItemNotFound else { throw Problem("Unlock the phone and retry.") }
    }
}
struct Credentials: Codable {
    var access: String
    var refresh: String
    var expires: Date
}
@MainActor final class Google: NSObject, ASWebAuthenticationPresentationContextProviding {
    private var browser: ASWebAuthenticationSession?
    private let client = Bundle.main.object(forInfoDictionaryKey: "GoogleClientID") as? String ?? ""
    private var refreshTask: Task<String, Error>?
    func presentationAnchor(for session: ASWebAuthenticationSession) -> ASPresentationAnchor {
        UIApplication.shared.connectedScenes.compactMap { ($0 as? UIWindowScene)?.keyWindow }.first ?? UIWindow()
    }
    private func encode(_ values: [String: String]) -> Data {
        let allowed = CharacterSet.alphanumerics.union(CharacterSet(charactersIn: "-._~"))
        return Data(values.map { key, value in key + "=" + (value.addingPercentEncoding(withAllowedCharacters: allowed) ?? "") }.joined(separator: "&").utf8)
    }
    func signIn() async throws {
        guard !client.isEmpty else { throw Problem("Build with GOOGLE_IOS_CLIENT_ID configured. See the Google setup guide.") }
        guard browser == nil else { throw Problem("Finish the current sign-in first.") }
        let verifier = UUID().uuidString + UUID().uuidString
        let challenge = Data(SHA256.hash(data: Data(verifier.utf8))).base64EncodedString().replacingOccurrences(of: "+", with: "-").replacingOccurrences(of: "/", with: "_").replacingOccurrences(of: "=", with: "")
        let state = UUID().uuidString
        let scheme = client.components(separatedBy: ".").reversed().joined(separator: ".")
        let redirect = scheme + ":/oauthredirect"
        var url = URLComponents(string: "https://accounts.google.com/o/oauth2/v2/auth")!
        url.queryItems = ["client_id": client, "scope": "https://www.googleapis.com/auth/youtube.force-ssl", "redirect_uri": redirect, "response_type": "code", "state": state, "code_challenge": challenge, "code_challenge_method": "S256", "prompt": "select_account consent"].map { URLQueryItem(name: $0.key, value: $0.value) }
        defer { browser = nil }
        let callback: URL = try await withCheckedThrowingContinuation { continuation in
            let session = ASWebAuthenticationSession(url: url.url!, callbackURLScheme: scheme) { url, _ in
                if let url { continuation.resume(returning: url) } else { continuation.resume(throwing: Problem("Sign-in cancelled or unavailable.")) }
            }
            browser = session
            session.presentationContextProvider = self
            if !session.start() { continuation.resume(throwing: Problem("Could not present Google sign-in.")) }
        }
        browser = nil
        let items = URLComponents(url: callback, resolvingAgainstBaseURL: false)?.queryItems ?? []
        guard callback.scheme == scheme, callback.path == "/oauthredirect", items.first(where: { $0.name == "state" })?.value == state,
              let code = items.first(where: { $0.name == "code" })?.value else { throw Problem("Google did not authorize the requested access.") }
        _ = try await exchange(["code": code, "redirect_uri": redirect, "grant_type": "authorization_code", "code_verifier": verifier], previous: "")
    }
    private func exchange(_ fields: [String: String], previous: String) async throws -> String {
        var req = URLRequest(url: URL(string: "https://oauth2.googleapis.com/token")!)
        req.httpMethod = "POST"
        req.setValue("application/x-www-form-urlencoded", forHTTPHeaderField: "Content-Type")
        req.httpBody = encode(fields.merging(["client_id": client]) { _, new in new })
        let (data, res) = try await URLSession.shared.data(for: req)
        guard (res as? HTTPURLResponse)?.statusCode == 200, let obj = try JSONSerialization.jsonObject(with: data) as? [String: Any],
              let access = obj["access_token"] as? String, let ttl = obj["expires_in"] as? Double else { throw Problem("Google authorization expired or was refused. Reconnect in Settings.") }
        let refresh = obj["refresh_token"] as? String ?? previous
        guard !refresh.isEmpty else { throw Problem("Google did not grant offline access. Reconnect with consent.") }
        try Vault.put("google", JSONEncoder().encode(Credentials(access: access, refresh: refresh, expires: Date().addingTimeInterval(ttl))))
        return access
    }
    func token() async throws -> String {
        guard let data = try Vault.read("google") else { throw Problem("Connect Google in Settings.") }
        let c = try JSONDecoder().decode(Credentials.self, from: data)
        if c.expires.timeIntervalSinceNow > 90 { return c.access }
        if let refreshTask { return try await refreshTask.value }
        let task = Task { try await exchange(["grant_type": "refresh_token", "refresh_token": c.refresh], previous: c.refresh) }
        refreshTask = task
        defer { refreshTask = nil }
        return try await task.value
    }
}
struct Destination: Identifiable, Hashable { let id: String; let title: String }
@MainActor struct YouTube {
    let auth: Google
    static func failure(_ status: Int, data: Data) -> Problem {
        let json = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any]
        let error = json?["error"] as? [String: Any]
        let reason = (error?["errors"] as? [[String: Any]])?.first?["reason"] as? String
        switch (status, reason) {
        case (401, _): return Problem("Google authorization expired. Reconnect the same channel.")
        case (_, "quotaExceeded"), (_, "dailyLimitExceeded"), (_, "uploadLimitExceeded"): return Problem("Google quota or channel upload limit reached. Retry after the limit resets.")
        case (403, _): return Problem("Channel permissions or restrictions blocked this operation.")
        case (404, _): return Problem("The remote resource was removed or the session expired.")
        case (413, _), (415, _), (400, _): return Problem("Google rejected the file or metadata. Check size, format and title.")
        case (429, _), (500...599, _): return Problem("Google is busy (HTTP \(status)). Retry later.")
        default: return Problem("Google returned HTTP \(status).")
        }
    }
    func request(_ path: String, _ query: [String:String], body: [String:Any]? = nil) async throws -> [String:Any] {
        var url = URLComponents(string: "https://www.googleapis.com/youtube/v3/" + path)!
        url.queryItems = query.map { URLQueryItem(name: $0.key, value: $0.value) }
        var req = URLRequest(url: url.url!)
        req.setValue("Bearer " + (try await auth.token()), forHTTPHeaderField: "Authorization")
        if let body {
            req.httpMethod = "POST"
            req.setValue("application/json", forHTTPHeaderField: "Content-Type")
            req.httpBody = try JSONSerialization.data(withJSONObject: body)
        }
        let (data, res) = try await URLSession.shared.data(for: req)
        let status = (res as? HTTPURLResponse)?.statusCode ?? 0
        guard (200..<300).contains(status) else { throw Self.failure(status, data: data) }
        return try JSONSerialization.jsonObject(with: data) as? [String:Any] ?? [:]
    }
    func list(_ resource: String) async throws -> [Destination] {
        var result: [Destination] = [], page: String?
        repeat {
            var q = ["part":"snippet", "mine":"true", "maxResults":"50"]
            q["pageToken"] = page
            let data = try await request(resource,q)
            for row in data["items"] as? [[String:Any]] ?? [] {
                if let id = row["id"] as? String, Rule.safeID(id), let title = (row["snippet"] as? [String:Any])?["title"] as? String { result.append(Destination(id:id,title:title)) }
            }
            page = data["nextPageToken"] as? String
        } while page != nil
        return result
    }
}
