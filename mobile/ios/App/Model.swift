import SwiftUI
import UIKit
import Photos
import UniformTypeIdentifiers

@MainActor final class Model: ObservableObject {
    static let shared = Model()
    let auth: Google
    var api: YouTube { YouTube(auth: auth) }
    let defaults = UserDefaults.standard
    @Published private(set) var jobs = [Job]()
    private var meters = [UUID:TransferMeter]()
    func meter(_ id:UUID) -> TransferMeter {
        if let existing = meters[id] { return existing }
        let meter = TransferMeter()
        meters[id] = meter
        return meter
    }
    @Published var notice = ""
    private var samples = [UUID:(Date,Int64)]()

    @Published var photoAssets = [PHAsset]()
    func scanPhotos(request: Bool) async {
        let status: PHAuthorizationStatus
        if request { status = await PHPhotoLibrary.requestAuthorization(for:.readWrite) }
        else { status = PHPhotoLibrary.authorizationStatus(for:.readWrite) }
        guard status == .authorized || status == .limited else {
            photoAssets = []
            if request { notice = "Allow Photos access in iPhone Settings." }
            return
        }
        let options = PHFetchOptions()
        options.sortDescriptors = [NSSortDescriptor(key:"creationDate",ascending:false)]
        let result = PHAsset.fetchAssets(with:.video,options:options)
        photoAssets = (0..<result.count).map { result.object(at:$0) }
    }
    func progress(_ id: UUID, count: Int64) {
        let now = Date()
        var speed: Double?
        if let (time,previous) = samples[id] {
            let interval = now.timeIntervalSince(time)
            guard interval >= 1 else { return }
            if count > previous { speed = Double(count - previous) / interval }
        }
        meter(id).reading = (count,speed)
        samples[id] = (now,count)
    }
    @Published var importStatus = ""
    @Published var channel: Destination?
    @Published var playlists = [Destination]()
    @Published var busy = Set<UUID>()
    @Published var accountBusy = false
    private var database: Storage?
    var concurrency: Int { max(1, min(4, defaults.integer(forKey:"concurrency"))) }
    private var draining = false
    func startSelected(_ selection: Set<UUID>) {
        guard let channel, !accountBusy else { return }
        do {
            var next = jobs
            for i in next.indices where selection.contains(next[i].id) && next[i].phase == .queued {
                next[i].phase = .waiting
                next[i].batchOwner = channel.id
            }
            try persist(next)
            Task { await drain() }
        } catch { show(error) }
    }
    func drain() async {
        guard !draining, !accountBusy, let owner = channel?.id else { return }
        draining = true
        defer { draining = false }
        while channel?.id == owner, !accountBusy {
            let active = jobs.filter { [.creating,.probing,.uploading].contains($0.phase) }
            guard Set(active.map(\.id)).union(busy).count < concurrency,
                  let next = jobs.first(where:{ $0.phase == .waiting && $0.batchOwner == owner && !busy.contains($0.id) }) else { break }
            await run(next.id)
        }
    }
    func recover(_ job: Job, video: String) async throws {
        guard job.phase == .uncertain, Rule.safeID(video), let channel, channel.id == job.channel else { throw Problem("Enter a video ID and connect the original channel.") }
        let result = try await api.request("videos",["part":"snippet,status","id":video])
        guard let item = (result["items"] as? [[String:Any]])?.first,
              let snippet = item["snippet"] as? [String:Any], snippet["channelId"] as? String == job.channel,
              (snippet["description"] as? String)?.components(separatedBy:.newlines).contains("TubeVault job " + job.id.uuidString) == true else { throw Problem("Channel and upload marker must both match.") }
        let receipt = try JSONSerialization.data(withJSONObject:["id":video])
        received(job.id,response:HTTPURLResponse(url:URL(string:"https://www.googleapis.com")!,statusCode:200,httpVersion:nil,headerFields:nil),data:receipt,interrupted:false)
    }
    private func scheduleRetry(_ id: UUID) {
        guard defaults.bool(forKey:"autoRetry"), let job = jobs.first(where:{ $0.id == id }), job.retries < 4 else { return }
        do { try edit(id) { $0.retries += 1 } } catch { show(error); return }
        let seconds = pow(2.0, Double(job.retries + 2)) + Double.random(in:0...3)
        Task {
            try? await Task.sleep(nanoseconds:UInt64(seconds * 1_000_000_000))
            guard jobs.first(where:{ $0.id == id })?.phase == .paused else { return }
            await run(id)
        }
    }
    init(auth: Google? = nil) {
        self.auth = auth ?? Google()
        do {
            let db = try Storage()
            jobs = try db.load()
            database = db
            try db.cleanAbandonedCopies(jobs:jobs)
        } catch { notice = "Queue could not be opened. Reopen after unlocking or freeing storage." }
    }
    func storage() throws -> Storage {
        guard let database else { throw Problem("Local queue unavailable. Reopen TubeVault.") }
        return database
    }
    func persist(_ value: [Job]) throws { try storage().save(value, replacing:jobs); jobs = value }
    func edit(_ id: UUID, _ change: (inout Job) -> Void) throws {
        guard let i = jobs.firstIndex(where: { $0.id == id }) else { throw Problem("Queue item missing.") }
        var job = jobs[i]
        change(&job)
        try storage().write(job, position:i)
        jobs[i] = job
    }
    func show(_ error: Error) { notice = (error as? Problem)?.message ?? "Operation interrupted. Check connectivity, available storage and permissions, then retry." }
    func account(_ login: Bool = false) async {
        guard !accountBusy, busy.isEmpty else { return }
        accountBusy = true
        defer { accountBusy = false; Task { await drain() } }
        do {
            if login { try await auth.signIn() }
            if try Vault.read("google") == nil { return }
            let channels = try await api.list("channels")
            guard let current = channels.first else { throw Problem("No YouTube channel found. Choose your channel during Google sign-in.") }
            if defaults.string(forKey:"lastChannel") != current.id {
                defaults.removeObject(forKey:"destination")
                defaults.set(current.id, forKey:"lastChannel")
            }
            channel = current
            playlists = try await api.list("playlists")
        } catch { channel = nil; playlists = []; show(error) }
    }
    func logout() throws {
        guard !accountBusy, busy.isEmpty, !jobs.contains(where: { $0.phase == .uploading || $0.phase == .creating || $0.phase == .probing }) else { throw Problem("Pause active transfers before switching accounts.") }
        try Vault.remove("google")
        channel = nil
        playlists = []
        defaults.removeObject(forKey:"destination")
    }
    func sessionURL(_ id: UUID) throws -> URL? {
        guard let data = try Vault.read(id.uuidString) else { return nil }
        guard let url = URL(string: String(decoding: data, as: UTF8.self)), Self.validSession(url) else { throw Problem("Cannot verify stored session address.") }
        return url
    }
    static func validSession(_ url: URL) -> Bool {
        url.scheme == "https" && ["www.googleapis.com","youtube.googleapis.com","upload.youtube.com"].contains(url.host?.lowercased() ?? "") && url.user == nil && url.password == nil && (url.port == nil || url.port == 443)
    }
    func reconcile() async {
        let tasks = await Transfers.shared.session.allTasks
        let active = Set(tasks.compactMap(\.taskDescription))
        for job in jobs where job.phase == .preparing && !busy.contains(job.id) {
            do { try edit(job.id) { $0.phase = .paused; $0.detail = "Preparation interrupted. Resume to continue." } } catch { show(error) }
        }
        for job in jobs where [.creating,.probing,.uploading].contains(job.phase) && !active.contains(job.id.uuidString) && !busy.contains(job.id) {
            do {
                let known = try sessionURL(job.id) != nil
                try edit(job.id) { $0.phase = known ? .paused : .uncertain; $0.detail = known ? "Transfer interrupted. Resume to check YouTube’s offset." : "Session creation was interrupted. Inspect YouTube Studio before reconciling." }
            } catch { show(error) }
        }
    }
    func run(_ id: UUID) async {
        guard !accountBusy, busy.insert(id).inserted else { return }
        defer { busy.remove(id); if !draining { Task { await drain() } } }
        guard var job = jobs.first(where: { $0.id == id }), ![.done,.uncertain,.creating,.uploading,.probing].contains(job.phase) else { return }
        do {
            guard let channel, job.channel.isEmpty || job.channel == channel.id else { throw Problem("Connect the original YouTube channel before continuing.") }
            if job.videoID != nil { try await associate(job); return }
            guard Set(jobs.filter({ $0.phase == .uploading || $0.phase == .creating || $0.phase == .probing }).map(\.id)).union(busy).subtracting([id]).count < concurrency else { throw Problem("Transfer limit reached. Try again after another upload finishes.") }
            if defaults.bool(forKey:"charging") {
                UIDevice.current.isBatteryMonitoringEnabled = true
                guard [.charging,.full].contains(UIDevice.current.batteryState) else { throw Problem("Connect power or turn off the charging preference.") }
            }
            if job.needsPhotoResource == true {
                try edit(id) { $0.phase = .preparing; $0.detail = "Reading original bytes from Photos." }
                try await preparePhoto(job)
                guard let prepared = jobs.first(where:{ $0.id == id }) else { throw Problem("Queue item missing.") }; job = prepared
            }
            let file = try storage().media(id)
            guard FileManager.default.fileExists(atPath: file.path) else { throw Problem("Staged original is missing. Review the job before importing again.") }
            let token = try await auth.token()
            var url: URL
            if let existing = try sessionURL(id) {
                url = existing
                try edit(id) { $0.phase = .probing; $0.lastAttempt = Date(); $0.detail = "" }
                var probe = URLRequest(url: url)
                probe.httpMethod = "PUT"
                probe.allowsCellularAccess = defaults.bool(forKey: "cellular")
                probe.setValue("Bearer " + token, forHTTPHeaderField: "Authorization")
                probe.setValue("bytes */\(job.bytes)", forHTTPHeaderField: "Content-Range")
                probe.setValue("0", forHTTPHeaderField: "Content-Length")
                let (data, response) = try await auth.transport.data(for: probe)
                guard let http = response as? HTTPURLResponse else { throw Problem("No server response.") }
                if http.statusCode != 308 { received(id, response: http, data: data, interrupted: false); return }
                guard let offset = Rule.offset(http.value(forHTTPHeaderField:"Range"), total: job.bytes), offset < job.bytes else { throw Problem("No final video ID from YouTube. Check Studio and retry the status probe.") }
                try edit(id) { $0.confirmed = offset }
            } else {
                guard job.channel.isEmpty else { try edit(id) { $0.phase = .uncertain }; return }
                var req = URLRequest(url: URL(string:"https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status")!)
                req.httpMethod = "POST"
                req.allowsCellularAccess = defaults.bool(forKey:"cellular")
                req.setValue("Bearer " + token, forHTTPHeaderField:"Authorization")
                req.setValue("application/json", forHTTPHeaderField:"Content-Type")
                req.setValue(String(job.bytes), forHTTPHeaderField:"X-Upload-Content-Length")
                req.setValue(mime(job), forHTTPHeaderField:"X-Upload-Content-Type")
                let title = String(job.filename.prefix(100))
                req.httpBody = try JSONSerialization.data(withJSONObject:["snippet":["title": title, "description":"TubeVault job " + id.uuidString], "status":["privacyStatus":job.privacy]])
                try edit(id) { $0.phase = .creating; $0.channel = channel.id; $0.lastAttempt = Date(); $0.detail = "" }
                let (data,response) = try await auth.transport.data(for:req)
                guard let http = response as? HTTPURLResponse else { throw Problem("No session receipt.") }
                guard (200..<300).contains(http.statusCode) else {
                    if [400,401,403,413,415,429].contains(http.statusCode) { try edit(id) { $0.channel = ""; $0.phase = .failed } }
                    throw YouTube.failure(http.statusCode,data:data)
                }
                guard let location = http.value(forHTTPHeaderField:"Location"), let session = URL(string:location), Self.validSession(session) else { throw Problem("Invalid session receipt. Check Studio.") }
                url = session
                try Vault.put(id.uuidString,Data(location.utf8))
            }
            let offset = jobs.first(where: { $0.id == id })!.confirmed
            var body = file
            var end = job.bytes
            if offset > 0 {
                end = offset + min(job.bytes - offset, 16 * 1024 * 1024)
                let length = end - offset
                body = try storage().tail(id)
                let target = body
                try await Task.detached {
                    let input = try FileHandle(forReadingFrom:file)
                    defer { try? input.close() }
                    try input.seek(toOffset:UInt64(offset))
                    try Data().write(to:target)
                    let output = try FileHandle(forWritingTo:target)
                    defer { try? output.close() }
                    var left = length
                    while left > 0 {
                        guard let block = try input.read(upToCount:Int(min(left,1024 * 1024))), !block.isEmpty else { throw Problem("Staged video is incomplete.") }
                        try output.write(contentsOf:block)
                        left -= Int64(block.count)
                    }
                }.value
            }
            var req = URLRequest(url:url)
            req.httpMethod = "PUT"
            req.allowsCellularAccess = defaults.bool(forKey:"cellular")
            req.setValue("Bearer " + token, forHTTPHeaderField:"Authorization")
            req.setValue(mime(job), forHTTPHeaderField:"Content-Type")
            req.setValue("bytes \(offset)-\(end-1)/\(job.bytes)", forHTTPHeaderField:"Content-Range")
            try edit(id) { $0.phase = .uploading; $0.detail = "File handed to iOS. Network scheduling can delay transmission." }
            let task = Transfers.shared.session.uploadTask(with:req,fromFile:body)
            task.taskDescription = id.uuidString
            task.resume()
        } catch {
            do { try edit(id) { j in
                if j.phase == .creating { j.phase = .uncertain }
                else if j.videoID != nil { j.phase = .playlist }
                else if j.phase != .uncertain { j.phase = .failed }
                j.detail = (error as? Problem)?.message ?? "Connection or staging interrupted. Check storage and connectivity."
            } } catch { show(error) }
        }
    }
    private func mime(_ job: Job) -> String { UTType(filenameExtension:(job.filename as NSString).pathExtension)?.preferredMIMEType ?? "application/octet-stream" }
    func received(_ id: UUID, response: HTTPURLResponse?, data: Data, interrupted: Bool) {
        defer { Task { await drain() } }
        meters.removeValue(forKey:id)?.reading = nil
        samples[id] = nil

        guard let job = jobs.first(where: { $0.id == id }), job.videoID == nil else { return }
        do {
            let status = response?.statusCode ?? 0
            if (200..<300).contains(status), let obj = (try? JSONSerialization.jsonObject(with:data)) as? [String:Any], let video = obj["id"] as? String, Rule.safeID(video) {
                try edit(id) { $0.videoID = video; $0.confirmed = job.bytes; $0.completed = Date(); $0.phase = job.playlistID.isEmpty ? .done : .playlist; $0.detail = "YouTube accepted the upload. Processing status can be refreshed in Archive." }
                try Vault.remove(id.uuidString)
                try? FileManager.default.removeItem(at: storage().media(id))
                try? FileManager.default.removeItem(at: storage().tail(id))
                if !job.playlistID.isEmpty { Task { await Task.yield(); await run(id) } }
            } else {
                try edit(id) { j in
                    if j.phase == .cancelled && interrupted { j.detail = "Cancelled. The saved session is retained for recovery." }
                    else if status == 404 || status == 410 { j.phase = .uncertain; j.detail = "Session expired. Check YouTube Studio for the job marker." }
                    else if status == 308, let offset = Rule.offset(response?.value(forHTTPHeaderField:"Range"),total:j.bytes) { j.phase = .paused; j.confirmed = offset; j.detail = "Server confirmed partial receipt. Resume to send remaining bytes." }
                    else { j.phase = .paused; j.detail = interrupted ? "Transfer stopped. Resume to check confirmed bytes." : YouTube.failure(status,data:data).message }
                }
            }
            if !interrupted, status == 308, job.phase == .uploading, let offset = Rule.offset(response?.value(forHTTPHeaderField:"Range"),total:job.bytes), offset > job.confirmed, offset < job.bytes {
                try? FileManager.default.removeItem(at: storage().tail(id))
                try edit(id) { $0.phase = .waiting; $0.batchOwner = job.channel; $0.detail = "Waiting to send the next part of this upload." }
            }
            if !interrupted && (status == 429 || (500..<600).contains(status)) { scheduleRetry(id) }
        } catch { show(error) }
    }
    private func associate(_ job: Job) async throws {
        guard let video = job.videoID, Rule.safeID(video), Rule.safeID(job.playlistID) else { throw Problem("Invalid playlist or video identifier.") }
        let found = try await api.request("playlistItems",["part":"id","playlistId":job.playlistID,"videoId":video])
        if (found["items"] as? [[String:Any]])?.isEmpty == true {
            _ = try await api.request("playlistItems",["part":"snippet"],body:["snippet":["playlistId":job.playlistID,"resourceId":["kind":"youtube#video","videoId":video]]])
        } else if found["items"] as? [[String:Any]] == nil { throw Problem("Unable to confirm playlist membership.") }
        try edit(job.id) { $0.phase = .done; $0.detail = "Playlist membership confirmed." }
    }
    func pause(_ id: UUID, cancel: Bool = false) async {
        if jobs.first(where:{ $0.id == id })?.phase == .waiting, !busy.contains(id) {
            do { try edit(id) { $0.phase = $0.channel.isEmpty ? .queued : .paused; $0.batchOwner = nil; $0.detail = "" } } catch { show(error) }; return
        }
        if cancel { do { try edit(id) { $0.phase = .cancelled } } catch { show(error); return } }
        let tasks = await Transfers.shared.session.allTasks
        for task in tasks where task.taskDescription == id.uuidString { task.cancel() }
    }
    func forget(_ job: Job) throws {
        guard !busy.contains(job.id), job.phase == .queued || job.phase == .done else { throw Problem("Only queued items or completed records can be removed.") }
        try persist(jobs.filter { $0.id != job.id })
        try? FileManager.default.removeItem(at: storage().media(job.id))
        try? FileManager.default.removeItem(at: storage().media(job.id).appendingPathExtension("jpg"))
    }
}
