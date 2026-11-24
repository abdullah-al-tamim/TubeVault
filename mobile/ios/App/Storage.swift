import Foundation
import SQLite3
import CryptoKit
import Photos
import UniformTypeIdentifiers

final class Storage {
    let root: URL
    private var db: OpaquePointer?
    init() throws {
        root = try FileManager.default.url(for: .applicationSupportDirectory, in: .userDomainMask, appropriateFor: nil, create: true).appendingPathComponent("TubeVault", isDirectory: true)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true, attributes: [.protectionKey: FileProtectionType.completeUntilFirstUserAuthentication])
        var dir = root, values = URLResourceValues()
        values.isExcludedFromBackup = true
        try dir.setResourceValues(values)
        guard sqlite3_open(root.appendingPathComponent("queue.sqlite").path, &db) == SQLITE_OK,
              sqlite3_exec(db, "CREATE TABLE IF NOT EXISTS queue(id INTEGER PRIMARY KEY, json TEXT NOT NULL)", nil, nil, nil) == SQLITE_OK else { throw Problem("Unable to open the upload database.") }
    }
    deinit { sqlite3_close(db) }
    func load() throws -> [Job] {
        var stmt: OpaquePointer?
        defer { sqlite3_finalize(stmt) }
        guard sqlite3_prepare_v2(db, "SELECT json FROM queue WHERE id=1", -1, &stmt, nil) == SQLITE_OK else { throw Problem("Cannot read queue.") }
        let result = sqlite3_step(stmt)
        if result == SQLITE_DONE { return [] }
        guard result == SQLITE_ROW, let bytes = sqlite3_column_text(stmt, 0) else { throw Problem("Queue unavailable.") }
        return try JSONDecoder().decode([Job].self, from: Data(String(cString: bytes).utf8))
    }
    func save(_ jobs: [Job]) throws {
        let json = String(decoding: try JSONEncoder().encode(jobs), as: UTF8.self)
        var stmt: OpaquePointer?
        defer { sqlite3_finalize(stmt) }
        guard sqlite3_prepare_v2(db, "INSERT OR REPLACE INTO queue VALUES(1,?)", -1, &stmt, nil) == SQLITE_OK,
              sqlite3_bind_text(stmt, 1, json, -1, unsafeBitCast(-1, to: sqlite3_destructor_type.self)) == SQLITE_OK,
              sqlite3_step(stmt) == SQLITE_DONE else { throw Problem("Cannot save queue. Free device storage and reopen TubeVault.") }
    }
    func media(_ id: UUID) -> URL { root.appendingPathComponent(id.uuidString) }
    func tail(_ id: UUID) -> URL { media(id).appendingPathExtension("part") }
    static func digest(_ file: URL) throws -> (String, Int64) {
        let reader = try FileHandle(forReadingFrom: file)
        defer { try? reader.close() }
        var hash = SHA256(), length: Int64 = 0
        while let data = try reader.read(upToCount: 1024 * 1024), !data.isEmpty {
            hash.update(data: data)
            length += Int64(data.count)
        }
        guard length > 0 else { throw Problem("The selected video is empty.") }
        return (hash.finalize().map { String(format:"%02x",$0) }.joined(), length)
    }
}
extension Model {
    func importFile(_ url: URL) async throws {
        let id = UUID(), target = try storage().media(id)
        let access = url.startAccessingSecurityScopedResource()
        defer { if access { url.stopAccessingSecurityScopedResource() } }
        do {
            try await Task.detached {
                var coordinationError: NSError?, copyError: Error?
                NSFileCoordinator().coordinate(readingItemAt: url, options: [], error: &coordinationError) { source in
                    do { try FileManager.default.copyItem(at: source, to: target) } catch { copyError = error }
                }
                if let error = coordinationError { throw error }
                if let error = copyError { throw error }
            }.value
            try await record(id, name: url.lastPathComponent, source: "Files/" + url.deletingLastPathComponent().lastPathComponent)
        } catch { try? FileManager.default.removeItem(at: target); throw error }
    }
    func importAsset(_ asset: PHAsset) async throws {
        guard let resource = PHAssetResource.assetResources(for: asset).first(where: { $0.type == .video }) else { throw Problem("Original video is unavailable.") }
        let id = UUID(), target = try storage().media(id)
        let options = PHAssetResourceRequestOptions()
        options.isNetworkAccessAllowed = true
        options.progressHandler = { value in Task { @MainActor in self.importStatus = "Retrieving original: \(Int(value * 100))%" } }
        defer { importStatus = "" }
        do {
            try await withCheckedThrowingContinuation { (c: CheckedContinuation<Void, Error>) in
                PHAssetResourceManager.default().writeData(for: resource, toFile: target, options: options) { error in
                    if let error { c.resume(throwing: error) } else { c.resume() }
                }
            }
            try await record(id, name: resource.originalFilename, source: asset.localIdentifier)
        } catch { try? FileManager.default.removeItem(at: target); throw error }
    }
    private func record(_ id: UUID, name: String, source: String) async throws {
        let url = try storage().media(id)
        let (digest, bytes) = try await Task.detached { try Storage.digest(url) }.value
        guard !jobs.contains(where: { $0.digest == digest }) else { throw Problem("\(name) already has a queue or archive record.") }
        var job = Job(filename: name, source: source, bytes: bytes, digest: digest, privacy: defaults.string(forKey:"privacy") == "unlisted" ? "unlisted" : "private", playlistID: defaults.string(forKey:"destination") ?? "")
        job.id = id
        try persist(jobs + [job])
    }
}
