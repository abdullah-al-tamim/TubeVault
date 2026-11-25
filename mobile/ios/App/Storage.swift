import Foundation
import SQLite3
import CryptoKit
import AVFoundation
import UIKit
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
    private func legacy() throws -> [Job] {
        var stmt: OpaquePointer?
        defer { sqlite3_finalize(stmt) }
        guard sqlite3_prepare_v2(db, "SELECT json FROM queue WHERE id=1", -1, &stmt, nil) == SQLITE_OK else { throw Problem("Cannot read queue.") }
        let result = sqlite3_step(stmt)
        if result == SQLITE_DONE { return [] }
        guard result == SQLITE_ROW, let bytes = sqlite3_column_text(stmt, 0) else { throw Problem("Queue unavailable.") }
        return try JSONDecoder().decode([Job].self, from: Data(String(cString: bytes).utf8))
    }
    private func execute(_ sql: String) throws {
        guard sqlite3_exec(db,sql,nil,nil,nil) == SQLITE_OK else { throw Problem("Queue database write failed. Check available storage.") }
    }
    func load() throws -> [Job] {
        try execute("BEGIN IMMEDIATE")
        do {
            try execute("CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, position INTEGER NOT NULL, json BLOB NOT NULL)")
            for (i,job) in try legacy().enumerated() { try write(job,position:i) }
            try execute("DELETE FROM queue WHERE id=1")
            try execute("COMMIT")
        } catch { try? execute("ROLLBACK"); throw error }
        var stmt: OpaquePointer?
        defer { sqlite3_finalize(stmt) }
        guard sqlite3_prepare_v2(db,"SELECT json FROM jobs ORDER BY position,rowid",-1,&stmt,nil) == SQLITE_OK else { throw Problem("Cannot read jobs.") }
        var result = [Job]()
        while true {
            let code = sqlite3_step(stmt)
            if code == SQLITE_DONE { return result }
            guard code == SQLITE_ROW, let ptr = sqlite3_column_blob(stmt,0) else { throw Problem("Cannot read job.") }
            result.append(try JSONDecoder().decode(Job.self,from:Data(bytes:ptr,count:Int(sqlite3_column_bytes(stmt,0)))))
        }
    }
    func write(_ job:Job, position:Int) throws {
        let data = try JSONEncoder().encode(job)
        var stmt: OpaquePointer?
        defer { sqlite3_finalize(stmt) }
        let copy = unsafeBitCast(-1,to:sqlite3_destructor_type.self)
        guard sqlite3_prepare_v2(db,"INSERT OR REPLACE INTO jobs VALUES(?,?,?)",-1,&stmt,nil) == SQLITE_OK,
              sqlite3_bind_text(stmt,1,job.id.uuidString,-1,copy) == SQLITE_OK,
              sqlite3_bind_int64(stmt,2,Int64(position)) == SQLITE_OK,
              data.withUnsafeBytes({ sqlite3_bind_blob(stmt,3,$0.baseAddress,Int32($0.count),copy) }) == SQLITE_OK,
              sqlite3_step(stmt) == SQLITE_DONE else { throw Problem("Cannot save job. Check device storage.") }
    }
    func save(_ jobs:[Job], replacing old:[Job]) throws {
        try execute("BEGIN IMMEDIATE")
        do {
            let ids = Set(jobs.map(\.id))
            for job in old where !ids.contains(job.id) { try execute("DELETE FROM jobs WHERE id='\(job.id.uuidString)'") }
            for (i,job) in jobs.enumerated() where i >= old.count || old[i] != job { try write(job,position:i) }
            try execute("COMMIT")
        } catch { try? execute("ROLLBACK"); throw error }
    }
    func cleanAbandonedCopies(jobs:[Job]) throws {
        let live = Dictionary(uniqueKeysWithValues:jobs.map { ($0.id,$0) })
        for url in try FileManager.default.contentsOfDirectory(at:root,includingPropertiesForKeys:nil) {
            let ext = url.pathExtension
            guard ["","jpg","part"].contains(ext), let id = UUID(uuidString:url.deletingPathExtension().lastPathComponent) else { continue }
            let job = live[id]
            if job == nil || (ext != "jpg" && job?.videoID != nil) {
                try? FileManager.default.removeItem(at:url)
            }
        }
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
    func remainingStagingBytes() throws -> Int64 {
        let root = try storage().root
        let entries = try FileManager.default.contentsOfDirectory(at:root,includingPropertiesForKeys:[.fileSizeKey])
        var used: Int64 = 0
        for entry in entries { used += Int64(try entry.resourceValues(forKeys:[.fileSizeKey]).fileSize ?? 0) }
        let gb = defaults.integer(forKey:"stageGB")
        return Int64(gb == 0 ? 20 : gb) * 1_000_000_000 - used
    }
    func importFile(_ url: URL) async throws {
        let id = UUID(), target = try storage().media(id)
        let access = url.startAccessingSecurityScopedResource()
        defer { if access { url.stopAccessingSecurityScopedResource() } }
        do {
            let size = try url.resourceValues(forKeys:[.fileSizeKey]).fileSize ?? 0
            guard Int64(size) <= (try remainingStagingBytes()) else { throw Problem("Staging limit reached. Raise it in Settings or finish queued uploads.") }
            try await Task.detached {
                var coordinationError: NSError?, copyError: Error?
                NSFileCoordinator().coordinate(readingItemAt: url, options: [], error: &coordinationError) { source in
                    do { try FileManager.default.copyItem(at: source, to: target) } catch { copyError = error }
                }
                if let error = coordinationError { throw error }
                if let error = copyError { throw error }
            }.value
            try await record(id, name: url.lastPathComponent, source: "Files/" + url.deletingLastPathComponent().lastPathComponent, collections:[url.deletingLastPathComponent().lastPathComponent])
        } catch { try? FileManager.default.removeItem(at: target); throw error }
    }
    func importAsset(_ asset: PHAsset) async throws {
        guard !jobs.contains(where:{ $0.source == asset.localIdentifier }) else { throw Problem("This Photos original already has a queue or archive record.") }
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
            let albums = PHAssetCollection.fetchAssetCollectionsContaining(asset, with:.album, options:nil)
            let names = (0..<albums.count).compactMap { albums.object(at:$0).localizedTitle }.sorted()
            try await record(id, name: resource.originalFilename, source: asset.localIdentifier, collections:names + ["Camera Roll"])
        } catch { try? FileManager.default.removeItem(at: target); throw error }
    }
    private func record(_ id: UUID, name: String, source: String, collections:[String]) async throws {
        let url = try storage().media(id)
        let (digest, bytes) = try await Task.detached { try Storage.digest(url) }.value
        guard !jobs.contains(where: { $0.digest == digest }) else { throw Problem("\(name) already has a queue or archive record.") }
        guard try remainingStagingBytes() >= 0 else { throw Problem("Staging limit exceeded. Increase it in Settings.") }
        let rules = defaults.dictionary(forKey:"mapping." + (channel?.id ?? "")) as? [String:String] ?? [:]
        let mapped = collections.compactMap { rules[$0] }.first
        var job = Job(filename: name, source: source, bytes: bytes, digest: digest, privacy: defaults.string(forKey:"privacy") == "unlisted" ? "unlisted" : "private", playlistID: mapped ?? defaults.string(forKey:"destination") ?? "")
        job.id = id
        let asset = AVURLAsset(url:url)
        if let seconds = try? await asset.load(.duration).seconds, seconds.isFinite { job.duration = seconds }
        let preview = url.appendingPathExtension("jpg")
        let frame = AVAssetImageGenerator(asset:asset)
        frame.appliesPreferredTrackTransform = true
        frame.maximumSize = CGSize(width:200,height:150)
        if let result = try? await frame.image(at:.zero),
           let image = UIImage(cgImage:result.image).jpegData(compressionQuality:0.75) {
            try? image.write(to:preview,options:.atomic)
        }
        guard !jobs.contains(where: { $0.digest == digest }) else {
            try? FileManager.default.removeItem(at:preview)
            throw Problem("This video was just added to the queue.")
        }
        try persist(jobs + [job])
    }
}
