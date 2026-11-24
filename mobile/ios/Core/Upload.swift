import Foundation

enum Phase: String, Codable, CaseIterable {
    case queued = "Queued", creating = "Opening upload session", probing = "Checking server progress"
    case uploading = "Uploading", paused = "Paused", uncertain = "Needs reconciliation"
    case playlist = "Playlist pending", done = "Uploaded", failed = "Needs attention"
}
struct Job: Identifiable, Codable {
    var id = UUID()
    var filename: String
    var source: String
    var bytes: Int64
    var digest: String
    var privacy: String
    var playlistID: String
    var channel = ""
    var phase = Phase.queued
    var confirmed: Int64 = 0
    var videoID: String?
    var detail = ""
    var created = Date()
    var completed: Date?
    var lastAttempt: Date?
    var retries = 0
}
enum Rule {
    static func offset(_ range: String?, total: Int64) -> Int64? {
        guard let range else { return 0 }
        guard range.hasPrefix("bytes=0-"), let end = Int64(range.dropFirst(8)), end >= 0, end < total else { return nil }
        return end + 1
    }
    static func matches(_ query: String, _ text: String) -> Bool {
        var remaining = text.lowercased()[...]
        for character in query.lowercased() {
            guard let index = remaining.firstIndex(of: character) else { return false }
            remaining = remaining[remaining.index(after: index)...]
        }
        return true
    }
    static func safeID(_ id: String) -> Bool {
        !id.isEmpty && id.utf8.count <= 128 && id.utf8.allSatisfy { (65...90).contains($0) || (97...122).contains($0) || (48...57).contains($0) || $0 == 45 || $0 == 95 }
    }
}
