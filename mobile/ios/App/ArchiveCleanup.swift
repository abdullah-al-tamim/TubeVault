import SwiftUI
import Photos
import CryptoKit
import UniformTypeIdentifiers

struct CleanupSelection: Identifiable {
    let id = UUID()
    let jobs: [Job]
}

extension Model {
    func verifyBackups(_ records:[Job]) async throws {
        guard !records.isEmpty, let owner = channel?.id,
              records.allSatisfy({ $0.channel == owner && $0.videoID.map(Rule.safeID) == true && $0.confirmed == $0.bytes && $0.originalDeleted == nil }) else {
            throw Problem("Select backed-up videos from the connected channel.")
        }
        for start in stride(from:0,to:records.count,by:50) {
            let group = records[start..<min(records.count,start+50)]
            let ids = group.compactMap(\.videoID).joined(separator:",")
            let result = try await api.request("videos",["part":"snippet,status","id":ids])
            let items = result["items"] as? [[String:Any]] ?? []
            for job in group {
                guard let item = items.first(where:{ $0["id"] as? String == job.videoID }),
                      let snippet = item["snippet"] as? [String:Any], snippet["channelId"] as? String == owner,
                      let status = item["status"] as? [String:Any], status["uploadStatus"] as? String == "processed"
                else { throw Problem("YouTube has not confirmed a processed backup on this channel for \(job.filename).") }
            }
        }
    }
    func photosForDeletion(_ records:[Job]) throws -> [PHAsset] {
        let found = PHAsset.fetchAssets(withLocalIdentifiers:records.map(\.source),options:nil)
        var assets = [String:PHAsset]()
        found.enumerateObjects { asset,_,_ in assets[asset.localIdentifier] = asset }
        return try records.map { job in
            guard let asset = assets[job.source], asset.mediaType == .video, asset.canPerform(.delete),
                  (asset.modificationDate ?? .distantPast) <= job.created,
                  !PHAssetResource.assetResources(for:asset).contains(where:{ $0.type == .adjustmentData || $0.type == .fullSizeVideo })
            else { throw Problem("\(job.filename) is unavailable, edited, or read-only. Its original was kept.") }
            return asset
        }
    }
    func deleteSelectedPhotos(_ records:[Job]) async throws {
        try await verifyBackups(records)
        let assets = try photosForDeletion(records)
        try await PHPhotoLibrary.shared().performChanges { PHAssetChangeRequest.deleteAssets(assets as NSArray) }
        var next = jobs
        let removed = Set(records.map(\.id))
        for i in next.indices where removed.contains(next[i].id) { next[i].originalDeleted = Date() }
        try persist(next)
    }
    func deleteSelectedFile(_ job:Job, url:URL) async throws {
        try await verifyBackups([job])
        try await Task.detached {
            guard url.startAccessingSecurityScopedResource() else { throw Problem("The file provider did not grant write access.") }
            defer { url.stopAccessingSecurityScopedResource() }
            var coordinationError: NSError?
            var operationError: Error?
            NSFileCoordinator().coordinate(writingItemAt:url,options:.forDeleting,error:&coordinationError) { coordinated in
                do {
                    guard job.filename == coordinated.lastPathComponent, job.source == "Files/" + coordinated.deletingLastPathComponent().lastPathComponent else { throw Problem("Choose the original file from the recorded folder.") }
                    let (digest, size) = try Storage.digest(coordinated)
                    guard digest == job.digest, size == job.bytes else { throw Problem("The selected file differs from the uploaded bytes. It was kept.") }
                    try FileManager.default.removeItem(at:coordinated)
                } catch { operationError = error }
            }
            if let error = coordinationError { throw error }
            if let error = operationError { throw error }
        }.value
        try edit(job.id) { $0.originalDeleted = Date() }
    }
}

struct CleanupReview: View {
    let records:[Job]
    @EnvironmentObject private var model:Model
    @Environment(\.dismiss) private var dismiss
    @State private var confirm = false
    @State private var working = false
    @State private var pickFile = false
    @State private var file:URL?
    @State private var message = ""
    private var containsFiles: Bool { records.contains { $0.source.hasPrefix("Files/") } }
    var body: some View {
        NavigationStack {
            List {
                Section("Selected originals") {
                    ForEach(records) { job in
                        VStack(alignment:.leading) { Text(job.filename); Text(bytes(job.bytes)).font(.caption) }
                    }
                }
                Text("Your YouTube videos and archive records stay available.")
                if containsFiles {
                    if records.count == 1 {
                        Button(file?.lastPathComponent ?? "Locate original in Files") { pickFile = true }
                        Text("Choose the original from its recorded folder. TubeVault checks its contents before deletion. A cloud file provider may sync deletion to other devices.")
                    } else { Text("Select Files imports one at a time so you can identify the original. Photos videos can be deleted together.") }
                } else {
                    Text("With iCloud Photos, deletion syncs to your other devices. Photos normally keeps videos in Recently Deleted for 30 days.")
                }
                if !message.isEmpty { Text(message) }
                if working { ProgressView("Checking backup and updating originals…") }
                Button("Delete selected originals…",role:.destructive) { confirm = true }
                    .disabled(working || (containsFiles && (file == nil || records.count != 1)))
            }
            .navigationTitle("Free up space")
            .toolbar { Button("Close") { dismiss() }.disabled(working) }
            .interactiveDismissDisabled(working)
            .fileImporter(isPresented:$pickFile,allowedContentTypes:[.movie,.video]) { result in
                if case .success(let url) = result { file = url }
            }
            .confirmationDialog("Delete \(records.count) selected original(s)?",isPresented:$confirm,titleVisibility:.visible) {
                Button("Delete from device",role:.destructive) { Task {
                    working = true
                    defer { working = false }
                    do {
                        if containsFiles {
                            guard let file, let job = records.first, records.count == 1 else { return }
                            try await model.deleteSelectedFile(job,url:file)
                        } else { try await model.deleteSelectedPhotos(records) }
                        dismiss()
                    } catch { message = (error as? Problem)?.message ?? "Deletion was cancelled or could not be completed. Check Photos or Files before retrying." }
                } }
                Button("Cancel",role:.cancel) {}
            }
        }
    }
}
